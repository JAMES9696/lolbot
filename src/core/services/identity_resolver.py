"""Identity Resolver Service - Unified account identity resolution for 方案C.

This service provides a single entry point for resolving user identities across
multiple input formats:
- Discord user's primary account (no params)
- Discord user's Nth account (numeric index)
- Riot ID lookup (Name#Tag format)
- Discord mention (@user)

Architecture:
- Separates "invoker" (who called the command, receives TTS) from "target" (whose data is queried)
- Supports 1:N account bindings per Discord user
- Handles caching for Riot API calls
"""

import logging
import re
from dataclasses import dataclass
from typing import Literal

from src.core.ports import DatabasePort, RiotAPIPort

logger = logging.getLogger(__name__)


# ========================================================================
# Exceptions
# ========================================================================


class IdentityResolutionError(Exception):
    """Base exception for identity resolution failures."""

    pass


class NoBindingError(IdentityResolutionError):
    """Raised when user has no account binding."""

    pass


class AccountNotFoundError(IdentityResolutionError):
    """Raised when specified account index doesn't exist."""

    pass


class RiotAPIError(IdentityResolutionError):
    """Raised when Riot API lookup fails."""

    pass


class InvalidInputError(IdentityResolutionError):
    """Raised when input format is invalid."""

    pass


# ========================================================================
# Contracts
# ========================================================================


@dataclass(frozen=True)
class ResolvedIdentity:
    """Immutable identity resolution result.

    This contract is the single source of truth for downstream services.
    """

    # Core identity
    puuid: str  # Riot PUUID (78 chars)
    summoner_name: str  # Format: "GameName#TAG"
    region: str  # Lowercase region code (e.g., 'na1', 'kr')

    # Metadata for context
    source: Literal["binding", "riot_api"]  # Where data came from
    is_self: bool  # True if target == invoker (affects TTS person)
    account_index: int | None  # If from binding, which account (1-based, None for API)

    # Optional enrichment
    nickname: str | None = None  # User-defined alias (if from binding)

    def display_name(self) -> str:
        """Get human-readable display name.

        Prioritizes nickname over summoner_name for better UX.
        """
        return self.nickname or self.summoner_name


# ========================================================================
# Service Implementation
# ========================================================================


class IdentityResolver:
    """Unified identity resolution service.

    Handles all input formats for /战绩 command and resolves to PUUID + metadata.
    """

    # Regex pattern for Riot ID format: GameName#TAG
    RIOT_ID_PATTERN = re.compile(r"^(.+?)#([A-Za-z0-9]{2,5})$")

    def __init__(self, db: DatabasePort, riot_api: RiotAPIPort):
        """Initialize resolver with required dependencies.

        Args:
            db: Database adapter for binding lookups
            riot_api: Riot API adapter for RiotID → PUUID resolution
        """
        self.db = db
        self.riot_api = riot_api
        logger.info("IdentityResolver initialized")

    async def resolve(
        self,
        invoker_discord_id: str,
        target: str | None = None,
        guild_id: str | None = None,
    ) -> ResolvedIdentity:
        """Resolve identity from various input formats.

        Args:
            invoker_discord_id: Discord user who invoked the command (for TTS)
            target: Optional target parameter (None, number, Name#Tag, or @mention)
            guild_id: Optional guild ID (reserved for future region inference)

        Returns:
            ResolvedIdentity with all required fields

        Raises:
            NoBindingError: When target=None but user has no binding
            AccountNotFoundError: When index is out of range
            RiotAPIError: When Riot API lookup fails
            InvalidInputError: When input format is invalid
        """
        # Priority 1: No target → Query invoker's primary account
        if target is None:
            return await self._resolve_primary_account(invoker_discord_id)

        # Priority 2: Pure number → Query invoker's Nth account
        if target.isdigit():
            index = int(target)
            return await self._resolve_account_by_index(invoker_discord_id, index)

        # Priority 3: Name#Tag → Riot API lookup
        riot_id_match = self.RIOT_ID_PATTERN.match(target)
        if riot_id_match:
            game_name, tag_line = riot_id_match.groups()
            return await self._resolve_riot_id(invoker_discord_id, game_name, tag_line, guild_id)

        # Priority 4: Discord mention → Query mentioned user's primary account
        if target.startswith("<@") and target.endswith(">"):
            mentioned_discord_id = target.strip("<@!>")
            return await self._resolve_mentioned_user(invoker_discord_id, mentioned_discord_id)

        # Unrecognized format
        raise InvalidInputError(
            f"无效的查询格式: {target}\n"
            f"支持的格式:\n"
            f"  • 留空 - 查询自己的主账号\n"
            f"  • 数字 (如 2) - 查询自己的第N个账号\n"
            f"  • Name#TAG (如 Faker#KR) - 查询任意召唤师\n"
            f"  • @用户 - 查询队友的主账号"
        )

    # ========================================================================
    # Resolution Strategies (Private)
    # ========================================================================

    async def _resolve_primary_account(self, discord_id: str) -> ResolvedIdentity:
        """Resolve to user's primary (default) account."""
        binding = await self.db.get_primary_account(discord_id)

        if not binding:
            raise NoBindingError(
                "你还没有绑定拳头账号！\n" "请先使用 `/bind` 命令绑定你的LOL账号，然后再查询战绩。"
            )

        return ResolvedIdentity(
            puuid=binding["riot_puuid"],
            summoner_name=binding["summoner_name"],
            region=binding["region"],
            source="binding",
            is_self=True,
            account_index=1,  # Primary is always conceptually index 1
            nickname=binding.get("nickname"),
        )

    async def _resolve_account_by_index(self, discord_id: str, index: int) -> ResolvedIdentity:
        """Resolve to user's Nth account (1-based user input → 0-based DB query)."""
        if index <= 0:
            raise InvalidInputError(
                f"账号序号必须大于0！你输入的是 {index}。\n"
                f"提示：使用 `/accounts` 查看你的所有绑定账号。"
            )

        # Convert 1-based user input to 0-based array index
        db_index = index - 1

        binding = await self.db.get_account_by_index(discord_id, db_index)

        if not binding:
            # Check total accounts for better error message
            all_accounts = await self.db.list_user_accounts(discord_id)
            total = len(all_accounts)

            if total == 0:
                raise NoBindingError(
                    "你还没有绑定任何拳头账号！\n" "请先使用 `/bind` 命令绑定账号。"
                )

            raise AccountNotFoundError(
                f"你只绑定了 {total} 个账号，但你查询的是第 {index} 个账号。\n"
                f"提示：使用 `/accounts` 查看所有绑定账号。"
            )

        return ResolvedIdentity(
            puuid=binding["riot_puuid"],
            summoner_name=binding["summoner_name"],
            region=binding["region"],
            source="binding",
            is_self=True,
            account_index=index,  # User-facing 1-based index
            nickname=binding.get("nickname"),
        )

    async def _resolve_riot_id(
        self,
        invoker_discord_id: str,
        game_name: str,
        tag_line: str,
        guild_id: str | None,
    ) -> ResolvedIdentity:
        """Resolve via Riot API lookup (temporary query, no binding required).

        Args:
            invoker_discord_id: Who invoked the command (for is_self check)
            game_name: Riot Game Name (before #)
            tag_line: Riot Tag Line (after #)
            guild_id: Optional guild ID for region inference

        Returns:
            ResolvedIdentity with source='riot_api'
        """
        # Infer region from guild or use default
        # TODO: Implement guild → region mapping when multi-region support is added
        region = "americas"  # Default continent for Riot API

        try:
            account_data = await self.riot_api.get_account_by_riot_id(
                game_name=game_name, tag_line=tag_line, region=region
            )
        except Exception as e:
            logger.error(f"Riot API lookup failed for {game_name}#{tag_line}: {e}")
            raise RiotAPIError(
                f"无法找到召唤师 {game_name}#{tag_line}\n"
                f"请检查拼写是否正确，或确认该账号是否存在。"
            ) from e

        if not account_data:
            raise RiotAPIError(
                f"召唤师 {game_name}#{tag_line} 不存在。\n" f"请检查游戏名称和标签（如 Faker#KR）。"
            )

        puuid = account_data.get("puuid")
        if not puuid:
            raise RiotAPIError("Riot API 返回的数据格式异常（缺少 PUUID）")

        # Check if this PUUID belongs to the invoker (cross-check with bindings)
        # This supports the case: user has binding, but queries via RiotID
        is_self = await self._check_if_own_account(invoker_discord_id, puuid)

        # Default platform region to na1 (can be refined with match history later)
        platform_region = "na1"

        return ResolvedIdentity(
            puuid=puuid,
            summoner_name=f"{game_name}#{tag_line}",
            region=platform_region,
            source="riot_api",
            is_self=is_self,
            account_index=None,  # Not from binding
            nickname=None,
        )

    async def _resolve_mentioned_user(
        self, invoker_discord_id: str, mentioned_discord_id: str
    ) -> ResolvedIdentity:
        """Resolve to mentioned Discord user's primary account."""
        binding = await self.db.get_primary_account(mentioned_discord_id)

        if not binding:
            raise NoBindingError(
                f"<@{mentioned_discord_id}> 还没有绑定拳头账号。\n"
                f"提醒 TA 使用 `/bind` 命令绑定账号吧！"
            )

        return ResolvedIdentity(
            puuid=binding["riot_puuid"],
            summoner_name=binding["summoner_name"],
            region=binding["region"],
            source="binding",
            is_self=(invoker_discord_id == mentioned_discord_id),  # Self if mentioning self
            account_index=1,  # Mentioned user's primary account
            nickname=binding.get("nickname"),
        )

    async def _check_if_own_account(self, discord_id: str, puuid: str) -> bool:
        """Check if a PUUID belongs to the invoker's bindings.

        Used for RiotID lookups to detect self-queries.
        """
        try:
            all_accounts = await self.db.list_user_accounts(discord_id)
            return any(acc["riot_puuid"] == puuid for acc in all_accounts)
        except Exception as e:
            logger.warning(f"Failed to check account ownership for {discord_id}: {e}")
            return False  # Default to not-self on error

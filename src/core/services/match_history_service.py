"""Match history service implementation.

Bridges IMatchHistoryService port to Riot API and Database adapters.
Used by DiscordAdapter to implement the /讲道理 command flow.
"""

from __future__ import annotations


from src.adapters.database import DatabaseAdapter
from src.adapters.riot_api import RiotAPIAdapter
from src.core.ports.match_history_port import IMatchHistoryService


class MatchHistoryService(IMatchHistoryService):
    """Production implementation of match history service."""

    def __init__(self, riot_api: RiotAPIAdapter, db: DatabaseAdapter) -> None:
        self.riot_api = riot_api
        self.db = db

    async def get_match_id_list(self, puuid: str, region: str, count: int = 20) -> list[str]:
        return await self.riot_api.get_match_history(puuid=puuid, region=region, count=count)

    async def get_analysis_status(self, match_id: str) -> dict[str, str] | None:
        record = await self.db.get_analysis_result(match_id)
        if not record:
            return None

        status = str(record.get("status", "unknown"))
        created_at = str(record.get("created_at")) if record.get("created_at") else ""
        # Optional: result presence indicator; keep payload small
        has_result = "llm_narrative" in record or "score_data" in record

        return {
            "status": status,
            "created_at": created_at,
            "has_result": "true" if has_result else "false",
        }

    async def get_puuid_by_riot_id(self, game_name: str, tag_line: str) -> str | None:
        """Resolve a Riot ID (game_name#tag) to a PUUID using Account-V1.

        Args:
            game_name: Riot ID game name
            tag_line: Riot ID tag line (e.g., NA1, EUW, KR)

        Returns:
            PUUID string if found, else None
        """
        acct = await self.riot_api.get_account_by_riot_id(game_name=game_name, tag_line=tag_line)
        return acct.get("puuid") if acct else None

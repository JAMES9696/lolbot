"""Riot API adapter using Cassiopeia + Match-V5 REST.

Provides:
- Account-V1 (REST)
- Match-V5 IDs/Match/Timeline (REST)
- Summoner by PUUID (Cassiopeia)

Implements RiotAPIPort with consistent async semantics and session reuse.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import cassiopeia as cass
from cassiopeia import Summoner

from src.config.settings import settings
from src.contracts import SummonerDTO
from src.core.ports import RiotAPIPort


class RiotAPIError(Exception):
    def __init__(
        self, message: str, status_code: int | None = None, retry_after: int | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimitError(RiotAPIError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded", status_code=429, retry_after=retry_after)


logger = logging.getLogger(__name__)


class RiotAPIAdapter(RiotAPIPort):
    def __init__(self) -> None:
        cass.apply_settings(
            {
                "api_key": settings.riot_api_key,
                "default_region": "NA",
                "rate_limiter": {
                    "type": "application",
                    "limiting_share": 1.0,
                    "include_429s": False,
                },
                "cache": {
                    "type": "lru",
                    "expiration_time": {"summoner": 3600, "match": 86400, "match_timeline": 86400},
                },
            }
        )
        try:
            logging.getLogger("datapipelines.pipelines").setLevel(logging.WARNING)
            logging.getLogger("cassiopeia").setLevel(logging.WARNING)
        except Exception:
            pass
        self._session: Any | None = None
        self._session_loop: asyncio.AbstractEventLoop | None = None
        logger.info("Riot API adapter initialized")

    async def _ensure_session(self):
        import aiohttp

        loop = asyncio.get_running_loop()
        needs_new_session = (
            self._session is None
            or getattr(self._session, "closed", True)
            or self._session_loop is None
            or self._session_loop is not loop
        )
        if needs_new_session:
            if self._session and not getattr(self._session, "closed", True):
                try:
                    await self._session.close()
                except Exception:
                    logger.warning("Failed to close stale Riot API session", exc_info=True)
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._session_loop = loop
        return self._session

    async def close(self) -> None:
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        except Exception:
            pass
        finally:
            self._session = None
            self._session_loop = None

    async def get_account_by_riot_id(
        self, game_name: str, tag_line: str, region: str = "americas"
    ) -> dict[str, str] | None:
        from urllib.parse import quote

        encoded_name = quote(game_name)
        encoded_tag = quote(tag_line)
        url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{encoded_name}/{encoded_tag}"
        headers = {"X-Riot-Token": settings.riot_api_key}
        try:
            session = await self._ensure_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "puuid": data.get("puuid", ""),
                        "game_name": data.get("gameName", game_name),
                        "tag_line": data.get("tagLine", tag_line),
                    }
                if resp.status == 404:
                    return None
                if resp.status == 429:
                    raise RateLimitError(int(resp.headers.get("Retry-After", "60")))
                logger.error(f"Account API error {resp.status}: {await resp.text()}")
                return None
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Account API error for {game_name}#{tag_line}: {e}")
            return None

    async def get_summoner_by_discord_id(self, discord_id: str) -> dict[str, Any] | None:
        logger.warning(f"get_summoner_by_discord_id not implemented for {discord_id}")
        return None

    async def get_summoner_by_puuid(self, puuid: str, region: str = "NA") -> SummonerDTO | None:
        try:
            cass_region = self._convert_region(region)
            summoner = await asyncio.to_thread(Summoner, puuid=puuid, region=cass_region)
            await asyncio.to_thread(summoner.load)
            return SummonerDTO(
                accountId=summoner.account_id,
                profileIconId=summoner.profile_icon.id,
                revisionDate=int(summoner.revision_date.timestamp()),
                id=summoner.id,
                puuid=summoner.puuid,
                summonerLevel=summoner.level,
                name=summoner.name,
            )
        except Exception as e:
            logger.error(f"Summoner fetch error for puuid {puuid}: {e}")
            return None

    async def get_match_history(self, puuid: str, region: str, count: int = 20) -> list[str]:
        route = self._regional_routing(region)
        url = f"https://{route}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={max(1, min(count, 100))}"
        headers = {"X-Riot-Token": settings.riot_api_key}
        try:
            session = await self._ensure_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [str(m) for m in data] if isinstance(data, list) else []
                if resp.status == 404:
                    return []
                if resp.status == 429:
                    raise RateLimitError(int(resp.headers.get("Retry-After", "60")))
                logger.error(f"Match IDs API error {resp.status}: {await resp.text()}")
                return []
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Match history error for puuid {puuid}: {e}")
            return []

    async def get_match_details(self, match_id: str, region: str) -> dict[str, Any] | None:
        route = self._regional_routing(region)
        url = f"https://{route}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        headers = {"X-Riot-Token": settings.riot_api_key}
        try:
            session = await self._ensure_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, dict) else None
                if resp.status == 404:
                    return None
                if resp.status == 429:
                    raise RateLimitError(int(resp.headers.get("Retry-After", "60")))
                if resp.status == 403:
                    raise RiotAPIError("Forbidden: Check API key permissions", status_code=403)
                logger.error(f"Match details API error {resp.status}: {await resp.text()}")
                return None
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Match details error for {match_id}: {e}")
            return None

    async def get_match_timeline(self, match_id: str, region: str) -> dict[str, Any] | None:
        route = self._regional_routing(region)
        url = f"https://{route}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        headers = {"X-Riot-Token": settings.riot_api_key}
        try:
            session = await self._ensure_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    if not (isinstance(raw, dict) and "info" in raw and "metadata" in raw):
                        logger.error("Unexpected timeline payload shape")
                        return None
                    # Participants mapping
                    match_details = await self.get_match_details(match_id, region)
                    participants_map: list[dict[str, Any]] = []
                    if match_details and isinstance(match_details.get("info"), dict):
                        info_md = match_details["info"]
                        parts = info_md.get("participants", [])
                        if isinstance(parts, list):
                            for i, p in enumerate(parts[:10]):
                                participants_map.append(
                                    {
                                        "participant_id": int(p.get("participantId", i + 1)),
                                        "puuid": str(p.get("puuid", "")),
                                    }
                                )
                    if not participants_map:
                        meta_parts = raw.get("metadata", {}).get("participants", [])
                        if isinstance(meta_parts, list) and len(meta_parts) == 10:
                            participants_map = [
                                {"participant_id": i + 1, "puuid": str(p)}
                                for i, p in enumerate(meta_parts)
                            ]

                    # Convert frames
                    def _cs_map(d: dict[str, Any]) -> dict[str, Any]:
                        m = {
                            "abilityHaste": "ability_haste",
                            "abilityPower": "ability_power",
                            "armor": "armor",
                            "armorPen": "armor_pen",
                            "armorPenPercent": "armor_pen_percent",
                            "attackDamage": "attack_damage",
                            "attackSpeed": "attack_speed",
                            "bonusArmorPenPercent": "bonus_armor_pen_percent",
                            "bonusMagicPenPercent": "bonus_magic_pen_percent",
                            "ccReduction": "cc_reduction",
                            "cooldownReduction": "cooldown_reduction",
                            "health": "health",
                            "healthMax": "health_max",
                            "healthRegen": "health_regen",
                            "lifesteal": "lifesteal",
                            "magicPen": "magic_pen",
                            "magicPenPercent": "magic_pen_percent",
                            "magicResist": "magic_resist",
                            "movementSpeed": "movement_speed",
                            "omnivamp": "omnivamp",
                            "physicalVamp": "physical_vamp",
                            "power": "power",
                            "powerMax": "power_max",
                            "powerRegen": "power_regen",
                            "spellVamp": "spell_vamp",
                        }
                        return {m.get(k, k): v for k, v in d.items()}

                    def _ds_map(d: dict[str, Any]) -> dict[str, Any]:
                        m = {
                            "magicDamageDone": "magic_damage_done",
                            "magicDamageDoneToChampions": "magic_damage_done_to_champions",
                            "magicDamageTaken": "magic_damage_taken",
                            "physicalDamageDone": "physical_damage_done",
                            "physicalDamageDoneToChampions": "physical_damage_done_to_champions",
                            "physicalDamageTaken": "physical_damage_taken",
                            "totalDamageDone": "total_damage_done",
                            "totalDamageDoneToChampions": "total_damage_done_to_champions",
                            "totalDamageTaken": "total_damage_taken",
                            "trueDamageDone": "true_damage_done",
                            "trueDamageDoneToChampions": "true_damage_done_to_champions",
                            "trueDamageTaken": "true_damage_taken",
                        }
                        return {m.get(k, k): v for k, v in d.items()}

                    frames: list[dict[str, Any]] = []
                    for fr in raw.get("info", {}).get("frames", []) or []:
                        pf_raw = fr.get("participantFrames", {}) or {}
                        pf_conv: dict[str, Any] = {}
                        for key, val in pf_raw.items():
                            if isinstance(val, dict):
                                pf_conv[str(key)] = {
                                    "participant_id": int(val.get("participantId", key)),
                                    "champion_stats": _cs_map(val.get("championStats", {})),
                                    "damage_stats": _ds_map(val.get("damageStats", {})),
                                    "current_gold": val.get("currentGold", 0),
                                    "gold_per_second": val.get("goldPerSecond", 0),
                                    "jungle_minions_killed": val.get("jungleMinionsKilled", 0),
                                    "level": val.get("level", 1),
                                    "minions_killed": val.get("minionsKilled", 0),
                                    "position": val.get("position", {}),
                                    "time_enemy_spent_controlled": val.get(
                                        "timeEnemySpentControlled", 0
                                    ),
                                    "total_gold": val.get("totalGold", 0),
                                    "xp": val.get("xp", 0),
                                }
                        frames.append(
                            {
                                "timestamp": fr.get("timestamp", 0),
                                "participant_frames": pf_conv,
                                "events": fr.get("events", []),
                            }
                        )

                    meta = raw.get("metadata", {})
                    info = raw.get("info", {})
                    game_id = 0
                    if match_details and isinstance(match_details.get("info"), dict):
                        try:
                            game_id = int(match_details["info"].get("gameId", 0))
                        except Exception:
                            game_id = 0

                    return {
                        "metadata": {
                            "data_version": meta.get("dataVersion", ""),
                            "match_id": meta.get("matchId", match_id),
                            "participants": meta.get("participants", []),
                        },
                        "info": {
                            "frame_interval": info.get("frameInterval", 60000),
                            "frames": frames,
                            "game_id": game_id,
                            "participants": participants_map,
                        },
                    }
                if resp.status == 404:
                    return None
                if resp.status == 429:
                    raise RateLimitError(int(resp.headers.get("Retry-After", "60")))
                if resp.status == 403:
                    raise RiotAPIError("Forbidden: Check API key permissions", status_code=403)
                logger.error(f"Timeline API error {resp.status}: {await resp.text()}")
                return None
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Timeline error for {match_id}: {e}")
            return None

    def _convert_region(self, region: str) -> str:
        mapping = {
            "na1": "NA",
            "euw1": "EUW",
            "eune1": "EUNE",
            "kr": "KR",
            "br1": "BR",
            "la1": "LAN",
            "la2": "LAS",
            "oc1": "OCE",
            "ru": "RU",
            "tr1": "TR",
            "jp1": "JP",
        }
        return mapping.get(region.lower(), "NA")

    def _regional_routing(self, platform_region: str) -> str:
        pr = platform_region.upper()
        americas = {"NA1", "BR1", "LA1", "LA2", "OC1"}
        europe = {"EUW1", "EUN1", "RU", "TR1"}
        asia = {"KR", "JP1"}
        sea = {"PH2", "SG2", "TH2", "TW2", "VN2"}
        if pr in americas:
            return "americas"
        if pr in europe:
            return "europe"
        if pr in asia:
            return "asia"
        if pr in sea:
            return "sea"
        return "americas"

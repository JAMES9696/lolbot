import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class DDragonAdapter:
    def __init__(self, version: str | None = None, language: str = "en_US") -> None:
        self.base_url = "https://ddragon.leagueoflegends.com"
        self.version = version
        self.language = language
        self.cache: dict[str, Any] = {}
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "DDragonAdapter":
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.session:
            await self.session.close()

    async def get_latest_version(self) -> str | None:
        """Fetch the latest game version from versions.json"""
        cache_key = "latest_version"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(f"{self.base_url}/api/versions.json") as response:
                if response.status == 200:
                    versions = await response.json()
                    self.cache[cache_key] = versions[0]
                    return versions[0]
                else:
                    logger.warning(f"Failed to fetch latest version. Status: {response.status}")
                    return None
        except Exception as e:
            logger.warning(f"Network error while fetching latest version: {e}")
            return None

    def set_version(self, version: str) -> None:
        """Set a specific version for data fetching"""
        self.version = version
        self.clear_cache()

    async def _get_version(self) -> str | None:
        """Get current version or fetch latest if not set"""
        if self.version:
            return self.version
        return await self.get_latest_version()

    async def _fetch_data(self, endpoint: str) -> dict[str, Any] | None:
        """Helper method to fetch data from DDragon"""
        version = await self._get_version()
        if not version:
            return None

        cache_key = f"{endpoint}_{version}_{self.language}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            url = f"{self.base_url}/cdn/{version}/data/{self.language}/{endpoint}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.cache[cache_key] = data
                    return data
                else:
                    logger.warning(f"Failed to fetch {endpoint}. Status: {response.status}")
                    return None
        except Exception as e:
            logger.warning(f"Network error while fetching {endpoint}: {e}")
            return None

    async def get_all_champions(self) -> dict[str, Any]:
        """Get all champion data"""
        data = await self._fetch_data("champion.json")
        if not data:
            return {}
        return data.get("data", {})

    async def get_champion_by_id(self, champion_id: int) -> dict[str, Any] | None:
        """Get champion data by ID"""
        champions = await self.get_all_champions()
        for champion in champions.values():
            if int(champion.get("key", 0)) == champion_id:
                version = await self._get_version()
                if not version:
                    return None
                return {
                    "id": champion.get("id"),
                    "key": champion.get("key"),
                    "name": champion.get("name"),
                    "title": champion.get("title"),
                    "image_url": f"{self.base_url}/cdn/{version}/img/champion/{champion.get('image', {}).get('full', '')}",
                    "tags": champion.get("tags", []),
                    "info": champion.get("info", {}),
                }
        return None

    async def get_champion_by_name(self, name: str) -> dict[str, Any] | None:
        """Get champion data by name"""
        champions = await self.get_all_champions()
        champion = champions.get(name)
        if not champion:
            return None

        version = await self._get_version()
        if not version:
            return None

        return {
            "id": champion.get("id"),
            "key": champion.get("key"),
            "name": champion.get("name"),
            "title": champion.get("title"),
            "image_url": f"{self.base_url}/cdn/{version}/img/champion/{champion.get('image', {}).get('full', '')}",
            "tags": champion.get("tags", []),
            "info": champion.get("info", {}),
        }

    async def get_all_items(self) -> dict[str, Any]:
        """Get all item data"""
        data = await self._fetch_data("item.json")
        if not data:
            return {}
        return data.get("data", {})

    async def get_item_by_id(self, item_id: int) -> dict[str, Any] | None:
        """Get item data by ID"""
        items = await self.get_all_items()
        item = items.get(str(item_id))
        if not item:
            return None

        version = await self._get_version()
        if not version:
            return None

        return {
            "id": item_id,
            "name": item.get("name"),
            "description": item.get("description"),
            "image_url": f"{self.base_url}/cdn/{version}/img/item/{item.get('image', {}).get('full', '')}",
            "gold": item.get("gold", {}),
            "tags": item.get("tags", []),
        }

    async def get_all_summoner_spells(self) -> dict[str, Any]:
        """Get all summoner spell data"""
        data = await self._fetch_data("summoner.json")
        if not data:
            return {}
        return data.get("data", {})

    async def get_summoner_spell_by_id(self, spell_id: int) -> dict[str, Any] | None:
        """Get summoner spell data by ID"""
        spells = await self.get_all_summoner_spells()
        for spell in spells.values():
            if spell.get("key") == str(spell_id):
                version = await self._get_version()
                if not version:
                    return None
                return {
                    "id": spell_id,
                    "name": spell.get("name"),
                    "description": spell.get("description"),
                    "image_url": f"{self.base_url}/cdn/{version}/img/spell/{spell.get('image', {}).get('full', '')}",
                    "cooldown": spell.get("cooldown", []),
                }
        return None

    async def get_all_runes(self) -> dict[str, Any]:
        """Get all rune data"""
        data = await self._fetch_data("runesReforged.json")
        if not data:
            return {}
        return data

    async def get_rune_by_id(self, rune_id: int) -> dict[str, Any] | None:
        """Get rune data by ID"""
        runes = await self.get_all_runes()
        for rune_tree in runes:
            if rune_tree.get("id") == rune_id:
                return rune_tree
            for slot in rune_tree.get("slots", []):
                for rune in slot.get("runes", []):
                    if rune.get("id") == rune_id:
                        return rune
        return None

    async def _get_champion_data(self) -> dict[str, Any] | None:
        """Helper to get champion data for image URL generation"""
        version = await self._get_version()
        if not version:
            return None

        cache_key = f"champion_data_{version}_{self.language}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            url = f"{self.base_url}/cdn/{version}/data/{self.language}/champion.json"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    self.cache[cache_key] = data
                    return data
                else:
                    logger.warning(f"Failed to fetch champion data. Status: {response.status}")
                    return None
        except Exception as e:
            logger.warning(f"Network error while fetching champion data: {e}")
            return None

    def get_champion_image_url(self, champion_key: str) -> str:
        """Get champion image URL by champion key"""
        return f"{self.base_url}/cdn/{self.version or ''}/img/champion/{champion_key}.png"

    def get_item_image_url(self, item_id: int) -> str:
        """Get item image URL by item ID"""
        return f"{self.base_url}/cdn/{self.version or ''}/img/item/{item_id}.png"

    def get_spell_image_url(self, spell_key: str) -> str:
        """Get summoner spell image URL by spell key"""
        return f"{self.base_url}/cdn/{self.version or ''}/img/spell/{spell_key}.png"

    def clear_cache(self) -> None:
        """Clear the cache to force refresh data"""
        self.cache.clear()

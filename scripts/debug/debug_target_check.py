#!/usr/bin/env python3
"""Check Arena match target player."""
import asyncio
from src.adapters.database import DatabaseAdapter


async def main():
    db = DatabaseAdapter()
    await db.connect()

    query = """
        SELECT match_data
        FROM match_data
        WHERE match_id = 'NA1_5388494924'
    """
    row = await db._pool.fetchrow(query)

    if row:
        match_data = row["match_data"]
        parts = match_data.get("info", {}).get("participants", [])

        print(f"Arena玩家列表 (NA1_5388494924, 总共{len(parts)}人):\n")
        for i, p in enumerate(parts, 1):
            name = p.get("riotIdGameName", "Unknown")
            tag = p.get("riotIdTagline", "")
            champ = p.get("championName", "Unknown")

            # 检查是否是用户（Irelia/Fuji shan xia）
            is_irelia = champ == "Irelia"
            marker = "🎯 " if is_irelia else "   "
            full_name = f"{name}#{tag}" if tag else name
            print(f"{marker}{i}. {full_name:30} - {champ:15}")
            if is_irelia:
                puuid = p.get("puuid", "")
                print(f"      PUUID: {puuid}")

    await db.disconnect()


asyncio.run(main())

"""Simple HTTP-based Riot API test.

Bypasses Cassiopeia to test Personal API Key directly.
"""

import asyncio
import aiohttp
from src.config.settings import settings


async def test_riot_api_flow():
    """Test complete Riot API flow with Personal API Key."""
    print("=" * 60)
    print("🔑 Testing Riot API with Personal API Key (HTTP Direct)")
    print("=" * 60)
    print(f"API Key: {settings.riot_api_key[:20]}...")
    print("Summoner: Fuji shan xia#NA1")
    print("=" * 60)

    headers = {"X-Riot-Token": settings.riot_api_key}

    async with aiohttp.ClientSession() as session:
        # Step 1: Account API - Get PUUID
        print("\n📝 Step 1: Account API - Looking up Riot ID...")
        account_url = "https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Fuji%20shan%20xia/NA1"

        async with session.get(account_url, headers=headers) as resp:
            if resp.status != 200:
                print(f"❌ Account API failed: {resp.status}")
                print(await resp.text())
                return False

            account_data = await resp.json()
            puuid = account_data["puuid"]
            print("✅ Account found!")
            print(f"   PUUID: {puuid[:20]}...")
            print(f"   Game Name: {account_data['gameName']}#{account_data['tagLine']}")

        # Step 2: Summoner API - Get summoner info
        print("\n📝 Step 2: Summoner API - Fetching summoner data...")
        summoner_url = f"https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"

        async with session.get(summoner_url, headers=headers) as resp:
            if resp.status != 200:
                print(f"❌ Summoner API failed: {resp.status}")
                print(await resp.text())
                return False

            summoner_data = await resp.json()
            print("✅ Summoner found!")
            print(f"   Level: {summoner_data.get('summonerLevel', 'N/A')}")
            print(f"   Profile Icon: {summoner_data.get('profileIconId', 'N/A')}")

        # Step 3: Match-V5 API - Get match history
        print("\n📝 Step 3: Match API - Fetching match history...")
        match_history_url = (
            f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count=5"
        )

        async with session.get(match_history_url, headers=headers) as resp:
            if resp.status != 200:
                print(f"❌ Match history API failed: {resp.status}")
                print(await resp.text())
                return False

            match_ids = await resp.json()
            print(f"✅ Found {len(match_ids)} recent matches:")
            for idx, match_id in enumerate(match_ids, 1):
                print(f"   {idx}. {match_id}")

        # Step 4: Match Detail API
        if match_ids:
            first_match = match_ids[0]
            print(f"\n📝 Step 4: Match Detail API - Fetching {first_match}...")
            match_detail_url = (
                f"https://americas.api.riotgames.com/lol/match/v5/matches/{first_match}"
            )

            async with session.get(match_detail_url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"❌ Match detail API failed: {resp.status}")
                    print(await resp.text())
                    return False

                match_data = await resp.json()
                info = match_data.get("info", {})

                print("✅ Match details retrieved!")
                print(f"   Game Mode: {info.get('gameMode', 'Unknown')}")
                print(f"   Game Duration: {info.get('gameDuration', 0)}s")
                print(f"   Participants: {len(info.get('participants', []))}")

                # Find player's performance
                for participant in info.get("participants", []):
                    if participant.get("puuid") == puuid:
                        print("\n👤 Player Performance:")
                        print(f"   Champion: {participant.get('championName', 'Unknown')}")
                        print(
                            f"   KDA: {participant.get('kills', 0)}/{participant.get('deaths', 0)}/{participant.get('assists', 0)}"
                        )
                        print(f"   Win: {'✅' if participant.get('win', False) else '❌'}")
                        break

    print("\n" + "=" * 60)
    print("✅ All API tests passed! Personal API Key is working.")
    print("=" * 60)

    print("\n📊 Rate Limit Status:")
    print("   App Rate Limit: 20 req/1s, 100 req/2min")
    print("   Method Rate Limit: 2000 req/60s")
    print("   ✅ No rate limit errors encountered")

    return True


if __name__ == "__main__":
    import sys

    success = asyncio.run(test_riot_api_flow())
    sys.exit(0 if success else 1)

"""Test Riot API flow with Personal API Key.

Tests summoner lookup and match retrieval for:
Summoner: Fuji shan xia
Region: NA1
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters.riot_api import RiotAPIAdapter
from src.config.settings import settings


async def test_summoner_lookup():
    """Test summoner lookup with Fuji shan xia (NA1)."""
    print("=" * 60)
    print("🔑 Testing Riot API with Personal API Key")
    print("=" * 60)
    print(f"API Key: {settings.riot_api_key[:20]}...")
    print("Summoner: Fuji shan xia")
    print("Region: NA1")
    print("=" * 60)

    try:
        # Initialize adapter
        riot_api = RiotAPIAdapter()
        print("\n✅ RiotAPIAdapter initialized")

        # Step 1: Get PUUID from Riot ID
        print("\n📝 Step 1: Looking up account by Riot ID: Fuji shan xia#NA1...")
        account = await riot_api.get_account_by_riot_id(
            game_name="Fuji shan xia", tag_line="NA1", region="americas"
        )

        if not account:
            print("❌ Failed to find account")
            return False

        puuid = account["puuid"]
        print("✅ Account found!")
        print(f"   PUUID: {puuid[:20]}...")
        print(f"   Game Name: {account['game_name']}#{account['tag_line']}")

        # Step 2: Get summoner data from PUUID
        print("\n📝 Step 2: Fetching summoner data by PUUID...")
        summoner = await riot_api.get_summoner_by_puuid(puuid=puuid, region="NA")

        if not summoner:
            print("❌ Failed to get summoner data")
            return False

        print("\n✅ Summoner found!")
        print(f"   PUUID: {summoner.puuid[:20]}...")
        print(f"   Summoner Name: {summoner.name}")
        print(f"   Level: {summoner.level}")
        print(f"   Profile Icon: {summoner.profile_icon_id}")

        # Step 3: Test match history
        print("\n📝 Step 3: Fetching match history...")
        matches = await riot_api.get_match_history(puuid=puuid, region="americas", count=5)

        print(f"\n✅ Found {len(matches)} recent matches:")
        for idx, match_id in enumerate(matches, 1):
            print(f"   {idx}. {match_id}")

        # Step 4: Test match detail
        if matches:
            first_match_id = matches[0]
            print(f"\n📝 Step 4: Fetching match details: {first_match_id}...")
            match_detail = await riot_api.get_match_details(
                match_id=first_match_id, region="americas"
            )

            print("\n✅ Match details retrieved!")
            print(f"   Game Mode: {match_detail.get('info', {}).get('gameMode', 'Unknown')}")
            print(f"   Game Duration: {match_detail.get('info', {}).get('gameDuration', 0)}s")
            participants = match_detail.get("info", {}).get("participants", [])
            print(f"   Participants: {len(participants)}")

            # Find our summoner's performance
            for participant in participants:
                if participant.get("puuid") == puuid:
                    print("\n👤 Player Performance:")
                    print(f"   Champion: {participant.get('championName', 'Unknown')}")
                    print(
                        f"   KDA: {participant.get('kills', 0)}/{participant.get('deaths', 0)}/{participant.get('assists', 0)}"
                    )
                    print(f"   Win: {'✅' if participant.get('win', False) else '❌'}")
                    break

        print("\n" + "=" * 60)
        print("✅ All tests passed! Personal API Key is working correctly.")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"   Type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_summoner_lookup())
    sys.exit(0 if success else 1)

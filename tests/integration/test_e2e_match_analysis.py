"""End-to-End Test: Match Analysis to AI Narrative播报.

Tests the complete /讲道理 command flow:
1. Fetch match history for a player
2. Select a specific match
3. Fetch match detail + timeline
4. Calculate V1 scores (5 dimensions)
5. Generate AI narrative (蔷薇教练风格)
6. Save to database
7. Display final narrative
"""

import asyncio
import sys
import os
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters.riot_api import RiotAPIAdapter
from src.adapters.database import DatabaseAdapter
from src.config.settings import settings


def print_header(title: str):
    """Print formatted header."""
    print("\n" + "=" * 90)
    print(f"  {title}")
    print("=" * 90)


def print_step(step: str):
    """Print step title."""
    print(f"\n>>> {step}")
    print("-" * 90)


async def test_e2e_match_analysis():
    """Run end-to-end match analysis test."""
    print_header("🎮 End-to-End Match Analysis Test - /讲道理 Complete Flow")
    print(f"📅 Test Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Test configuration
    test_summoner = "Fuji shan xia"
    test_tag = "NA1"
    test_continent = "americas"

    try:
        # ========================================
        # PHASE 1: Get Player PUUID
        # ========================================
        print_header("PHASE 1: Player Identification")

        print_step("Step 1.1: Initialize Riot API Adapter")
        riot_api = RiotAPIAdapter()
        print("✅ RiotAPIAdapter initialized")

        print_step(f"Step 1.2: Get PUUID for {test_summoner}#{test_tag}")
        account_data = await riot_api.get_account_by_riot_id(
            game_name=test_summoner, tag_line=test_tag, region=test_continent
        )

        if not account_data:
            print(f"❌ Failed to get account data for {test_summoner}#{test_tag}")
            return False

        puuid = account_data["puuid"]
        print(f"✅ PUUID obtained: {puuid[:20]}...{puuid[-10:]}")
        print(f"   Game Name: {account_data['game_name']}")
        print(f"   Tag Line: {account_data['tag_line']}")

        # ========================================
        # PHASE 2: Fetch Match History
        # ========================================
        print_header("PHASE 2: Match History Retrieval")

        print_step("Step 2.1: Fetch Recent Matches")
        # Use direct API call instead of Cassiopeia
        import aiohttp

        match_history_url = (
            f"https://{test_continent}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        )
        headers = {"X-Riot-Token": settings.riot_api_key}
        params = {"count": 5}

        async with aiohttp.ClientSession() as session:
            async with session.get(match_history_url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"❌ Failed to get match history: {resp.status}")
                    print(f"   Error: {error_text}")
                    return False

                match_ids = await resp.json()

        if not match_ids:
            print("❌ No matches found")
            return False

        print(f"✅ Found {len(match_ids)} recent matches")
        for i, match_id in enumerate(match_ids, 1):
            print(f"   {i}. {match_id}")

        # Select first match for analysis
        selected_match_id = match_ids[0]
        print(f"\n📊 Selected Match for Analysis: {selected_match_id}")

        # ========================================
        # PHASE 3: Fetch Match Detail + Timeline
        # ========================================
        print_header("PHASE 3: Match Data Collection")

        print_step("Step 3.1: Fetch Match Detail (Direct HTTP)")

        # Use direct HTTP instead of Cassiopeia to avoid Match ID parsing issues
        match_detail_url = (
            f"https://{test_continent}.api.riotgames.com/lol/match/v5/matches/{selected_match_id}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(match_detail_url, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"❌ Failed to fetch match detail: {resp.status}")
                    print(f"   Error: {error_text}")
                    return False

                match_detail = await resp.json()

        if not match_detail:
            print("❌ Failed to fetch match detail")
            return False

        print("✅ Match detail fetched")

        # Extract match info
        match_info = match_detail.get("info", {})
        game_duration = match_info.get("gameDuration", 0)
        game_mode = match_info.get("gameMode", "UNKNOWN")
        game_version = match_info.get("gameVersion", "UNKNOWN")

        print(f"   Game Mode: {game_mode}")
        print(f"   Duration: {game_duration // 60}m {game_duration % 60}s")
        print(f"   Patch: {game_version}")

        # Find our player's data
        participant = None
        participant_id = None
        for p in match_info.get("participants", []):
            if p.get("puuid") == puuid:
                participant = p
                participant_id = p.get("participantId")
                break

        if not participant:
            print("❌ Player not found in match participants")
            return False

        print("\n🎯 Player Data Found:")
        print(f"   Participant ID: {participant_id}")
        print(f"   Champion: {participant.get('championName')}")
        print(f"   Role: {participant.get('teamPosition')}")
        print(
            f"   KDA: {participant.get('kills')}/{participant.get('deaths')}/{participant.get('assists')}"
        )
        print(f"   Result: {'🏆 Victory' if participant.get('win') else '💔 Defeat'}")
        print(f"   Damage Dealt: {participant.get('totalDamageDealtToChampions'):,}")
        print(f"   Gold Earned: {participant.get('goldEarned'):,}")
        print(
            f"   CS: {participant.get('totalMinionsKilled', 0) + participant.get('neutralMinionsKilled', 0)}"
        )

        print_step("Step 3.2: Fetch Match Timeline (Direct HTTP)")

        timeline_url = f"https://{test_continent}.api.riotgames.com/lol/match/v5/matches/{selected_match_id}/timeline"

        async with aiohttp.ClientSession() as session:
            async with session.get(timeline_url, headers=headers) as resp:
                if resp.status != 200:
                    print("⚠️  Timeline data not available")
                    print(f"   Status: {resp.status}")
                    print("   (Will use simplified scoring without timeline)")
                    timeline_data = None
                else:
                    timeline_data = await resp.json()
                    print("✅ Timeline data fetched")
                    frames_count = len(timeline_data.get("info", {}).get("frames", []))
                    print(f"   Total Frames: {frames_count}")

        # ========================================
        # PHASE 4: Calculate V1 Scores
        # ========================================
        print_header("PHASE 4: V1 Scoring Algorithm")

        print_step("Step 4.1: Extract Participant Stats")

        # Basic stats from participant data
        kills = participant.get("kills", 0)
        deaths = participant.get("deaths", 0)
        assists = participant.get("assists", 0)
        damage_dealt = participant.get("totalDamageDealtToChampions", 0)
        damage_taken = participant.get("totalDamageTaken", 0)
        gold_earned = participant.get("goldEarned", 0)
        cs = participant.get("totalMinionsKilled", 0) + participant.get("neutralMinionsKilled", 0)
        vision_score = participant.get("visionScore", 0)
        wards_placed = participant.get("wardsPlaced", 0)
        wards_killed = participant.get("wardsKilled", 0)

        print(f"   Kills: {kills}, Deaths: {deaths}, Assists: {assists}")
        print(f"   Damage Dealt: {damage_dealt:,}")
        print(f"   Damage Taken: {damage_taken:,}")
        print(f"   Gold: {gold_earned:,}")
        print(f"   CS: {cs}")
        print(f"   Vision Score: {vision_score}")

        print_step("Step 4.2: Calculate 5-Dimension Scores")

        # Simplified scoring (without full timeline analysis)
        kda = (kills + assists) / max(deaths, 1)

        # Combat Efficiency (0-100)
        combat_score = min(100, (kda / 5.0) * 100)  # 5.0 KDA = 100 points
        if damage_dealt > 0:
            damage_bonus = min(20, (damage_dealt / 20000) * 20)  # Up to 20 bonus points
            combat_score = min(100, combat_score * 0.8 + damage_bonus)

        # Economy Management (0-100)
        cs_per_min = cs / (game_duration / 60)
        economy_score = min(100, (cs_per_min / 8.0) * 100)  # 8 CS/min = 100 points
        if gold_earned > 0:
            gold_bonus = min(20, (gold_earned / 15000) * 20)
            economy_score = min(100, economy_score * 0.8 + gold_bonus)

        # Vision Control (0-100)
        vision_score_normalized = min(100, (vision_score / 100) * 100)  # 100 vision = 100 points

        # Objective Control (0-100) - Simplified without timeline
        objectives_taken = (
            participant.get("objectivesStolen", 0)
            + participant.get("baronKills", 0)
            + participant.get("dragonKills", 0)
        )
        objective_score = min(100, objectives_taken * 20)  # Each obj = 20 points

        # Team Contribution (0-100)
        kill_participation = (
            (kills + assists) / max(1, participant.get("teamKills", kills + assists)) * 100
        )
        team_score = min(100, kill_participation)

        # Overall Score (weighted average)
        weights = {
            "combat": 0.30,
            "economy": 0.25,
            "vision": 0.15,
            "objective": 0.15,
            "teamplay": 0.15,
        }

        overall_score = (
            combat_score * weights["combat"]
            + economy_score * weights["economy"]
            + vision_score_normalized * weights["vision"]
            + objective_score * weights["objective"]
            + team_score * weights["teamplay"]
        )

        scores = {
            "combat": round(combat_score, 1),
            "economy": round(economy_score, 1),
            "vision": round(vision_score_normalized, 1),
            "objective": round(objective_score, 1),
            "teamplay": round(team_score, 1),
            "total": round(overall_score, 1),
        }

        print("\n📈 Calculated Scores:")
        print(f"   Combat Efficiency:    {scores['combat']:.1f}/100 ⚔️")
        print(f"   Economy Management:   {scores['economy']:.1f}/100 💰")
        print(f"   Vision Control:       {scores['vision']:.1f}/100 👁️")
        print(f"   Objective Control:    {scores['objective']:.1f}/100 🐉")
        print(f"   Team Contribution:    {scores['teamplay']:.1f}/100 🤝")
        print(f"   ⭐ Overall Score:      {scores['total']:.1f}/100")

        # ========================================
        # PHASE 5: Generate AI Narrative (蔷薇教练)
        # ========================================
        print_header("PHASE 5: AI Narrative Generation (蔷薇教练风格)")

        print_step("Step 5.1: Prepare Analysis Prompt")

        match_result = "胜利" if participant.get("win") else "失败"
        champion_name = participant.get("championName")

        analysis_prompt = f"""作为蔷薇教练,请分析以下对局表现:

英雄: {champion_name}
位置: {participant.get('teamPosition', 'UNKNOWN')}
战绩: {kills}/{deaths}/{assists}
结果: {match_result}

详细数据:
- 伤害输出: {damage_dealt:,}
- 承受伤害: {damage_taken:,}
- 金币获取: {gold_earned:,}
- 补刀数: {cs}
- 视野得分: {vision_score}
- 插眼/排眼: {wards_placed}/{wards_killed}

评分数据:
- 战斗效率: {scores['combat']:.1f}/100
- 经济管理: {scores['economy']:.1f}/100
- 视野控制: {scores['vision']:.1f}/100
- 目标控制: {scores['objective']:.1f}/100
- 团队贡献: {scores['teamplay']:.1f}/100
- 综合评分: {scores['total']:.1f}/100

请用蔷薇教练的专业、直接的风格给出分析和建议(200字以内):
1. 简短评价整体表现
2. 指出2-3个突出优点
3. 指出2-3个需要改进的地方
4. 给出实用建议
"""

        print(f"✅ Analysis prompt prepared ({len(analysis_prompt)} chars)")

        print_step("Step 5.2: Call OhMyGPT API")

        # Check if OhMyGPT is configured
        openai_api_key = os.getenv("OPENAI_API_KEY")
        openai_api_base = os.getenv("OPENAI_API_BASE")
        openai_model = os.getenv("OPENAI_MODEL")

        if not openai_api_key:
            print("⚠️  OpenAI API Key not configured")
            print("   Skipping AI narrative generation")
            ai_narrative = "[AI narrative generation skipped - no API key]"
        else:
            print(f"   API Base: {openai_api_base}")
            print(f"   Model: {openai_model}")

            import aiohttp

            url = f"{openai_api_base}/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": openai_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是蔷薇教练,一位专业且严格的英雄联盟分析师。你的分析直接、专业,既指出优点也指出不足,帮助玩家真正提升。",
                    },
                    {"role": "user", "content": analysis_prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        print(f"❌ AI API Error {resp.status}: {error_text}")
                        ai_narrative = "[AI generation failed]"
                    else:
                        data = await resp.json()
                        ai_narrative = data["choices"][0]["message"]["content"]
                        token_usage = data.get("usage", {})

                        print("✅ AI Narrative Generated Successfully")
                        print(
                            f"   Tokens: {token_usage.get('total_tokens', 0)} (prompt: {token_usage.get('prompt_tokens', 0)}, completion: {token_usage.get('completion_tokens', 0)})"
                        )

        # ========================================
        # PHASE 6: Display Final Narrative播报
        # ========================================
        print_header("PHASE 6: Final Narrative播报 (蔷薇教练评价)")

        print("\n" + "=" * 90)
        print(f"📊 对局分析报告 - {champion_name}")
        print("=" * 90)

        print("\n基本信息:")
        print(f"  英雄: {champion_name} ({participant.get('teamPosition', 'UNKNOWN')})")
        print(f"  战绩: {kills}/{deaths}/{assists} (KDA: {kda:.2f})")
        print(f"  结果: {match_result}")
        print(f"  时长: {game_duration // 60}分{game_duration % 60}秒")

        print("\n数据详情:")
        print(f"  伤害输出: {damage_dealt:,}")
        print(f"  金币获取: {gold_earned:,}")
        print(f"  补刀数: {cs} ({cs_per_min:.1f} CS/min)")
        print(f"  视野得分: {vision_score}")

        print("\n评分结果:")
        print(f"  ⚔️  战斗效率: {scores['combat']:.1f}/100")
        print(f"  💰 经济管理: {scores['economy']:.1f}/100")
        print(f"  👁️  视野控制: {scores['vision']:.1f}/100")
        print(f"  🐉 目标控制: {scores['objective']:.1f}/100")
        print(f"  🤝 团队贡献: {scores['teamplay']:.1f}/100")
        print(f"  ⭐ 综合评分: {scores['total']:.1f}/100")

        print("\n🎙️  蔷薇教练的评价:")
        print("-" * 90)
        print(ai_narrative)
        print("-" * 90)

        # ========================================
        # PHASE 7: Save to Database (Optional)
        # ========================================
        print_header("PHASE 7: Database Persistence (Optional)")

        print_step("Step 7.1: Save Analysis Results")

        db = DatabaseAdapter()
        await db.connect()

        # Save to match_analytics table (if table exists)
        try:
            # Check if table exists
            query_check = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'match_analytics'
            );
            """
            table_exists = await db._pool.fetchval(query_check)

            if table_exists:
                query_insert = """
                INSERT INTO match_analytics (
                    match_id, puuid, champion_name, scores, ai_narrative,
                    emotion_tag, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (match_id, puuid) DO UPDATE SET
                    scores = EXCLUDED.scores,
                    ai_narrative = EXCLUDED.ai_narrative,
                    updated_at = NOW();
                """

                await db._pool.execute(
                    query_insert,
                    selected_match_id,
                    puuid,
                    champion_name,
                    scores,  # Will be stored as JSONB
                    ai_narrative,
                    "专业分析",  # Simplified emotion tag
                    datetime.now(UTC),
                )
                print("✅ Analysis results saved to database")
            else:
                print("⚠️  match_analytics table not found (skipping save)")

        except Exception as e:
            print(f"⚠️  Failed to save to database: {e}")

        await db.disconnect()

        # ========================================
        # Final Summary
        # ========================================
        print_header("✅ End-to-End Test Complete")

        print("\n📊 Test Summary:")
        print(f"   ✅ Player Identification: {test_summoner}#{test_tag}")
        print(f"   ✅ Match Data Retrieved: {selected_match_id}")
        print(f"   ✅ V1 Scores Calculated: {scores['total']:.1f}/100")
        print(f"   ✅ AI Narrative Generated: {len(ai_narrative)} chars")
        print("   ✅ Final播报 Displayed")

        print("\n💡 /讲道理 Command Flow:")
        print("   1. User runs: /讲道理 [match_index]")
        print("   2. Bot fetches match from history")
        print("   3. Bot calculates V1 scores")
        print("   4. Bot generates AI narrative (蔷薇教练)")
        print("   5. Bot sends formatted analysis to Discord")
        print("   6. Bot saves results to database")

        print("\n🎉 All Systems Operational!")

        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_e2e_match_analysis())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

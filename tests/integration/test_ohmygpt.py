"""Test OhMyGPT API connectivity and match analysis generation."""

import asyncio
import aiohttp
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_ohmygpt_api():
    """Test OhMyGPT API with OpenAI-compatible endpoint."""
    print("=" * 70)
    print("🤖 Testing OhMyGPT API (OpenAI-Compatible)")
    print("=" * 70)

    # OhMyGPT configuration
    api_key = "sk-KTBF5Gj319a97eF2fdA3T3BlbKFJFf88b99e6952435Ca358"
    api_base = "https://api.ohmygpt.com"
    model = "gemini-2.5-flash-lite"  # Using Gemini 2.5 Flash Lite (fast & economical)

    print("\n📝 Configuration:")
    print(f"   API Base: {api_base}")
    print(f"   API Key: {api_key[:20]}...")
    print(f"   Model: {model}")
    print("=" * 70)

    try:
        # Test 1: Simple completion
        print("\n🔍 Test 1: Basic API Connectivity...")

        url = f"{api_base}/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是蔷薇教练，一位专业的英雄联盟分析师。"},
                {
                    "role": "user",
                    "content": "请用中文简短分析：玩家使用Aurora英雄，取得11杀2死1助攻，最终获胜。请给出简短点评（50字以内）。",
                },
            ],
            "temperature": 0.7,
            "max_tokens": 200,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ API Error {response.status}:")
                    print(error_text)
                    return False

                data = await response.json()

                # Extract response
                choices = data.get("choices", [])
                if not choices:
                    print("❌ No response from API")
                    return False

                content = choices[0].get("message", {}).get("content", "")

                print("✅ API 响应成功")
                print("\n📝 生成的分析内容:")
                print("-" * 70)
                print(content)
                print("-" * 70)

        # Test 2: Match analysis with structured data
        print("\n🔍 Test 2: Match Analysis with Game Data...")

        match_data = {
            "player": {
                "champion": "Aurora",
                "kills": 11,
                "deaths": 2,
                "assists": 1,
                "result": "victory",
            },
            "scores": {
                "combat": 85.5,
                "economy": 78.2,
                "vision": 65.0,
                "objective": 72.8,
                "teamplay": 68.5,
                "total": 73.8,
            },
        }

        analysis_prompt = f"""作为蔷薇教练，请分析以下对局表现：

英雄: {match_data['player']['champion']}
战绩: {match_data['player']['kills']}/{match_data['player']['deaths']}/{match_data['player']['assists']}
结果: {'胜利' if match_data['player']['result'] == 'victory' else '失败'}

评分数据:
- 战斗效率: {match_data['scores']['combat']:.1f}
- 经济管理: {match_data['scores']['economy']:.1f}
- 视野控制: {match_data['scores']['vision']:.1f}
- 目标控制: {match_data['scores']['objective']:.1f}
- 团队贡献: {match_data['scores']['teamplay']:.1f}
- 综合评分: {match_data['scores']['total']:.1f}

请用蔷薇教练的风格给出专业分析和建议（200字以内）。"""

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是蔷薇教练，一位专业且严格的英雄联盟分析师。你会给出直接、专业的分析，既指出优点也指出需要改进的地方。",
                },
                {"role": "user", "content": analysis_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 500,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ Analysis Error {response.status}:")
                    print(error_text)
                    return False

                data = await response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                print("✅ 详细分析生成成功")
                print("\n📝 蔷薇教练的分析:")
                print("-" * 70)
                print(content)
                print("-" * 70)

                # Display token usage
                usage = data.get("usage", {})
                if usage:
                    print("\n📊 Token Usage:")
                    print(f"   Prompt: {usage.get('prompt_tokens', 0)}")
                    print(f"   Completion: {usage.get('completion_tokens', 0)}")
                    print(f"   Total: {usage.get('total_tokens', 0)}")

        # Success
        print("\n" + "=" * 70)
        print("✅ All OhMyGPT API Tests Passed!")
        print("=" * 70)

        print("\n📊 Summary:")
        print("   ✅ API Connectivity: Working")
        print("   ✅ Basic Generation: Working")
        print("   ✅ Match Analysis: Working")
        print(f"   ✅ Model: {model}")

        print("\n🎉 OhMyGPT API is ready for /讲道理 command!")
        print("\n💡 Next Steps:")
        print("   1. Create OpenAI adapter for the application")
        print("   2. Update settings.py to support OpenAI config")
        print("   3. Integrate with /讲道理 command")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_ohmygpt_api())
    sys.exit(0 if success else 1)

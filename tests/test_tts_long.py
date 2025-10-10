"""Test TTS with longer narrative text."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.adapters.tts_adapter import TTSAdapter


async def test_long_tts():
    """Test TTS with realistic game analysis text."""
    print("🎤 Testing TTS with Long Narrative...")
    print("-" * 60)

    adapter = TTSAdapter()

    # Realistic game analysis narrative (similar to what the bot generates)
    long_text = "本局比赛表现出色！你的盖伦在对线期展现了强大的压制力，成功击杀对手三次并拿下一血。团战中你的进场时机把握得很好，多次利用大招斩杀残血敌人。建议继续保持这种进攻性的打法，同时注意保护好己方后排。总的来说，这是一场值得骄傲的胜利！"

    print(f"📝 Input text: {len(long_text)} chars")
    print(f"✅ TTS enabled: {adapter.tts_enabled}")
    print()

    try:
        audio_url = await adapter.synthesize_speech_to_url(text=long_text, emotion="激动")

        if audio_url:
            print("✅ SUCCESS!")
            print(f"🔊 Audio URL: {audio_url}")

            # Check file
            if audio_url.startswith("http://localhost"):
                file_path = audio_url.replace("http://localhost:3000/", "")
                if Path(file_path).exists():
                    file_size = Path(file_path).stat().st_size
                    print(f"📁 File: {file_path}")
                    print(f"📊 Size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")
        else:
            print("ℹ️  TTS returned None")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_long_tts())

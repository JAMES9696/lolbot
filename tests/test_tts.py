"""Quick test script for TTS functionality."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.adapters.tts_adapter import TTSAdapter


async def test_tts():
    """Test TTS synthesis with official example text."""
    print("🎤 Testing TTS Adapter...")
    print("-" * 50)

    adapter = TTSAdapter()

    # Test with official example text
    test_text = "豆包语音"
    print(f"📝 Input text: {test_text}")
    print(f"✅ TTS enabled: {adapter.tts_enabled}")
    print(f"⏱️  Timeout: {adapter.request_timeout_s}s")
    print()

    try:
        audio_url = await adapter.synthesize_speech_to_url(text=test_text, emotion="激动")

        if audio_url:
            print("✅ SUCCESS!")
            print(f"🔊 Audio URL: {audio_url}")

            # Check if file exists
            if audio_url.startswith("http://localhost"):
                file_path = audio_url.replace("http://localhost:3000/", "")
                if Path(file_path).exists():
                    file_size = Path(file_path).stat().st_size
                    print(f"📁 File saved: {file_path} ({file_size} bytes)")
        else:
            print("ℹ️  TTS returned None (feature disabled or failed)")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_tts())

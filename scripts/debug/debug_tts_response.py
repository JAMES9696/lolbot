"""Debug TTS API response to check for truncation."""

import asyncio
import json
import base64
import aiohttp
from pathlib import Path


async def debug_tts():
    """Debug TTS API response."""

    api_url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    api_key = "be15f04b-e7fc-4b51-a80b-b921e511b320"

    # Test with the same text
    test_text = "豆包语音"

    additions_config = json.dumps(
        {
            "disable_markdown_filter": True,
            "enable_language_detector": True,
            "enable_latex_tn": True,
            "disable_default_bit_rate": True,
            "max_length_to_filter_parenthesis": 0,
            "cache_config": {"text_type": 1, "use_cache": True},
        },
        ensure_ascii=False,
    )

    payload = {
        "req_params": {
            "text": test_text,
            "speaker": "zh_male_beijingxiaoye_emo_v2_mars_bigtts",
            "additions": additions_config,
            "audio_params": {"format": "mp3", "sample_rate": 24000},
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "X-Api-Resource-Id": "volc.service_type.10029",
        "Connection": "keep-alive",
    }

    print(f"🎤 Testing TTS API with text: {test_text}")
    print("-" * 60)

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload, headers=headers) as response:
            print(f"📡 Response Status: {response.status}")

            response_text = await response.text()
            print(f"📝 Raw Response Length: {len(response_text)} chars")
            print()

            # Split by newlines and analyze each JSON object
            lines = response_text.strip().split("\n")
            print(f"📊 Number of JSON objects: {len(lines)}")
            print()

            audio_chunks = []
            for idx, line in enumerate(lines, 1):
                if not line.strip():
                    continue

                try:
                    json_obj = json.loads(line)
                    print(f"[Object #{idx}]")
                    print(f"  code: {json_obj.get('code')}")
                    print(f"  message: {json_obj.get('message', '')}")

                    data = json_obj.get("data")
                    if data and isinstance(data, str):
                        print(f"  data (Base64): {len(data)} chars")
                        # Decode and collect
                        audio_bytes = base64.b64decode(data)
                        print(f"  audio_bytes: {len(audio_bytes)} bytes")
                        audio_chunks.append(audio_bytes)
                    else:
                        print(f"  data: {data}")

                    # Check for sentence metadata
                    sentence = json_obj.get("sentence")
                    if sentence:
                        print(f"  sentence.text: {sentence.get('text', '')}")

                    print()
                except json.JSONDecodeError as e:
                    print(f"[Object #{idx}] JSON Error: {e}")
                    print()

            # Combine all audio chunks
            if audio_chunks:
                total_audio = b"".join(audio_chunks)
                print(f"✅ Total audio size: {len(total_audio)} bytes")
                print(f"📦 Number of chunks: {len(audio_chunks)}")

                # Save complete audio
                output_path = Path("debug_complete_audio.mp3")
                output_path.write_bytes(total_audio)
                print(f"💾 Saved to: {output_path}")

                # Also save first chunk only (what we were doing before)
                if len(audio_chunks) > 0:
                    first_chunk_path = Path("debug_first_chunk_only.mp3")
                    first_chunk_path.write_bytes(audio_chunks[0])
                    print(f"💾 First chunk only saved to: {first_chunk_path}")
            else:
                print("❌ No audio data found!")


if __name__ == "__main__":
    asyncio.run(debug_tts())

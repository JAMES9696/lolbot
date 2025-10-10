# Discord 语音播报部署指南

本项目的语音播报依赖 Discord 语音栈与 FFmpeg。请按以下步骤完成系统依赖与 Python 依赖配置。

## 系统依赖（必需）

- ffmpeg（音频解码/重采样）
- libopus（语音编码）
- libsodium（加密）

示例安装命令：

- macOS (Homebrew)
  - `brew install ffmpeg opus libsodium`

- Ubuntu/Debian (APT)
  - `sudo apt-get update && sudo apt-get install -y ffmpeg libopus0 libopus-dev libsodium23 libsodium-dev`

- Alpine (APK)
  - `apk add --no-cache ffmpeg opus opus-dev libsodium libsodium-dev`

安装完成后，确保 `ffmpeg` 在 PATH 中可用：`ffmpeg -version`。

## Python 依赖

`requirements.txt` 已包含：

- `discord.py` — Discord 机器人 SDK
- `PyNaCl` — Discord 语音所需加密支持（必须）

安装：`pip install -r requirements.txt`

## 应用配置

`.env` 示例（与 `src/config/settings.py` 一致）：

```
FEATURE_VOICE_ENABLED=true
AUDIO_STORAGE_PATH=static/audio
AUDIO_BASE_URL=http://localhost:3000/static/audio

# TTS（Doubao/Volcengine）
TTS_API_URL=https://openspeech.bytedance.com/api/v1/tts
TTS_API_KEY=ve-xxxxxxxx
TTS_VOICE_ID=doubao_xxx
```

## 使用说明

- 语音播放入口：`DiscordAdapter.play_tts_in_voice_channel(...)`
- 队列播报（单公会单路）：`VoiceBroadcastService.enqueue(...)`
- 动态加入用户所在频道：`DiscordAdapter.play_tts_to_user_channel(...)`

## 推荐设置

- 音量：`volume=0.4~0.6`
- 最大播报时长：`max_seconds=60~90`
- 音量标准化：`normalize=True`（等效 ffmpeg `-filter:a loudnorm`）

## 故障排查

- 报错 `Opus not loaded`：确认已安装 `libopus` 并可被系统加载。
- 播放无声/卡死：检查 `ffmpeg` 是否可用；`audio_url` 是否可直接访问；服务器出站网络是否正常。
- 语音连接失败：确认机器人在目标语音频道具备 Connect/Speak 权限。

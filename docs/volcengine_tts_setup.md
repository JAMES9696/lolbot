# Volcengine 大模型语音合成（TTS）接入指南

本项目当前通过环境变量读取 TTS 配置（见 `src/config/settings.py:57` 起）。本文档基于火山引擎语音技术的「大模型语音合成 API」整理最小可用接入步骤，并与仓库现有 `.env.example` 对齐。

参考官方文档：大模型语音合成 API（语音技术）．请以官方页面为准。https://www.volcengine.com/docs/6561/1257584

## 准备工作
- 火山引擎账号与开通「语音技术 / 语音合成（大模型）」
- 在控制台创建应用，获取以下凭据：
  - API Key（用于请求鉴权）
  - App ID（有的接口需要，放在请求体中）
- 了解可用发音人/音色 ID（Voice/Speaker），与采样率、编码格式等参数

## 环境变量映射（与本仓库保持一致）
- `TTS_API_URL`：TTS 服务地址
  - HTTP 同步（示例）：`https://openspeech.bytedance.com/api/v1/tts`
  - WebSocket 流式（示例）：`wss://openspeech.bytedance.com/api/v1/tts/ws`
- `TTS_API_KEY`：从火山引擎控制台获取的 API Key（放入请求头）
- `TTS_VOICE_ID`：发音人/音色标识（如官方文档中的示例 ID）
- `FEATURE_VOICE_ENABLED`：设为 `true` 以在应用层启用语音能力（代码集成进度视具体模块而定）

> 说明：本项目当前未直接使用 AK/SK + 签名的鉴权方式，统一采用 API Key 头部鉴权；如后续需要 SigV4 鉴权，再扩展对应配置。

## 快速自检（HTTP 同步合成）
准备 `.env`（可从 `.env.example` 复制并填写）：

```
TTS_API_URL=https://openspeech.bytedance.com/api/v1/tts
TTS_API_KEY=ve-xxxxxxxxxxxxxxxxxxxxxxxx
TTS_VOICE_ID=doubao_xxx
FEATURE_VOICE_ENABLED=true
```

使用 curl 进行最小化验证（生成 MP3 文件）：

```
curl -X POST "$TTS_API_URL" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $TTS_API_KEY" \
  -d '{
        "app": {"appid": "your_volc_app_id"},
        "audio": {"voice_type": "'"$TTS_VOICE_ID"'", "format": "mp3"},
        "request": {"text": "你好，召唤师！欢迎来到英雄联盟。", "lang": "zh"}
      }' \
  --output out.mp3
```

常见变体：
- WebSocket 流式：将 `TTS_API_URL` 换为 `wss://.../tts/ws`，数据按帧返回；适合长文本与边播边下。
- 音色选择：有的文档字段名为 `voice_type`、有的为 `speaker` 或 `voice`；以官方文档为准。

## 与项目的集成位点
- 配置加载：`src/config/settings.py:57` 起（`tts_api_key`、`tts_api_url`、`tts_voice_id`、`feature_voice_enabled`）
- 建议在 `src/adapters/` 下新增 `volc_tts_adapter.py`（若尚未实现），实现：
  - `synthesize(text: str, voice_id: str, format: str) -> bytes`
  - 通过 `X-Api-Key: <TTS_API_KEY>` 调用 `TTS_API_URL`
  - 允许 `mp3/wav/pcm` 等格式
- 运行时开关：用 `FEATURE_VOICE_ENABLED` 保护调用路径（避免在未配置时触发请求）

## 安全与合规
- `.env` 已在 `.gitignore`；严禁提交真实密钥。
- 若曾在聊天或日志中暴露过密钥或 Token，请立即在控制台重置。
- 最小权限与密钥轮换：为 TTS 单独创建应用与 API Key，定期轮换。

## 故障排查
- 401/403：检查 `X-Api-Key` 是否正确、是否绑定到对应产品；确认 `appid` 是否与 Key 对应。
- 404/405：确认 URL 路径（HTTP vs WS）、是否使用了正确的地域/集群。
- 声音异常/乱码：检查 `format` 与客户端播放器是否匹配（`mp3` 最兼容）。
- 限流/熔断：遵循官方速率限制，必要时增加重试与退避策略。

## 后续扩展（可选）
- 新增 `tts_audio_format`、`tts_sample_rate` 等可配置项（保持 KISS，在确需时再引入）。
- 抽象 `ITTSAdapter` 接口，允许替换为其它 TTS 提供商（遵循依赖倒置）。

# Voice & UX Optimization Plan

## 📋 现状分析

### 当前语音实现 (src/adapters/discord_adapter.py:1686-1769)

**工作流程**:
```
TTS API → Base64 解码 → 保存磁盘 (static/audio/) →
生成 HTTP URL → FFmpegPCMAudio(url) → Discord 播放
```

**性能瓶颈**:
1. **磁盘 I/O**: 两次操作（写入 + 读取）
2. **延迟**: ~200-500ms 额外延迟
3. **存储管理**: 需要文件清理机制

---

## 🚀 优化方案

### 1. 流式音频处理 (Streaming Audio)

#### 1.1 架构改进

**优化后的工作流程**:
```
TTS API → Base64 解码 → BytesIO (内存) →
FFmpegPCMAudio(pipe=True) → Discord 播放
```

#### 1.2 实现方案

```python
# src/adapters/discord_adapter.py

import io
from discord import FFmpegPCMAudio, PCMVolumeTransformer

async def play_tts_streaming(
    self,
    *,
    guild_id: int,
    voice_channel_id: int,
    audio_bytes: bytes,  # 直接传递字节，而非 URL
    volume: float = 0.5,
    normalize: bool = False,
    max_seconds: int | None = None,
) -> bool:
    """Play TTS audio from in-memory bytes (streaming mode).

    Performance Benefits:
    - Eliminates disk I/O (no file write/read)
    - Reduces latency by ~200-500ms
    - No file cleanup required

    Args:
        audio_bytes: Complete MP3 audio data in memory

    Implementation:
        Uses BytesIO to create a file-like object that FFmpeg
        can read directly from memory via pipe.
    """
    try:
        # 1. Connect to voice channel (same as before)
        guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)
        channel = guild.get_channel(voice_channel_id) or await self.bot.fetch_channel(voice_channel_id)

        if not isinstance(channel, discord.VoiceChannel):
            logger.error("Target channel is not a voice channel")
            return False

        vc = discord.utils.get(self.bot.voice_clients, guild=guild)
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
        else:
            vc = await channel.connect()

        # 2. Create in-memory file-like object
        audio_stream = io.BytesIO(audio_bytes)

        # 3. FFmpeg options
        ff_opts = "-vn"  # No video
        if normalize:
            ff_opts += " -filter:a loudnorm"
        if isinstance(max_seconds, int) and max_seconds > 0:
            ff_opts += f" -t {max_seconds}"

        # 4. Create audio source with pipe=True
        # FFmpeg will read from the BytesIO stream
        source = FFmpegPCMAudio(
            audio_stream,
            pipe=True,  # Critical: tells FFmpeg to read from stdin
            options=ff_opts,
        )
        player = PCMVolumeTransformer(source, volume=volume)

        # 5. Play and wait
        vc.play(player)
        while vc.is_playing():
            await asyncio.sleep(1)

        await vc.disconnect()
        return True

    except Exception as e:
        logger.error(f"Streaming voice playback error: {e}", exc_info=True)
        return False
```

#### 1.3 集成修改

**修改 TTS Adapter** (src/adapters/tts_adapter.py):

```python
async def synthesize_speech_to_bytes(
    self, text: str, emotion: str | None = None
) -> bytes | None:
    """Direct bytes variant for streaming playback.

    Returns audio bytes directly without saving to disk.
    Used when FEATURE_VOICE_STREAMING=true.
    """
    if not self.tts_enabled:
        return None

    try:
        voice_profile = self._map_emotion_to_voice(emotion)

        # Call Volcengine TTS (reuse existing logic)
        audio_bytes = await asyncio.wait_for(
            self._call_volcengine_tts(text=text, voice_profile=voice_profile),
            timeout=self.request_timeout_s,
        )

        logger.info(
            f"TTS streaming synthesis (size: {len(audio_bytes)} bytes, "
            f"chunks collected, no disk I/O)"
        )
        return audio_bytes

    except Exception as e:
        logger.error(f"TTS streaming error: {e}")
        return None
```

**修改 VoiceJob** (src/core/services/voice_broadcast_service.py):

```python
@dataclass(slots=True)
class VoiceJob:
    guild_id: int
    channel_id: int
    # Support both URL (legacy) and bytes (streaming)
    audio_url: str | None = None
    audio_bytes: bytes | None = None
    volume: float = 0.5
    normalize: bool = False
    max_seconds: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate that either URL or bytes is provided."""
        if not self.audio_url and not self.audio_bytes:
            raise ValueError("Either audio_url or audio_bytes must be provided")


# Update worker to handle both modes
async def _worker(self, guild_id: int) -> None:
    q = self._get_queue(guild_id)
    while True:
        try:
            job = await q.get()
        except Exception:
            break

        try:
            # Choose playback method based on job type
            if job.audio_bytes:
                # Streaming mode (new)
                ok = await self._adapter.play_tts_streaming(
                    guild_id=job.guild_id,
                    voice_channel_id=job.channel_id,
                    audio_bytes=job.audio_bytes,
                    volume=job.volume,
                    normalize=job.normalize,
                    max_seconds=job.max_seconds,
                )
            else:
                # URL mode (legacy)
                ok = await self._adapter.play_tts_in_voice_channel(
                    guild_id=job.guild_id,
                    voice_channel_id=job.channel_id,
                    audio_url=job.audio_url,
                    volume=job.volume,
                    normalize=job.normalize,
                    max_seconds=job.max_seconds,
                )

            if not ok:
                logger.warning("Voice job failed guild=%s", guild_id)
            else:
                logger.info("Voice job done guild=%s", guild_id)

        except Exception:
            logger.exception("Voice worker error guild=%s", guild_id)
        finally:
            try:
                q.task_done()
            except Exception:
                pass

        if q.empty():
            break
```

#### 1.4 配置与回退策略

**环境变量** (.env):
```bash
# Voice streaming optimization
FEATURE_VOICE_STREAMING=true  # Enable in-memory streaming (recommended)
FEATURE_VOICE_STREAMING=false # Fallback to disk-based playback
```

**渐进式部署**:
1. Phase 1: 实现 streaming 方法，保留 URL 方法
2. Phase 2: 在开发环境测试 streaming
3. Phase 3: 在生产环境启用（通过 feature flag）
4. Phase 4: 移除 URL 方法（可选）

---

### 2. 图标化信息 (Icon Integration)

#### 2.1 Discord 自定义表情方案

**参考项目**:
- Kindred Bot: https://github.com/Kindred-bot
- GangplankBot: 表情符号展示符文/英雄

**实现步骤**:

1. **准备图标资源**:
   ```
   assets/
   ├── champions/      # 英雄头像 (64x64 PNG)
   │   ├── aatrox.png
   │   ├── ahri.png
   │   └── ...
   ├── runes/          # 符文图标 (32x32 PNG)
   │   ├── electrocute.png
   │   ├── conqueror.png
   │   └── ...
   └── ranks/          # 段位徽章 (48x48 PNG)
       ├── iron.png
       ├── bronze.png
       └── ...
   ```

2. **上传到 Discord 服务器**:
   ```python
   # scripts/upload_emojis.py

   import asyncio
   import discord
   from pathlib import Path

   async def upload_emojis_to_guild(bot: discord.Client, guild_id: int):
       """Upload all game assets as custom emojis."""
       guild = bot.get_guild(guild_id)

       # Upload champions
       champions_dir = Path("assets/champions")
       for icon_path in champions_dir.glob("*.png"):
           champion_name = icon_path.stem.lower()
           emoji_name = f"lol_{champion_name}"

           # Check if emoji exists
           existing = discord.utils.get(guild.emojis, name=emoji_name)
           if existing:
               print(f"✓ {emoji_name} already exists")
               continue

           # Upload
           with open(icon_path, 'rb') as f:
               image = f.read()
           emoji = await guild.create_custom_emoji(
               name=emoji_name,
               image=image,
               reason="LoL Bot champion icons"
           )
           print(f"✓ Uploaded {emoji_name}: {emoji}")

   # Similar for runes and ranks
   ```

3. **在消息中使用表情**:
   ```python
   # src/core/views/analysis_view.py

   def _get_champion_emoji(self, champion_name: str, guild: discord.Guild) -> str:
       """Get custom emoji for champion, fallback to text."""
       emoji_name = f"lol_{champion_name.lower().replace(' ', '_')}"
       emoji = discord.utils.get(guild.emojis, name=emoji_name)

       if emoji:
           return str(emoji)  # Returns <:lol_aatrox:123456789>
       else:
           return champion_name  # Fallback to text

   def render_champion_summary(self, champion: str, guild: discord.Guild) -> str:
       """Render champion with icon."""
       icon = self._get_champion_emoji(champion, guild)
       return f"{icon} **{champion}**"
   ```

4. **Embed 增强示例**:
   ```python
   # Before (text only)
   embed.add_field(
       name="英雄",
       value="盖伦",
       inline=True
   )

   # After (with emoji)
   embed.add_field(
       name="英雄",
       value=f"{champion_emoji} **盖伦**",
       inline=True
   )

   # Rune example
   embed.add_field(
       name="主系符文",
       value=f"{conqueror_emoji} 征服者 → {triumph_emoji} 凯旋",
       inline=False
   )
   ```

#### 2.2 表情符号限制与策略

**Discord 限制**:
- 普通服务器: 50 个静态 + 50 个动态表情
- Boost Level 1: 100 个静态 + 100 个动态
- Boost Level 2: 150 个静态 + 150 个动态
- Boost Level 3: 250 个静态 + 250 个动态

**优先级策略**:
1. **高优先级** (50个槽位):
   - Top 30 热门英雄
   - Top 10 主流符文
   - 5 个段位徽章 (Iron → Challenger)
   - 5 个状态图标 (胜利/失败/MVP等)

2. **中优先级** (50个槽位):
   - 其他常用英雄
   - 次级符文树

3. **低优先级** (按需上传):
   - 稀有英雄
   - 老旧符文

**动态加载策略**:
```python
# Emoji cache with LRU eviction
from functools import lru_cache

@lru_cache(maxsize=200)
def get_champion_emoji_cached(champion_name: str, guild_id: int) -> str:
    """Cached emoji lookup to reduce API calls."""
    # ... lookup logic
```

---

## 📊 性能对比

### 语音播放延迟

| 方案 | 步骤 | 延迟 (ms) | 备注 |
|-----|------|----------|------|
| **当前 (URL)** | TTS → 保存磁盘 → 读取 → 播放 | ~500-800 | 2x 磁盘 I/O |
| **优化 (Streaming)** | TTS → BytesIO → 播放 | ~200-300 | 纯内存操作 |

**预期提升**: ~60% 延迟减少

---

## 🎯 实施优先级

### Phase 1: 流式音频 (High Priority)
- ✅ 立即可实现
- ✅ 显著性能提升
- ✅ 无需额外资源

**预估工作量**: 2-4 小时
- [ ] 实现 `play_tts_streaming()` 方法
- [ ] 修改 `TTS_adapter.synthesize_speech_to_bytes()`
- [ ] 更新 `VoiceJob` 数据结构
- [ ] 添加 feature flag
- [ ] 测试验证

### Phase 2: 图标化信息 (Medium Priority)
- ⚠️ 需要准备资源（图标）
- ⚠️ 受限于服务器 Boost 等级
- ✅ 提升视觉体验

**预估工作量**: 4-8 小时
- [ ] 收集/制作图标资源
- [ ] 编写上传脚本
- [ ] 修改 view 层集成 emoji
- [ ] 处理回退逻辑
- [ ] 文档更新

---

## 🔧 技术注意事项

### 1. FFmpeg Pipe 模式注意点

```python
# ✅ CORRECT: BytesIO for in-memory streaming
audio_stream = io.BytesIO(audio_bytes)
source = FFmpegPCMAudio(audio_stream, pipe=True)

# ❌ WRONG: File path with pipe=True
source = FFmpegPCMAudio("/path/to/file.mp3", pipe=True)  # Will fail
```

### 2. 内存管理

```python
# Large audio files (>10MB) consideration
if len(audio_bytes) > 10 * 1024 * 1024:  # 10MB
    logger.warning("Large audio file, consider URL fallback")
    # Use disk-based method for very large files
```

### 3. 错误处理

```python
# Graceful degradation
try:
    # Try streaming first
    result = await play_tts_streaming(audio_bytes=audio_bytes)
except Exception as e:
    logger.warning(f"Streaming failed, falling back to URL: {e}")
    # Fallback to disk-based method
    audio_url = await upload_to_cdn(audio_bytes)
    result = await play_tts_in_voice_channel(audio_url=audio_url)
```

---

## 📚 参考资源

### 开源项目
- **Kindred Bot**: https://github.com/Kindred-bot
  - Discord.py 架构参考
  - Embed 消息格式化

- **GangplankBot**: 表情符号集成示例
  - 自定义 emoji 管理
  - 视觉优化策略

### Discord.py 文档
- Voice: https://discordpy.readthedocs.io/en/stable/api.html#voice-related
- FFmpegPCMAudio: https://discordpy.readthedocs.io/en/stable/api.html#discord.FFmpegPCMAudio
- Custom Emojis: https://discordpy.readthedocs.io/en/stable/api.html#discord.Guild.create_custom_emoji

### FFmpeg 文档
- Pipe input: https://ffmpeg.org/ffmpeg-protocols.html#pipe
- Audio filters: https://ffmpeg.org/ffmpeg-filters.html#Audio-Filters

---

## ✅ 测试清单

### 流式音频测试
- [ ] 短文本 (<50 字) 播放正常
- [ ] 长文本 (>200 字) 播放正常
- [ ] 多个连续播放不崩溃
- [ ] 内存使用稳定 (无泄漏)
- [ ] 延迟确实减少
- [ ] 错误时回退到 URL 模式

### 图标测试
- [ ] 表情符号正确显示
- [ ] 未上传的英雄回退到文本
- [ ] 不同服务器独立管理表情
- [ ] 表情符号更新/删除正常

---

## 📝 后续优化方向

1. **WebSocket Streaming**: 实时 TTS 流式传输（豆包 API 支持的话）
2. **语音指令**: 支持语音频道内的语音指令控制
3. **动态表情**: 使用 GIF 表情显示动态效果
4. **Thumbnail 集成**: 在 Embed 中显示英雄头像大图
5. **数据可视化**: 生成性能雷达图/趋势图

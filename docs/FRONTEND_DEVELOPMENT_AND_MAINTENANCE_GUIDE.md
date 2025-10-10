# Frontend Development and Maintenance Guide

**Project:** Project Chimera - Discord LOL Analysis Bot
**Component:** CLI 1 (Frontend - Discord UI Layer)
**Version:** V2.4 (Comprehensive V2.0-V2.3 Coverage)
**Last Updated:** 2025-10-07
**Target Audience:** Frontend Developers, New Contributors, System Maintainers

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Organization](#code-organization)
3. [Key Components Deep Dive](#key-components-deep-dive)
4. [Development Workflow](#development-workflow)
5. [Testing Guidelines](#testing-guidelines)
6. [Deployment Procedures](#deployment-procedures)
7. [Maintenance Tasks](#maintenance-tasks)
8. [Adding New Features](#adding-new-features)
9. [Critical Constraints and Best Practices](#critical-constraints-and-best-practices)
10. [Troubleshooting Guide](#troubleshooting-guide)
11. [Appendix](#appendix)

---

## Architecture Overview

### Hexagonal Architecture Context

Project Chimera follows **Hexagonal Architecture** (Ports and Adapters) with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     CLI 1: Frontend                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Discord Interaction Layer (discord_adapter.py)       │  │
│  │  - Slash command registration                         │  │
│  │  - Interaction handling                               │  │
│  │  - Defer reply mechanism                              │  │
│  └──────────────────┬────────────────────────────────────┘  │
│                     │ Uses                                  │
│                     ▼                                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  View Components (src/core/views/)                    │  │
│  │  - paginated_team_view.py (V2.0)                      │  │
│  │  - prescriptive_view.py (V2.1)                        │  │
│  │  - settings_modal.py (V2.2)                           │  │
│  │  - fallback_analysis_view.py (V2.3)                   │  │
│  └──────────────────┬────────────────────────────────────┘  │
│                     │ Consumes                              │
│                     ▼                                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Data Contracts (src/contracts/)                      │  │
│  │  - v2_team_analysis.py                                │  │
│  │  - discord_interactions.py                            │  │
│  │  - user_preferences.py                                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Webhook Delivery (async)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     CLI 2: Backend                          │
│  - Team analysis pipeline (team_tasks.py)                   │
│  - LLM orchestration (gemini_adapter.py)                    │
│  - Riot API integration (riot_api_enhanced.py)              │
│  - Webhook publishing (discord_webhook.py)                  │
└─────────────────────────────────────────────────────────────┘
```

### Responsibilities of CLI 1 (Frontend)

**Primary Responsibilities:**
1. **User Interface:** All Discord Embeds, Buttons, Modals
2. **Interaction Handling:** Processing slash commands and button clicks
3. **Defer Reply Management:** Preventing Discord interaction timeouts
4. **Data Transformation:** Converting backend contracts to Discord UI components
5. **User Feedback:** A/B testing buttons and feedback collection

**Non-Responsibilities (Handled by CLI 2):**
- Riot API calls
- LLM analysis logic
- Database operations (except preference retrieval)
- Complex business logic

**Key Principle:**
> **CLI 1 is a pure presentation layer.** It should never contain game logic, scoring algorithms, or data fetching beyond user preferences.

---

### Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **discord.py** | 2.3+ | Discord bot framework |
| **Python** | 3.11+ | Programming language |
| **Pydantic** | 2.0+ | Data validation and contracts |
| **httpx** | 0.24+ | Async HTTP client (webhook delivery) |
| **asyncio** | Built-in | Async/await patterns |

**Why discord.py?**
- Official Discord API wrapper with full slash command support
- Excellent async/await integration
- Active community and documentation
- Type hints and IDE support

---

## Code Organization

### Directory Structure

```
src/
├── adapters/
│   └── discord_adapter.py          # Main Discord bot adapter (CLI 1 entry point)
├── contracts/
│   ├── v2_team_analysis.py         # V2 team analysis data contract
│   ├── discord_interactions.py     # Webhook delivery contracts
│   └── user_preferences.py         # V2.2 user settings contracts
├── core/
│   └── views/
│       ├── paginated_team_view.py  # V2.0: Pagination UI
│       ├── prescriptive_view.py    # V2.1: Collapsible advice
│       ├── settings_modal.py       # V2.2: User preference modal
│       └── fallback_analysis_view.py # V2.3: Graceful degradation
├── config/
│   └── settings.py                 # Feature flags and environment config
└── main.py                         # Application entry point
```

### File Responsibilities

#### `src/adapters/discord_adapter.py`

**Purpose:** Main Discord bot adapter, entry point for all Discord interactions

**Key Responsibilities:**
- Slash command registration (`/jiangli`, `/settings`, `/help`)
- Command handler routing
- Defer reply mechanism implementation
- Error handling and user-facing error messages
- Integration with webhook delivery (via CLI 2)

**Critical Methods:**
- `_handle_jiangli_command()` - Main analysis command (V2.0)
- `_handle_settings_command()` - User preference configuration (V2.2)
- `_handle_help_command()` - Help documentation (V2.3)
- `_send_team_analysis()` - Render analysis results (V2.0-V2.3)

**Code Reference:**
- Lines 214-223: Command registration
- Lines 424-445: `/jiangli` command with defer reply
- Lines 638-757: `/settings` command with modal handling
- Lines 768-870: `/help` command with compliance text

---

#### `src/core/views/paginated_team_view.py`

**Purpose:** V2.0 paginated team analysis UI with V2.3 mode-aware enhancements

**Key Responsibilities:**
- Multi-page navigation (Summary + Details)
- Feedback buttons (👍👎⭐) for A/B testing
- Mode-aware emoji and label rendering (V2.3)
- Conditional metric display based on game mode (V2.3)

**Critical Methods:**
- `__init__()` - Initialize with report and match_id
- `_get_mode_emoji_and_label()` - Map game mode to emoji (V2.3)
- `_should_show_vision_control()` - Filter Vision metric in ARAM (V2.3)
- `_create_summary_page()` - Page 1: Team overview
- `_create_team_details_page()` - Page 2: All 5 players
- `previous_page()` / `next_page()` - Pagination handlers

**Code Reference:**
- Lines 20-115: View initialization and feedback buttons
- Lines 53-68: Mode emoji mapping (V2.3)
- Lines 70-79: Vision Control filtering (V2.3)
- Lines 166-215: Summary page with mode emoji
- Lines 217-293: Details page with conditional rendering

**V2.3 Enhancements:**
- Mode emoji in title (🏞️🏞, ❄️, ⚔️)
- Vision Control hidden in ARAM mode
- Game mode label in description

---

#### `src/core/views/prescriptive_view.py`

**Purpose:** V2.1 collapsible advice UI with three-dimensional suggestions

**Key Responsibilities:**
- Render "📋 实操建议" button on details page
- Provide three collapsible advice sections:
  1. 📊 宏观决策建议 (Macro decisions)
  2. 🎯 微操技巧建议 (Micro mechanics)
  3. 💭 心态调整建议 (Mental adjustments)
- Display timeline evidence when enabled

**Critical Methods:**
- `create_advice_button()` - Create initial button to trigger expansion
- `create_collapsible_sections()` - Generate three advice panels
- `_create_section_embed()` - Individual advice section UI

**Code Reference:**
- Lines 20-60: Button creation
- Lines 62-148: Collapsible section logic
- Lines 110-120: Timeline evidence rendering

**Timeline Evidence Format:**
```python
# Example from narrative_with_evidence field:
"• 15:32 时你在中路 gank 后应该立即在河道插眼..."
"• 你在 22:10 缺少对大龙的视野控制..."
```

---

#### `src/core/views/settings_modal.py`

**Purpose:** V2.2 user preference configuration modal

**Key Responsibilities:**
- Display 4 input fields for user preferences
- Validate input values (role, tone, detail level, timeline)
- Generate `UserProfileUpdateRequest` contract
- Provide clear error messages for invalid inputs

**Critical Methods:**
- `__init__()` - Set up 4 TextInput fields
- `on_submit()` - Handle modal submission
- `_parse_inputs()` - Convert strings to contract fields
- `_validate_inputs()` - Check input validity

**Code Reference:**
- Lines 10-42: TextInput field definitions
- Lines 44-95: Submission and validation logic

**Validation Rules:**
```python
main_role: ["top", "jungle", "mid", "bot", "support", "fill"]
analysis_tone: ["competitive", "casual", "balanced"]
advice_detail_level: ["concise", "detailed"]
show_timeline: ["yes", "no"]
```

---

#### `src/core/views/fallback_analysis_view.py`

**Purpose:** V2.3 graceful degradation for unsupported game modes

**Key Responsibilities:**
- Display basic match data (KDA, gold, damage) for unknown modes
- Provide positive "功能开发中" messaging
- List currently supported modes with ✅ indicators
- Avoid panic-inducing error language

**Critical Methods:**
- `create_fallback_embed()` - Create positive fallback UI
- `create_error_fallback_embed()` - Handle data fetch failures

**Code Reference:**
- Lines 20-50: FallbackMatchData contract
- Lines 64-130: Fallback embed creation
- Lines 133-187: Error fallback embed

**Design Philosophy:**
> "Never show a failure state. Always provide value, even if it's just basic data."

---

#### `src/contracts/v2_team_analysis.py`

**Purpose:** Data contract between CLI 2 (backend) and CLI 1 (frontend)

**Key Fields:**
- `match_id: str` - Riot match ID
- `match_result: Literal["victory", "defeat"]` - Game outcome
- `game_mode: Literal["summoners_rift", "aram", "arena", "unknown"]` - V2.3 mode identifier
- `target_player_name: str` - Player who invoked command
- `team_analysis: list[V2PlayerAnalysisResult]` - All 5 players' data
- `team_summary_insight: str` - Team-level narrative
- `ab_cohort: str` - A/B testing cohort
- `variant_id: str` - V2.1 narrative variant
- `processing_duration_ms: float` - Backend timing

**V2.3 Addition:**
```python
game_mode: Literal["summoners_rift", "aram", "arena", "unknown"] = Field(
    default="summoners_rift",
    description=(
        "Game mode identifier for mode-aware UI rendering. "
        "'summoners_rift': 5v5 Ranked/Normal, "
        "'aram': ARAM (Howling Abyss), "
        "'arena': 2v2v2v2 Arena mode, "
        "'unknown': Unsupported/future modes (fallback)"
    ),
)
```

**Code Reference:**
- Lines 130-150: V2TeamAnalysisReport structure

---

#### `src/contracts/discord_interactions.py`

**Purpose:** Webhook delivery contracts (CLI 2 → Discord)

**Key Contracts:**
- `WebhookDeliveryRequest` - Payload for webhook PATCH
- `DiscordEmbedDict` - Serializable Discord Embed
- `DiscordViewDict` - Serializable Discord UI View

**Code Reference:**
- Lines 126-146: WebhookDeliveryRequest definition

**Webhook Delivery Flow:**
```
1. User invokes /jiangli
2. CLI 1 defers reply: interaction.response.defer()
3. CLI 1 saves interaction_token
4. CLI 2 performs analysis (5-30s)
5. CLI 2 calls webhook: POST /webhooks/{application_id}/{interaction_token}
6. Discord updates original message with final result
```

---

#### `src/config/settings.py`

**Purpose:** Feature flags and environment configuration

**Key Feature Flags:**
```python
# V2.1: Prescriptive analysis
feature_v21_prescriptive_enabled: bool = Field(default=False)

# V2.2: User personalization
feature_v22_personalization_enabled: bool = Field(default=False)
```

**Usage in Code:**
```python
from src.config.settings import get_settings

settings = get_settings()
if settings.feature_v21_prescriptive_enabled:
    # Show "📋 实操建议" button
    pass
```

---

## Key Components Deep Dive

### Component 1: Defer Reply Mechanism (Critical)

**Problem:** Discord interactions expire after 3 seconds if not acknowledged.

**Solution:** Use `interaction.response.defer()` immediately, then send final result via webhook.

**Implementation:**

```python
# src/adapters/discord_adapter.py:424-445

async def _handle_jiangli_command(self, interaction: discord.Interaction) -> None:
    """Handle the /jiangli slash command with defer reply pattern."""

    # CRITICAL: Defer reply within 3 seconds to prevent timeout
    await interaction.response.defer(thinking=True)
    # "⏳ 正在分析..." placeholder now visible to user

    # Save interaction token for webhook delivery
    interaction_token = interaction.token
    application_id = self.bot.application_id

    # Trigger backend analysis (async, takes 5-30 seconds)
    # Backend will use webhook to update message when done
    await self._trigger_backend_analysis(
        user_id=str(interaction.user.id),
        interaction_token=interaction_token,
        application_id=application_id,
    )

    # Do NOT wait for result here - webhook will handle it
```

**Key Points:**
- `defer(thinking=True)` shows "Bot is thinking..." message
- Never block for more than 3 seconds in command handler
- Webhook delivery is asynchronous and independent

**Testing:**
```python
# Verify defer reply latency
start_time = time.time()
await interaction.response.defer()
latency = time.time() - start_time
assert latency < 1.0, "Defer reply took too long!"
```

---

### Component 2: Mode-Aware Rendering (V2.3)

**Problem:** Different game modes have different relevant metrics (e.g., Vision in SR vs. ARAM).

**Solution:** Conditional rendering based on `game_mode` field.

**Implementation:**

```python
# src/core/views/paginated_team_view.py:70-79

def _should_show_vision_control(self) -> bool:
    """Determine if vision control metric should be displayed."""
    # Vision control not meaningful in ARAM (single lane, no wards)
    return self.report.game_mode not in ["aram", "unknown"]

# Usage in player detail rendering (lines 255-272)
for player in sorted_players:
    show_strength = self._should_show_vision_control() or player.top_strength_dimension != "Vision"
    show_weakness = self._should_show_vision_control() or player.top_weakness_dimension != "Vision"

    if show_strength:
        field_value += f"✨ 优势: {player.top_strength_dimension}..."
    if show_weakness:
        field_value += f"⚠️ 劣势: {player.top_weakness_dimension}..."
```

**Mode Emoji Mapping:**
```python
# src/core/views/paginated_team_view.py:53-68

def _get_mode_emoji_and_label(self) -> tuple[str, str]:
    mode_map = {
        "aram": ("❄️", "ARAM（极地大乱斗）"),
        "arena": ("⚔️", "Arena（斗魂竞技场）"),
        "summoners_rift": ("🏞️", "召唤师峡谷"),
        "unknown": ("❓", "未知模式"),
    }
    return mode_map.get(self.report.game_mode, ("🎮", "游戏模式"))
```

**Testing:**
```python
# Test ARAM mode filtering
report = V2TeamAnalysisReport(game_mode="aram", ...)
view = PaginatedTeamAnalysisView(report, match_id="test")
assert not view._should_show_vision_control()

# Test SR mode (Vision shown)
report_sr = V2TeamAnalysisReport(game_mode="summoners_rift", ...)
view_sr = PaginatedTeamAnalysisView(report_sr, match_id="test")
assert view_sr._should_show_vision_control()
```

---

### Component 3: Modal Handling (V2.2)

**Problem:** Discord Modals require special handling and don't support `.wait()` pattern.

**Solution:** Monkey-patch modal's `on_submit` callback to add persistence logic.

**Implementation:**

```python
# src/adapters/discord_adapter.py:638-757

async def _handle_settings_command(self, interaction: discord.Interaction) -> None:
    from src.core.views.settings_modal import UserSettingsModal

    user_id = str(interaction.user.id)

    # Create modal instance
    settings_modal = UserSettingsModal()

    # Save original on_submit method
    original_on_submit = settings_modal.on_submit

    # Define new on_submit with persistence logic
    async def on_submit_with_persistence(modal_interaction: discord.Interaction) -> None:
        # Call original validation and parsing
        await original_on_submit(modal_interaction)

        # If validation passed, persist to database
        if hasattr(settings_modal, "update_request"):
            update_request = settings_modal.update_request

            # TODO(V2.2-CLI2): Integrate with UserProfileService
            # await profile_service.update_profile(user_id, update_request)

            logger.info(f"User {user_id} preferences: {update_request.model_dump()}")

            # Send success message
            await modal_interaction.followup.send(
                f"✅ 设置已保存！后续分析将应用你的偏好。",
                ephemeral=True
            )

    # Monkey-patch the modal's on_submit
    settings_modal.on_submit = on_submit_with_persistence

    # Send modal (opens on user's screen)
    await interaction.response.send_modal(settings_modal)
```

**Why Monkey-Patch?**
- Discord.py modals handle their own submission lifecycle
- Can't use `.wait()` pattern (modal not a message component)
- Monkey-patching preserves modal's validation logic

**Alternative Approaches (Not Recommended):**
- ❌ Subclassing `UserSettingsModal` - Breaks single responsibility
- ❌ Passing callbacks to `__init__` - Complicates modal interface
- ✅ Monkey-patching `on_submit` - Clean, preserves validation

---

### Component 4: Collapsible Advice Sections (V2.1)

**Problem:** 15+ bullet points of advice overwhelm users; need progressive disclosure.

**Solution:** Three collapsible sections (Macro, Micro, Mental) that expand independently.

**Implementation:**

```python
# src/core/views/prescriptive_view.py:62-148

class CollapsibleAdviceView(discord.ui.View):
    def __init__(self, advice_sections: dict[str, list[str]]):
        super().__init__(timeout=900.0)  # 15 minutes
        self.advice_sections = advice_sections
        self.expanded_sections: set[str] = set()  # Track expanded state

    @discord.ui.button(label="📊 宏观决策建议", style=discord.ButtonStyle.primary)
    async def toggle_macro(self, interaction: discord.Interaction, button: discord.ui.Button):
        section_key = "macro"
        if section_key in self.expanded_sections:
            # Collapse: Remove section from embed
            self.expanded_sections.remove(section_key)
        else:
            # Expand: Add section to embed
            self.expanded_sections.add(section_key)

        # Re-render embed with current expanded state
        embed = self._create_advice_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # Similar buttons for "micro" and "mental" sections...

    def _create_advice_embed(self) -> discord.Embed:
        embed = discord.Embed(title="📋 实操建议")

        for section_key in ["macro", "micro", "mental"]:
            if section_key in self.expanded_sections:
                # Show bullet points
                bullets = self.advice_sections[section_key]
                field_value = "\\n".join([f"• {bullet}" for bullet in bullets])
                embed.add_field(name=f"{ICONS[section_key]} {LABELS[section_key]}", value=field_value)

        return embed
```

**Key Design Decisions:**
- Each button toggles its own section (independent state)
- Expanded state stored in `self.expanded_sections` set
- Re-render entire embed on each toggle (Discord limitation)

**Testing:**
```python
# Test section expansion
view = CollapsibleAdviceView({"macro": ["Advice 1", "Advice 2"]})
assert len(view.expanded_sections) == 0  # Initially collapsed

# Simulate button click
await view.toggle_macro(mock_interaction, mock_button)
assert "macro" in view.expanded_sections  # Now expanded

# Simulate second click
await view.toggle_macro(mock_interaction, mock_button)
assert "macro" not in view.expanded_sections  # Collapsed again
```

---

## Development Workflow

### Setting Up Development Environment

**Prerequisites:**
- Python 3.11+
- Poetry (dependency management)
- Discord Developer Account (for bot token)

**Step 1: Clone and Install Dependencies**

```bash
# Clone repository
git clone https://github.com/projectchimera/lolbot.git
cd lolbot

# Install dependencies with Poetry
poetry install

# Activate virtual environment
poetry shell
```

**Step 2: Configure Environment Variables**

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your credentials
# Required for CLI 1:
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_APPLICATION_ID=your_app_id_here

# Optional feature flags:
FEATURE_V21_PRESCRIPTIVE_ENABLED=true
FEATURE_V22_PERSONALIZATION_ENABLED=true
```

**Step 3: Create Test Discord Server**

1. Create a private Discord server for testing
2. Invite your bot using OAuth2 URL with `bot` and `applications.commands` scopes
3. Grant required permissions: Send Messages, Embed Links, Use Slash Commands

**Step 4: Run Bot Locally**

```bash
# Start bot in development mode
poetry run python main.py

# Verify bot is online in your test server
# Try: /help command
```

---

### Making UI Changes

**Typical Workflow:**

1. **Identify the Component:**
   - Embed layout change → Edit `paginated_team_view.py` or `fallback_analysis_view.py`
   - Button behavior change → Edit corresponding view's button handler
   - New command → Add to `discord_adapter.py`

2. **Read the Contract:**
   - Check `src/contracts/v2_team_analysis.py` for available data fields
   - Never assume new fields exist without backend coordination

3. **Make the Change:**
   ```python
   # Example: Add new field to player detail card
   # File: src/core/views/paginated_team_view.py

   field_value += f"**{player.champion_name}** | 综合得分: **{player.overall_score:.1f}**\n"
   # NEW: Add champion level
   field_value += f"**等级:** {player.champion_level}\n"  # ← Add this line
   field_value += f"✨ 优势: {player.top_strength_dimension}...\n"
   ```

4. **Test Locally:**
   ```bash
   # Restart bot
   poetry run python main.py

   # In Discord test server:
   # /jiangli → Verify new field appears
   ```

5. **Commit and Create PR:**
   ```bash
   git add src/core/views/paginated_team_view.py
   git commit -m "feat: add champion level to player detail card"
   git push origin feature/add-champion-level

   # Create Pull Request on GitHub
   ```

---

### Adding a New Slash Command

**Example: Add `/ping` command**

**Step 1: Register Command**

```python
# File: src/adapters/discord_adapter.py

# Add registration in __init__ (around line 220)
@self.bot.tree.command(name="ping", description="Check bot latency")
async def ping_command(interaction: discord.Interaction) -> None:
    await self._handle_ping_command(interaction)
```

**Step 2: Implement Handler**

```python
# File: src/adapters/discord_adapter.py

async def _handle_ping_command(self, interaction: discord.Interaction) -> None:
    """Handle the /ping command - show bot latency."""
    latency_ms = round(self.bot.latency * 1000, 2)

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot Latency: **{latency_ms}ms**",
        color=0x5865F2
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)
```

**Step 3: Sync Commands**

```bash
# Restart bot - commands auto-sync on startup
poetry run python main.py

# In Discord, slash commands update within 1 hour (global) or instant (guild-specific)
```

**Step 4: Document Command**

```python
# Update /help command embed (src/adapters/discord_adapter.py:780-800)

commands_text = (
    "`/jiangli` - 分析你的最新比赛\n"
    "`/settings` - 配置个人偏好\n"
    "`/help` - 查看此帮助文档\n"
    "`/ping` - 检查机器人延迟\n"  # ← Add this line
)
```

---

### Debugging Tips

**1. Enable Debug Logging**

```python
# File: main.py or src/adapters/discord_adapter.py

import logging
logging.basicConfig(level=logging.DEBUG)

# See all Discord API calls and responses
```

**2. Use Discord Developer Mode**

```
Settings > Advanced > Enable Developer Mode

# Right-click on messages, users, servers to copy IDs
# Useful for debugging interaction tokens
```

**3. Test with Mock Data**

```python
# File: tests/unit/test_paginated_view.py

from src.contracts.v2_team_analysis import V2TeamAnalysisReport

# Create mock report
mock_report = V2TeamAnalysisReport(
    match_id="TEST_123",
    game_mode="aram",
    match_result="victory",
    # ... fill required fields
)

# Test view rendering
view = PaginatedTeamAnalysisView(mock_report, "TEST_123")
embed = view._create_summary_page()

# Verify embed content
assert "ARAM" in embed.description
```

**4. Inspect Discord Embed Limits**

```python
# Discord Embed Limits (enforced by API):
MAX_TITLE_LENGTH = 256
MAX_DESCRIPTION_LENGTH = 4096
MAX_FIELD_COUNT = 25
MAX_FIELD_NAME_LENGTH = 256
MAX_FIELD_VALUE_LENGTH = 1024
MAX_FOOTER_LENGTH = 2048
MAX_AUTHOR_NAME_LENGTH = 256
MAX_TOTAL_CHARACTERS = 6000  # Sum of all text

# Truncate text if needed:
if len(text) > 1024:
    text = text[:1021] + "..."
```

---

## Testing Guidelines

### Unit Testing

**Test Coverage Targets:**
- Views: 80%+ (focus on conditional rendering logic)
- Adapters: 60%+ (mock Discord API calls)
- Contracts: 100% (Pydantic validation)

**Example: Test Mode-Aware Rendering**

```python
# File: tests/unit/test_paginated_view.py

import pytest
from src.core.views.paginated_team_view import PaginatedTeamAnalysisView
from src.contracts.v2_team_analysis import V2TeamAnalysisReport

def test_aram_mode_hides_vision_control():
    """Test that Vision Control is hidden in ARAM mode."""
    # Arrange
    report = V2TeamAnalysisReport(
        match_id="ARAM_123",
        game_mode="aram",
        match_result="victory",
        team_analysis=[
            # Player with Vision as top strength
            V2PlayerAnalysisResult(
                summoner_name="TestPlayer",
                top_strength_dimension="Vision",
                top_strength_score=85.0,
                # ... other fields
            )
        ]
    )

    # Act
    view = PaginatedTeamAnalysisView(report, "ARAM_123")
    embed = view._create_team_details_page()

    # Assert
    embed_text = str(embed.to_dict())
    assert "Vision" not in embed_text, "Vision Control should be hidden in ARAM"
    assert "Damage" in embed_text or "Teamfight" in embed_text, "Alternative metric should be shown"
```

**Run Unit Tests:**

```bash
# Run all unit tests
poetry run pytest tests/unit/

# Run with coverage report
poetry run pytest --cov=src/core/views --cov-report=html tests/unit/

# Open coverage report
open htmlcov/index.html
```

---

### Integration Testing

**Test Discord Interactions (Requires Bot Running):**

```python
# File: tests/integration/test_discord_commands.py

import discord
from discord.ext import commands
import pytest

@pytest.mark.asyncio
async def test_jiangli_command_defers_reply():
    """Test that /jiangli defers reply within 3 seconds."""
    # This requires a running bot and test server
    # Use discord.py testing framework or manual testing

    # Manual test procedure:
    # 1. Invoke /jiangli in test server
    # 2. Verify "Bot is thinking..." appears within 3s
    # 3. Verify final result appears after 5-30s
    pass  # Manual test
```

**Manual Testing Checklist:**

```markdown
### V2.0 Pagination
- [ ] `/jiangli` shows "⏳ 正在分析..." within 3 seconds
- [ ] Page 1 displays team summary and top 3 players
- [ ] ▶️ 下一页 button navigates to Page 2
- [ ] Page 2 displays all 5 players with details
- [ ] ◀️ 上一页 button navigates back to Page 1
- [ ] Feedback buttons (👍👎⭐) are clickable

### V2.1 Prescriptive Advice
- [ ] "📋 实操建议" button appears on Page 2
- [ ] Clicking button expands advice sections
- [ ] 📊 宏观决策 section can be toggled
- [ ] 🎯 微操技巧 section can be toggled
- [ ] 💭 心态调整 section can be toggled
- [ ] Timeline evidence shows format "15:32 时..."

### V2.2 Settings
- [ ] `/settings` opens modal within 3 seconds
- [ ] All 4 fields have placeholder text
- [ ] Submitting valid inputs shows success message
- [ ] Submitting invalid inputs shows error message
- [ ] Settings persist across multiple `/jiangli` invocations

### V2.3 Mode Awareness
- [ ] SR match shows 🏞️ emoji and "召唤师峡谷" label
- [ ] ARAM match shows ❄️ emoji and "ARAM" label
- [ ] ARAM match hides Vision Control metrics
- [ ] Arena match shows ⚔️ emoji and "Arena" label
- [ ] Unsupported mode shows fallback UI with basic data
```

---

### Visual Regression Testing

**Tools:**
- Playwright (screenshot comparison)
- Percy.io (visual diff service)

**Example: Screenshot Test**

```python
# File: tests/visual/test_embed_screenshots.py

from playwright.async_api import async_playwright

async def test_team_analysis_screenshot():
    """Capture screenshot of team analysis embed for visual regression."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Navigate to Discord web app (requires login)
        await page.goto("https://discord.com/channels/your_server/your_channel")

        # Wait for analysis result
        await page.wait_for_selector("text=团队分析总览")

        # Capture screenshot
        await page.screenshot(path="screenshots/team_analysis_v2.4.png")

        # Compare with baseline (using percy or manual diff)
        # assert image_diff("screenshots/baseline.png", "screenshots/current.png") < 5%
```

---

## Deployment Procedures

### Pre-Deployment Checklist

```markdown
- [ ] All unit tests pass (`poetry run pytest tests/unit/`)
- [ ] Manual testing completed on test server
- [ ] Code review approved by at least 1 reviewer
- [ ] Feature flags configured correctly in production `.env`
- [ ] Webhook delivery tested (requires CLI 2 coordination)
- [ ] Database migrations applied (if V2.2 settings)
- [ ] Sentry error tracking configured
- [ ] Rollback plan documented
```

---

### Deployment Steps (Production)

**Step 1: Merge to Main Branch**

```bash
# Ensure main is up-to-date
git checkout main
git pull origin main

# Merge feature branch
git merge feature/your-feature-name

# Push to main
git push origin main
```

**Step 2: Deploy to Production Server**

```bash
# SSH into production server
ssh user@production-server

# Navigate to project directory
cd /opt/lolbot

# Pull latest code
git pull origin main

# Install/update dependencies
poetry install --no-dev

# Restart bot service
sudo systemctl restart lolbot.service

# Verify bot is running
sudo systemctl status lolbot.service
```

**Step 3: Verify Deployment**

```bash
# Check logs for errors
sudo journalctl -u lolbot.service -f

# In Discord production server:
# 1. Test /help command
# 2. Test /jiangli command
# 3. Verify UI changes are visible
```

**Step 4: Monitor for Issues**

```bash
# Watch Sentry dashboard for new errors
# https://sentry.io/organizations/your-org/projects/lolbot/

# Monitor bot uptime
# Check Discord API rate limits (should be <80%)
```

---

### Rolling Back a Deployment

**If Critical Bug Detected:**

```bash
# SSH into production server
ssh user@production-server

# Navigate to project
cd /opt/lolbot

# Revert to previous commit
git log --oneline  # Find previous stable commit
git reset --hard abc1234  # Replace with actual commit SHA

# Restart bot
sudo systemctl restart lolbot.service

# Notify team in #incidents channel
```

---

### Feature Flag Management

**Enabling a Feature in Production:**

```bash
# Edit .env file on production server
sudo nano /opt/lolbot/.env

# Change feature flag:
FEATURE_V21_PRESCRIPTIVE_ENABLED=false → true

# Restart bot to apply changes
sudo systemctl restart lolbot.service
```

**Gradual Rollout Strategy:**

```python
# In settings.py, add user allowlist feature flag
class Settings(BaseSettings):
    feature_v22_personalization_enabled: bool = Field(default=False)
    feature_v22_allowlist_users: list[str] = Field(default_factory=list)

# In discord_adapter.py, check allowlist
if settings.feature_v22_personalization_enabled:
    if not settings.feature_v22_allowlist_users or str(interaction.user.id) in settings.feature_v22_allowlist_users:
        # Show settings command
        pass
```

---

## Maintenance Tasks

### Regular Maintenance (Weekly)

**Task 1: Monitor Error Rates**

```bash
# Check Sentry for new errors
# Target: <10 errors per day in production

# Common error patterns to watch:
# - Discord API rate limits (429 errors)
# - Interaction timeouts (3-second violations)
# - Webhook delivery failures
```

**Task 2: Review User Feedback**

```python
# Query feedback button clicks from database
# Analyze trends:
# - Thumbs up (👍) rate: Target >70%
# - Star (⭐) rate: Target >10%
# - Thumbs down (👎) rate: Target <20%

# If thumbs down rate increases, investigate:
# - Check if narrative quality degraded
# - Review recent LLM prompt changes
# - Read user comments (if feedback form exists)
```

**Task 3: Update Dependencies**

```bash
# Check for security updates
poetry update

# Run tests after updating
poetry run pytest tests/

# Deploy if tests pass
```

---

### Quarterly Maintenance

**Task 1: Review and Archive Old Features**

```python
# Example: Remove V1.x legacy code if V2.x is stable
# Check git blame for dead code:
git log --all --full-history -- "src/adapters/legacy_adapter.py"

# If not used in 6+ months, create archive branch and delete
git branch archive/v1-legacy
git rm src/adapters/legacy_adapter.py
git commit -m "chore: archive legacy V1 adapter"
```

**Task 2: Performance Optimization**

```python
# Profile bot performance
# Tools: py-spy, cProfile

# Target metrics:
# - /jiangli defer reply: <1s
# - Embed rendering: <100ms
# - Memory usage: <500MB

# If metrics degrade, investigate:
# - Memory leaks (use tracemalloc)
# - Slow database queries
# - Discord API rate limits
```

**Task 3: Documentation Updates**

```markdown
# Update this guide with:
# - New features added since last update
# - Common troubleshooting patterns
# - New integration requirements (CLI 2/3/4 changes)
```

---

## Adding New Features

### Feature Request Template

Before implementing a new feature, document:

```markdown
# Feature Request: [Feature Name]

## Problem Statement
What user problem does this solve?

## Proposed Solution
High-level design of the feature.

## UI Mockups
Screenshots or wireframes of proposed UI.

## Data Requirements
What new fields are needed in contracts?

## Backend Dependencies
Does this require CLI 2/3/4 changes?

## Testing Plan
How will this be tested?

## Rollout Strategy
Feature flag? Gradual rollout?

## Success Metrics
How will we measure success?
```

---

### Example: Adding a New Game Mode (e.g., URF)

**Step 1: Update Contract**

```python
# File: src/contracts/v2_team_analysis.py

# Update game_mode field to include new mode
game_mode: Literal["summoners_rift", "aram", "arena", "urf", "unknown"] = Field(...)
```

**Step 2: Add Mode Emoji Mapping**

```python
# File: src/core/views/paginated_team_view.py

def _get_mode_emoji_and_label(self) -> tuple[str, str]:
    mode_map = {
        "aram": ("❄️", "ARAM（极地大乱斗）"),
        "arena": ("⚔️", "Arena（斗魂竞技场）"),
        "summoners_rift": ("🏞️", "召唤师峡谷"),
        "urf": ("⚡", "URF（无限火力）"),  # ← Add this line
        "unknown": ("❓", "未知模式"),
    }
    return mode_map.get(self.report.game_mode, ("🎮", "游戏模式"))
```

**Step 3: Define Mode-Specific Metric Rules**

```python
# File: src/core/views/paginated_team_view.py

def _should_show_vision_control(self) -> bool:
    """URF has no vision control either (fast-paced, no wards)."""
    return self.report.game_mode not in ["aram", "urf", "unknown"]
```

**Step 4: Update Help Command**

```python
# File: src/adapters/discord_adapter.py

modes_text = (
    "✅ **召唤师峡谷** - 5v5 排位/匹配\n"
    "✅ **极地大乱斗 (ARAM)** - 单线混战\n"
    "✅ **斗魂竞技场 (Arena)** - 2v2v2v2 竞技\n"
    "✅ **无限火力 (URF)** - 快速高强度战斗\n"  # ← Add this line
    "\n更多游戏模式支持开发中..."
)
```

**Step 5: Coordinate with CLI 2**

```markdown
# Create issue for CLI 2 team:
## Backend: Add URF Mode Support

**Requirements:**
1. Update queue ID mapping to recognize URF (queue_id: 900, 1900)
2. Implement URF-specific analysis strategy
3. Populate `game_mode="urf"` in V2TeamAnalysisReport

**Acceptance Criteria:**
- URF matches detected correctly
- Analysis considers fast-paced gameplay (higher KDA expected)
- Vision metrics excluded from scoring

**Delivery Date:** [Target Date]
```

**Step 6: Test End-to-End**

```bash
# After CLI 2 deploys URF support:
# 1. Play a URF match
# 2. Invoke /jiangli
# 3. Verify ⚡ emoji appears in title
# 4. Verify Vision Control is hidden
# 5. Verify analysis narrative mentions URF-specific context
```

---

### Example: Adding a New Feedback Button (e.g., 🔥 "Super Helpful")

**Step 1: Add Button to View**

```python
# File: src/core/views/paginated_team_view.py

def _add_feedback_buttons(self) -> None:
    # Existing buttons: 👍 👎 ⭐

    # Add new "Super Helpful" button
    self.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="🔥",
            label="Super Helpful",
            custom_id=f"chimera:fb:fire:{self.match_id}",
            row=4,
        )
    )
```

**Step 2: Handle Button Click**

```python
# File: src/adapters/discord_adapter.py

# Add handler for fire button
@self.bot.tree.interaction_check
async def on_interaction(interaction: discord.Interaction) -> bool:
    if interaction.data.get("custom_id", "").startswith("chimera:fb:fire"):
        match_id = interaction.data["custom_id"].split(":")[-1]
        await self._handle_fire_feedback(interaction, match_id)
        return True
    return False

async def _handle_fire_feedback(self, interaction: discord.Interaction, match_id: str) -> None:
    # Log feedback to analytics
    logger.info(f"User {interaction.user.id} clicked 🔥 for match {match_id}")

    # Send thank you message
    await interaction.response.send_message(
        "🔥 Thanks for the feedback! This helps us improve.",
        ephemeral=True
    )
```

**Step 3: Track in Analytics**

```python
# File: src/core/observability.py

# Add new feedback type to metrics
feedback_clicks.labels(
    button_type="fire",
    match_id=match_id,
    user_id=user_id
).inc()
```

---

## Critical Constraints and Best Practices

### Constraint 1: Discord Interaction Timeout (3 Seconds)

**Rule:** You MUST respond to an interaction within 3 seconds, or Discord will show "This interaction failed."

**Solutions:**
1. **Defer Reply:** `await interaction.response.defer()`
2. **Immediate Ephemeral Response:** `await interaction.response.send_message("Working...", ephemeral=True)`
3. **Webhook Delivery:** For long-running tasks (>3s), use webhook to update message later

**Anti-Pattern:**
```python
# ❌ BAD: This will timeout if analysis takes >3 seconds
async def bad_command(interaction: discord.Interaction):
    result = await slow_analysis()  # Takes 10 seconds
    await interaction.response.send_message(result)  # TOO LATE!
```

**Correct Pattern:**
```python
# ✅ GOOD: Defer reply first
async def good_command(interaction: discord.Interaction):
    await interaction.response.defer()  # Immediate acknowledgment
    result = await slow_analysis()  # Takes 10 seconds
    await interaction.followup.send(result)  # Delivered via webhook
```

---

### Constraint 2: Discord Embed Limits

**Character Limits:**
```python
DISCORD_LIMITS = {
    "embed_title": 256,
    "embed_description": 4096,
    "embed_field_name": 256,
    "embed_field_value": 1024,
    "embed_footer": 2048,
    "embed_author_name": 256,
    "embed_total_characters": 6000,  # Sum of all text
    "embed_field_count": 25,
}
```

**Enforcement:**
```python
# Always truncate long text
def truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

# Usage
field_value = truncate_text(player.narrative_summary, 1024)
```

---

### Constraint 3: Discord Rate Limits

**Global Rate Limit:** 50 requests per second per bot

**Per-Route Rate Limits:**
- Send message: 5 messages per 5 seconds per channel
- Edit message: 5 edits per 5 seconds per channel
- Delete message: 5 deletes per 5 seconds per channel

**Best Practices:**
1. Batch operations when possible
2. Use `ephemeral=True` for temporary messages (doesn't count toward channel rate limit)
3. Implement exponential backoff for rate limit errors (429 status)

```python
# Example: Exponential backoff
import asyncio

async def send_with_retry(channel, content, max_retries=3):
    for attempt in range(max_retries):
        try:
            await channel.send(content)
            return
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                retry_after = e.retry_after
                await asyncio.sleep(retry_after)
            else:
                raise
```

---

### Best Practice 1: Always Use Ephemeral for Settings/Help

**Why:** Settings and help commands are user-specific and don't need to clutter chat.

```python
# ✅ GOOD: Ephemeral response
await interaction.response.send_message(
    embed=help_embed,
    ephemeral=True  # Only visible to user who invoked command
)

# ❌ BAD: Public response for settings
await interaction.response.send_message(embed=settings_embed)  # Everyone sees it!
```

---

### Best Practice 2: Validate User Inputs Early

**Why:** Discord modals don't have built-in validation; users can submit any text.

```python
# src/core/views/settings_modal.py:72-95

def _validate_inputs(self, update_request: UserProfileUpdateRequest) -> str | None:
    """Validate user inputs and return error message if invalid."""

    # Validate role
    valid_roles = ["top", "jungle", "mid", "bot", "support", "fill"]
    if update_request.main_role not in valid_roles:
        return f"主要位置必须是: {', '.join(valid_roles)}"

    # Validate tone
    valid_tones = ["competitive", "casual", "balanced"]
    if update_request.analysis_tone not in valid_tones:
        return f"分析语气必须是: {', '.join(valid_tones)}"

    # ... more validations

    return None  # All valid
```

---

### Best Practice 3: Use Type Hints Everywhere

**Why:** Type hints enable IDE autocomplete and catch bugs early.

```python
# ✅ GOOD: Full type hints
async def _create_page_embed(self, page_num: int) -> discord.Embed:
    embed: discord.Embed = discord.Embed(title="...")
    field_value: str = f"{player.champion_name}..."
    return embed

# ❌ BAD: No type hints
async def _create_page_embed(self, page_num):
    embed = discord.Embed(title="...")
    field_value = f"{player.champion_name}..."
    return embed
```

---

### Best Practice 4: Centralize Error Handling

**Why:** Consistent error messages improve user experience.

```python
# File: src/adapters/discord_adapter.py

async def _send_error_embed(self, interaction: discord.Interaction, error_message: str) -> None:
    """Send standardized error embed to user."""
    embed = discord.Embed(
        title="❌ 操作失败",
        description=error_message,
        color=0xE74C3C  # Red
    )
    embed.add_field(
        name="建议操作",
        value="• 等待 2-3 分钟后重试\n• 如果问题持续，请联系管理员"
    )

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Usage in command handlers:
try:
    # ... some operation
except Exception as e:
    logger.error(f"Command failed: {e}", exc_info=True)
    await self._send_error_embed(interaction, "分析服务暂时不可用，请稍后重试。")
```

---

## Troubleshooting Guide

### Issue 1: "This interaction failed" Error

**Symptoms:** User sees "This interaction failed" when invoking command.

**Cause:** Bot didn't respond within 3 seconds.

**Diagnosis:**
```python
# Add timing logs to identify slow operations
start_time = time.time()
await interaction.response.defer()
defer_latency = time.time() - start_time
logger.info(f"Defer latency: {defer_latency:.3f}s")

# If defer_latency > 1.0s, something is blocking
```

**Solutions:**
1. Move heavy operations to background task
2. Ensure `defer()` is called immediately in handler
3. Check for blocking I/O before `defer()` (e.g., database queries)

---

### Issue 2: Embed Not Displaying Correctly

**Symptoms:** Embed shows as plain text or fields are missing.

**Cause:** Embed structure invalid or exceeds Discord limits.

**Diagnosis:**
```python
# Print embed dict for inspection
embed_dict = embed.to_dict()
print(json.dumps(embed_dict, indent=2))

# Check total character count
total_chars = sum(len(str(v)) for v in embed_dict.values() if isinstance(v, str))
if total_chars > 6000:
    logger.error(f"Embed exceeds 6000 character limit: {total_chars}")
```

**Solutions:**
1. Truncate long text fields
2. Split into multiple embeds if necessary
3. Validate embed structure against Discord API docs

---

### Issue 3: Buttons Not Responding

**Symptoms:** User clicks button, nothing happens.

**Cause:** View timeout (15 minutes default) or button handler not registered.

**Diagnosis:**
```python
# Check if view is still active
logger.info(f"View timeout status: {view.is_finished()}")

# Add button click logging
@discord.ui.button(label="Test")
async def test_button(self, interaction, button):
    logger.info(f"Button clicked by {interaction.user.id}")
    # ... rest of handler
```

**Solutions:**
1. Increase view timeout: `discord.ui.View(timeout=3600)`  # 1 hour
2. Re-send message with fresh view if timeout occurred
3. Verify button `custom_id` format matches expected pattern

---

### Issue 4: Modal Not Opening

**Symptoms:** User invokes `/settings`, nothing happens.

**Cause:** Modal can only be sent as initial response, not in followup.

**Diagnosis:**
```python
# Check if interaction response already sent
if interaction.response.is_done():
    logger.error("Cannot send modal: interaction already responded to")
```

**Solutions:**
1. Ensure modal is sent as initial response: `await interaction.response.send_modal(modal)`
2. Don't call `defer()` before sending modal
3. If response already sent, ask user to re-invoke command

---

### Issue 5: Webhook Delivery Failing

**Symptoms:** Analysis completes but user never sees result.

**Cause:** Webhook URL invalid or interaction token expired (15 minutes).

**Diagnosis:**
```bash
# Check CLI 2 webhook logs
tail -f /var/log/lolbot/webhook_delivery.log

# Look for:
# - 404 errors (invalid webhook URL)
# - 410 errors (interaction token expired)
# - Network timeouts
```

**Solutions:**
1. Ensure analysis completes within 15 minutes
2. Verify webhook URL format: `https://discord.com/api/v10/webhooks/{app_id}/{token}`
3. Implement retry logic with exponential backoff
4. If expired, send new message instead of editing original

---

### Issue 6: Mode-Specific Metrics Not Filtering

**Symptoms:** Vision Control still shown in ARAM mode.

**Cause:** Backend not populating `game_mode` field correctly.

**Diagnosis:**
```python
# Add logging in view rendering
logger.info(f"Rendering analysis for mode: {self.report.game_mode}")
logger.info(f"Should show vision: {self._should_show_vision_control()}")

# Check backend response
# Expected: game_mode="aram"
# If game_mode="summoners_rift" or "unknown", backend issue
```

**Solutions:**
1. Verify CLI 2 queue ID mapping includes ARAM (queue_id: 450)
2. Check backend strategy selection logic
3. Ensure `game_mode` field is populated before sending to webhook

---

## Appendix

### Appendix A: Discord.py Quick Reference

**Common Patterns:**

```python
# Send embed
embed = discord.Embed(title="Title", description="Description", color=0x5865F2)
await interaction.response.send_message(embed=embed)

# Defer reply
await interaction.response.defer(thinking=True)
await interaction.followup.send("Result")

# Edit original message
await interaction.edit_original_response(content="Updated")

# Send ephemeral message
await interaction.response.send_message("Secret", ephemeral=True)

# Add button
view = discord.ui.View()
button = discord.ui.Button(label="Click", style=discord.ButtonStyle.primary)
view.add_item(button)
await interaction.response.send_message("Message", view=view)

# Open modal
modal = MyModal()
await interaction.response.send_modal(modal)
```

---

### Appendix B: Useful Discord Developer Resources

**Official Documentation:**
- Discord.py Docs: https://discordpy.readthedocs.io/
- Discord API Docs: https://discord.com/developers/docs/
- Interaction Docs: https://discord.com/developers/docs/interactions/receiving-and-responding

**Community Resources:**
- Discord.py Discord Server: https://discord.gg/dpy
- Discord Developers Server: https://discord.gg/discord-developers

**Tools:**
- Discord Embed Visualizer: https://leovoel.github.io/embed-visualizer/
- Discord Permissions Calculator: https://discordapi.com/permissions.html

---

### Appendix C: Git Workflow for Frontend Changes

**Branch Naming:**
```
feat/add-urf-mode       # New feature
fix/pagination-bug      # Bug fix
refactor/view-cleanup   # Code refactoring
docs/update-guide       # Documentation update
```

**Commit Message Format:**
```
<type>(<scope>): <subject>

<body>

<footer>

# Examples:
feat(views): add URF mode support with ⚡ emoji
fix(pagination): prevent crash when team has <5 players
docs(guide): update deployment procedures for V2.4
```

**Pull Request Template:**
```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Manual testing completed
- [ ] Screenshot attached (if UI change)

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or documented)

## Screenshots (if applicable)
[Attach before/after screenshots]

## Related Issues
Closes #123
```

---

### Appendix D: Performance Benchmarks

**Target Metrics (V2.4):**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Defer Reply Latency | <1s | Time from command invoke to `defer()` |
| Total Analysis Duration | <30s (p95) | End-to-end from invoke to result |
| Webhook Delivery | <2s | Time for webhook PATCH to complete |
| Embed Rendering | <100ms | Time to generate embed object |
| Button Click Response | <300ms | Time from click to visual feedback |
| Memory Usage | <500MB | Bot process RSS |
| CPU Usage (Idle) | <5% | Bot process CPU % when idle |

**Monitoring:**
```python
# Add timing metrics to key operations
from src.core.observability import timer

@timer("view.paginated_team_view.create_summary")
def _create_summary_page(self) -> discord.Embed:
    # ... implementation
    pass

# Query metrics in Prometheus/Grafana
rate(view_paginated_team_view_create_summary_duration_seconds[5m])
```

---

### Appendix E: Contact and Support

**For Frontend Development Questions:**
- Lead Frontend Developer: [Name] - [email]
- Discord Channel: `#cli1-frontend-dev`
- GitHub Discussions: [Project Discussions](https://github.com/projectchimera/lolbot/discussions)

**For Cross-Team Coordination:**
- CLI 2 (Backend) Lead: [Name] - [email] - For contract changes, webhook delivery
- CLI 3 (SRE) Lead: [Name] - [email] - For deployment, database issues
- CLI 4 (Lab) Lead: [Name] - [email] - For A/B testing, analytics

**Emergency Contacts:**
- Production Incident: `#incidents` channel
- On-Call Rotation: [PagerDuty Link]

---

**Document Version:** 2.4.0
**Last Updated:** 2025-10-07
**Maintained By:** CLI 1 Frontend Team
**Next Review Date:** 2026-01-07 (Quarterly)

**Changelog:**
- **2025-10-07 (V2.4.0):** Consolidated V2.0-V2.3 documentation, added V2.4 testing and release procedures
- **2025-09-15 (V2.3.0):** Added mode-aware UI documentation
- **2025-08-20 (V2.2.0):** Added settings modal documentation
- **2025-07-10 (V2.1.0):** Added prescriptive advice documentation
- **2025-06-01 (V2.0.0):** Initial version with pagination UI

---

**End of Guide**

For the latest updates, always refer to the GitHub repository: [github.com/projectchimera/lolbot/docs](https://github.com/projectchimera/lolbot/docs)

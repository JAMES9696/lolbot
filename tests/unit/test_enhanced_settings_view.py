"""Unit tests for Enhanced Settings View.

Tests the visual Select Menu and Button-based settings UI that
replaces the text input modal approach.
"""

import pytest
from unittest.mock import AsyncMock

from src.core.views.enhanced_settings_view import (
    EnhancedSettingsView,
    create_enhanced_settings_view,
)


@pytest.fixture
def mock_db_adapter():
    """Create mock database adapter."""
    db = AsyncMock()
    db.get_user_preferences = AsyncMock(return_value=None)
    db.save_user_preferences = AsyncMock(return_value=True)
    return db


@pytest.fixture
def mock_interaction():
    """Create mock Discord interaction."""
    interaction = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.message.edit = AsyncMock()
    interaction.data = {"values": ["top"]}
    return interaction


@pytest.fixture
def default_preferences():
    """Default user preferences for testing."""
    return {
        "main_role": "jungle",
        "analysis_tone": "competitive",
        "advice_detail_level": "detailed",
        "show_timeline_references": True,
    }


class TestEnhancedSettingsView:
    """Test suite for EnhancedSettingsView."""

    @pytest.mark.asyncio
    async def test_view_initialization_with_defaults(self, mock_db_adapter):
        """Test view initializes correctly with default preferences."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        assert view.user_id == "123456789"
        assert view.current_preferences == {}
        assert view.pending_changes == {}
        assert len(view.children) > 0  # UI components added

    @pytest.mark.asyncio
    async def test_view_initialization_with_existing_preferences(
        self, mock_db_adapter, default_preferences
    ):
        """Test view initializes correctly with existing preferences."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=default_preferences,
            db_adapter=mock_db_adapter,
        )

        assert view.current_preferences == default_preferences
        assert view.pending_changes == {}

    @pytest.mark.asyncio
    async def test_ui_components_present(self, mock_db_adapter):
        """Test all required UI components are added to view."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Check for Select components
        selects = [child for child in view.children if hasattr(child, "custom_id")]
        select_ids = [child.custom_id for child in selects if hasattr(child, "options")]

        assert "role_select" in select_ids
        assert "tone_select" in select_ids
        assert "detail_select" in select_ids

        # Check for Button components
        button_ids = [child.custom_id for child in selects if not hasattr(child, "options")]

        assert "timeline_toggle" in button_ids
        assert "save_button" in button_ids
        assert "reset_button" in button_ids

    @pytest.mark.asyncio
    async def test_role_selection_updates_pending_changes(self, mock_db_adapter, mock_interaction):
        """Test role selection updates pending changes."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Simulate role selection
        mock_interaction.data = {"values": ["top"]}
        await view._role_selected(mock_interaction)

        assert view.pending_changes["main_role"] == "top"
        mock_interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_tone_selection_updates_pending_changes(self, mock_db_adapter, mock_interaction):
        """Test tone selection updates pending changes."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Simulate tone selection
        mock_interaction.data = {"values": ["casual"]}
        await view._tone_selected(mock_interaction)

        assert view.pending_changes["analysis_tone"] == "casual"
        mock_interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_detail_selection_updates_pending_changes(
        self, mock_db_adapter, mock_interaction
    ):
        """Test detail level selection updates pending changes."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Simulate detail selection
        mock_interaction.data = {"values": ["concise"]}
        await view._detail_selected(mock_interaction)

        assert view.pending_changes["advice_detail_level"] == "concise"
        mock_interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeline_toggle_switches_value(self, mock_db_adapter, mock_interaction):
        """Test timeline toggle switches between True/False."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences={"show_timeline_references": True},
            db_adapter=mock_db_adapter,
        )

        # First toggle: True -> False
        await view._timeline_toggled(mock_interaction)
        assert view.pending_changes["show_timeline_references"] is False

        # Second toggle: False -> True
        await view._timeline_toggled(mock_interaction)
        assert view.pending_changes["show_timeline_references"] is True

    @pytest.mark.asyncio
    async def test_save_settings_persists_to_database(
        self, mock_db_adapter, mock_interaction, default_preferences
    ):
        """Test save button persists changes to database."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=default_preferences,
            db_adapter=mock_db_adapter,
        )

        # Add pending changes
        view.pending_changes = {
            "main_role": "top",
            "analysis_tone": "casual",
        }

        # Save settings
        await view._save_settings(mock_interaction)

        # Verify database call
        mock_db_adapter.save_user_preferences.assert_called_once()
        call_args = mock_db_adapter.save_user_preferences.call_args
        assert call_args[0][0] == "123456789"  # user_id
        assert "main_role" in call_args[0][1]
        assert call_args[0][1]["main_role"] == "top"

        # Verify pending changes cleared
        assert view.pending_changes == {}

        # Verify success message sent
        mock_interaction.followup.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_settings_handles_empty_changes(self, mock_db_adapter, mock_interaction):
        """Test save button handles case with no pending changes."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # No pending changes
        view.pending_changes = {}

        # Try to save
        await view._save_settings(mock_interaction)

        # Should not call database
        mock_db_adapter.save_user_preferences.assert_not_called()

        # Should send error message
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "没有待保存的更改" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_reset_changes_clears_pending(self, mock_db_adapter, mock_interaction):
        """Test reset button clears pending changes."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Add pending changes
        view.pending_changes = {
            "main_role": "top",
            "analysis_tone": "casual",
        }

        # Reset changes
        await view._reset_changes(mock_interaction)

        # Verify pending changes cleared
        assert view.pending_changes == {}

        # Verify view recreated
        mock_interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_embed_shows_pending_changes(self, mock_db_adapter):
        """Test preview embed correctly shows pending changes."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences={"main_role": "jungle"},
            db_adapter=mock_db_adapter,
        )

        # Add pending change
        view.pending_changes = {"main_role": "top"}

        # Create preview embed
        embed = view._create_preview_embed()

        # Check embed shows pending state
        assert "预览" in embed.title
        assert embed.color.value == 0xFEE75C  # Yellow color for pending

    @pytest.mark.asyncio
    async def test_factory_function_creates_view_with_preferences(
        self, mock_db_adapter, default_preferences
    ):
        """Test factory function creates view with fetched preferences."""
        mock_db_adapter.get_user_preferences = AsyncMock(return_value=default_preferences)

        embed, view = await create_enhanced_settings_view(
            user_id="123456789",
            db_adapter=mock_db_adapter,
        )

        # Verify preferences fetched
        mock_db_adapter.get_user_preferences.assert_called_once_with("123456789")

        # Verify view created with preferences
        assert view.current_preferences == default_preferences

        # Verify embed created
        assert embed.title == "⚙️ 个性化设置"

    @pytest.mark.asyncio
    async def test_embed_displays_all_settings_correctly(
        self, mock_db_adapter, default_preferences
    ):
        """Test embed correctly displays all settings with emojis."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=default_preferences,
            db_adapter=mock_db_adapter,
        )

        embed = view._create_settings_embed(show_pending=False)

        # Convert embed to dict for inspection
        embed_dict = embed.to_dict()
        fields = {field["name"]: field["value"] for field in embed_dict["fields"]}

        # Verify all fields present
        assert "📍 主要位置" in fields
        assert "🎯 分析语气" in fields
        assert "📊 建议详细程度" in fields
        assert "⏱️ 时间轴引用" in fields

        # Verify values have emojis
        assert "🌲" in fields["📍 主要位置"]  # Jungle emoji
        assert "🔥" in fields["🎯 分析语气"]  # Competitive emoji
        assert "📚" in fields["📊 建议详细程度"]  # Detailed emoji
        assert "✅" in fields["⏱️ 时间轴引用"]  # Enabled emoji

    @pytest.mark.asyncio
    async def test_save_settings_handles_database_error(self, mock_db_adapter, mock_interaction):
        """Test save settings gracefully handles database errors."""
        mock_db_adapter.save_user_preferences = AsyncMock(return_value=False)

        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        view.pending_changes = {"main_role": "top"}

        # Try to save
        await view._save_settings(mock_interaction)

        # Should send error message
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "失败" in call_args[0][0]

        # Pending changes should not be cleared
        assert view.pending_changes == {"main_role": "top"}


class TestSelectMenuOptions:
    """Test Select Menu options are correctly configured."""

    @pytest.mark.asyncio
    async def test_role_select_has_all_options(self, mock_db_adapter):
        """Test role select has all 6 role options."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Find role select
        role_select = next(
            child
            for child in view.children
            if hasattr(child, "custom_id") and child.custom_id == "role_select"
        )

        assert len(role_select.options) == 6
        option_values = [opt.value for opt in role_select.options]
        assert set(option_values) == {"top", "jungle", "mid", "bot", "support", "fill"}

    @pytest.mark.asyncio
    async def test_tone_select_has_all_options(self, mock_db_adapter):
        """Test tone select has all 3 tone options."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Find tone select
        tone_select = next(
            child
            for child in view.children
            if hasattr(child, "custom_id") and child.custom_id == "tone_select"
        )

        assert len(tone_select.options) == 3
        option_values = [opt.value for opt in tone_select.options]
        assert set(option_values) == {"competitive", "casual", "balanced"}

    @pytest.mark.asyncio
    async def test_detail_select_has_all_options(self, mock_db_adapter):
        """Test detail select has all 2 detail options."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=None,
            db_adapter=mock_db_adapter,
        )

        # Find detail select
        detail_select = next(
            child
            for child in view.children
            if hasattr(child, "custom_id") and child.custom_id == "detail_select"
        )

        assert len(detail_select.options) == 2
        option_values = [opt.value for opt in detail_select.options]
        assert set(option_values) == {"concise", "detailed"}

    @pytest.mark.asyncio
    async def test_default_selection_matches_current_preference(
        self, mock_db_adapter, default_preferences
    ):
        """Test select menus show correct default based on current preferences."""
        view = EnhancedSettingsView(
            user_id="123456789",
            current_preferences=default_preferences,
            db_adapter=mock_db_adapter,
        )

        # Find role select
        role_select = next(
            child
            for child in view.children
            if hasattr(child, "custom_id") and child.custom_id == "role_select"
        )

        # Check jungle is marked as default
        jungle_option = next(opt for opt in role_select.options if opt.value == "jungle")
        assert jungle_option.default is True

        # Check other options are not default
        top_option = next(opt for opt in role_select.options if opt.value == "top")
        assert top_option.default is False

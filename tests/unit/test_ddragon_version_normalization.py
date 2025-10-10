"""Unit tests for Data Dragon version normalization and icon URL generation.

Tests both team_tasks and team_analysis_view implementations to ensure:
- Underscore-separated versions are handled (e.g., "14.10.1_14.10.1.454")
- Missing gameVersion falls back gracefully
- Standard formats are normalized correctly
"""


class TestTeamTasksVersionNormalization:
    """Test _normalize_game_version and _champion_icon_url in team_tasks."""

    def test_normalize_standard_four_component_version(self) -> None:
        """Verify standard 4-component version (X.Y.Z.BUILD) is trimmed to X.Y.Z."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version("14.10.1.534")
        assert result == "14.10.1"

    def test_normalize_underscore_separated_version(self) -> None:
        """Verify underscore-separated duplicate versions extract first segment."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version("14.10.1_14.10.1.454")
        assert result == "14.10.1"

    def test_normalize_two_component_version(self) -> None:
        """Verify 2-component version (X.Y) appends .1 for patch."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version("14.10")
        assert result == "14.10.1"

    def test_normalize_three_component_version(self) -> None:
        """Verify 3-component version (X.Y.Z) is returned as-is."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version("14.10.1")
        assert result == "14.10.1"

    def test_normalize_none_version(self) -> None:
        """Verify None input returns None."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version(None)
        assert result is None

    def test_normalize_empty_string_version(self) -> None:
        """Verify empty string returns None."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version("")
        assert result is None

    def test_normalize_single_component_version(self) -> None:
        """Verify single component (invalid) returns None."""
        from src.tasks.team_tasks import _normalize_game_version

        result = _normalize_game_version("14")
        assert result is None

    def test_champion_icon_url_with_valid_version(self) -> None:
        """Verify champion icon URL uses normalized version."""
        from src.tasks.team_tasks import _champion_icon_url

        url = _champion_icon_url("Qiyana", "14.10.1.534")
        assert url == "https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/Qiyana.png"

    def test_champion_icon_url_with_underscore_version(self) -> None:
        """Verify champion icon URL handles underscore-separated versions."""
        from src.tasks.team_tasks import _champion_icon_url

        url = _champion_icon_url("Ahri", "14.10.1_14.10.1.454")
        assert url == "https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/Ahri.png"

    def test_champion_icon_url_with_none_version_fallback(self) -> None:
        """Verify champion icon URL falls back when version is None."""
        from src.tasks.team_tasks import _champion_icon_url

        url = _champion_icon_url("Yasuo", None)
        # Should contain a version (either from env, DDragon API, or hardcoded fallback)
        assert "https://ddragon.leagueoflegends.com/cdn/" in url
        assert "/img/champion/Yasuo.png" in url
        # Verify version format is X.Y.Z (not empty)
        version_part = url.split("/cdn/")[1].split("/img/")[0]
        assert len(version_part.split(".")) == 3


class TestTeamAnalysisViewVersionNormalization:
    """Test _normalize_game_version and _ddragon_icon in team_analysis_view."""

    def test_normalize_standard_four_component_version(self) -> None:
        """Verify standard 4-component version (X.Y.Z.BUILD) is trimmed to X.Y.Z."""
        from src.core.views.team_analysis_view import _normalize_game_version

        result = _normalize_game_version("14.10.1.534")
        assert result == "14.10.1"

    def test_normalize_underscore_separated_version(self) -> None:
        """Verify underscore-separated duplicate versions extract first segment."""
        from src.core.views.team_analysis_view import _normalize_game_version

        result = _normalize_game_version("14.10.1_14.10.1.454")
        assert result == "14.10.1"

    def test_normalize_two_component_version(self) -> None:
        """Verify 2-component version (X.Y) appends .1 for patch."""
        from src.core.views.team_analysis_view import _normalize_game_version

        result = _normalize_game_version("14.10")
        assert result == "14.10.1"

    def test_normalize_none_version(self) -> None:
        """Verify None input returns None."""
        from src.core.views.team_analysis_view import _normalize_game_version

        result = _normalize_game_version(None)
        assert result is None

    def test_ddragon_icon_with_valid_version(self) -> None:
        """Verify DDragon icon URL uses normalized version."""
        from src.core.views.team_analysis_view import _ddragon_icon

        url = _ddragon_icon("Qiyana", "14.10.1.534")
        assert url == "https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/Qiyana.png"

    def test_ddragon_icon_with_underscore_version(self) -> None:
        """Verify DDragon icon URL handles underscore-separated versions."""
        from src.core.views.team_analysis_view import _ddragon_icon

        url = _ddragon_icon("Ahri", "14.10.1_14.10.1.454")
        assert url == "https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/Ahri.png"

    def test_ddragon_icon_with_none_version_fallback(self) -> None:
        """Verify DDragon icon URL falls back when version is None."""
        from src.core.views.team_analysis_view import _ddragon_icon

        url = _ddragon_icon("Yasuo", None)
        # Should contain a version (either from DDragon API or hardcoded fallback)
        assert "https://ddragon.leagueoflegends.com/cdn/" in url
        assert "/img/champion/Yasuo.png" in url
        # Verify version format is X.Y.Z (not empty)
        version_part = url.split("/cdn/")[1].split("/img/")[0]
        assert len(version_part.split(".")) == 3

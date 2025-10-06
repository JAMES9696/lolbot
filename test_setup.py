#!/usr/bin/env python3
"""
Quick test script to validate the Project Chimera setup.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        from src.config import Settings, get_settings
        print("✓ Config module imported")
    except ImportError as e:
        print(f"✗ Failed to import config: {e}")
        return False

    try:
        from src.contracts.user_binding import UserBinding, BindingRequest, BindingResponse
        print("✓ User binding contracts imported")
    except ImportError as e:
        print(f"✗ Failed to import user_binding: {e}")
        return False

    try:
        from src.contracts.discord_interactions import InteractionResponse, CommandName
        print("✓ Discord interaction contracts imported")
    except ImportError as e:
        print(f"✗ Failed to import discord_interactions: {e}")
        return False

    try:
        from src.adapters.discord_adapter import DiscordAdapter, ChimeraBot
        print("✓ Discord adapter imported")
    except ImportError as e:
        print(f"✗ Failed to import discord_adapter: {e}")
        return False

    return True


def test_pydantic_models():
    """Test that Pydantic models work correctly."""
    print("\nTesting Pydantic models...")

    from src.contracts.user_binding import UserBinding, BindingStatus
    from src.contracts.discord_interactions import InteractionResponse, EmbedColor

    try:
        # Test UserBinding model
        binding = UserBinding(
            discord_id="123456789012345678",
            region="na1",
            status=BindingStatus.PENDING
        )
        print(f"✓ UserBinding created: {binding.discord_id}")

        # Test InteractionResponse model
        response = InteractionResponse(
            success=True,
            embed_title="Test",
            embed_description="Test description",
            embed_color=EmbedColor.SUCCESS
        )
        print(f"✓ InteractionResponse created: {response.embed_title}")

        return True
    except Exception as e:
        print(f"✗ Model validation failed: {e}")
        return False


def test_configuration():
    """Test configuration loading (without actual env vars)."""
    print("\nTesting configuration system...")

    try:
        from src.config import Settings

        # Test with mock values (won't actually connect)
        settings = Settings(
            DISCORD_BOT_TOKEN="MOCK_TOKEN_FOR_TESTING",
            DISCORD_APPLICATION_ID="123456789",
            RIOT_API_KEY="MOCK_RIOT_KEY"
        )

        print(f"✓ Settings object created")
        print(f"  - Bot token: {'*' * 10} (hidden)")
        print(f"  - Region: {settings.riot_region}")
        print(f"  - Debug mode: {settings.debug_mode}")

        return True
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("Project Chimera Setup Validation")
    print("=" * 50)

    all_passed = True

    if not test_imports():
        all_passed = False

    if not test_pydantic_models():
        all_passed = False

    if not test_configuration():
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All tests passed! Setup is valid.")
        print("\nNext steps:")
        print("1. Copy .env.example to .env")
        print("2. Add your Discord bot token")
        print("3. Run: python main.py")
    else:
        print("❌ Some tests failed. Please check the errors above.")
    print("=" * 50)


if __name__ == "__main__":
    main()
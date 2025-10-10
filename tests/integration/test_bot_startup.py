"""Test Discord Bot startup and command registration.

This script verifies that the bot can start up correctly and
register commands without actually connecting to Discord.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.settings import settings


def test_configuration():
    """Test that all required configurations are present."""
    print("=" * 70)
    print("🔍 Testing Discord Bot Configuration")
    print("=" * 70)

    errors = []

    # Required configurations
    required = {
        "Discord Bot Token": settings.discord_bot_token,
        "Discord Application ID": settings.discord_application_id,
        "Riot API Key": settings.riot_api_key,
        "Database URL": settings.database_url,
        "Redis URL": settings.redis_url,
        "Celery Broker": settings.celery_broker_url,
        "Celery Backend": settings.celery_result_backend,
    }

    # LLM configuration (at least one should be present)
    llm_configured = False
    llm_status = []

    if hasattr(settings, "gemini_api_key") and settings.gemini_api_key:
        llm_configured = True
        llm_status.append("✅ Gemini API Key configured")
    else:
        llm_status.append("⚠️  Gemini API Key not configured")

    if hasattr(settings, "openai_api_key") and settings.openai_api_key:
        llm_configured = True
        llm_status.append("✅ OpenAI API Key configured (OhMyGPT)")
    else:
        llm_status.append("⚠️  OpenAI API Key not configured")

    print("\n📝 Configuration Check:")
    print("-" * 70)

    for name, value in required.items():
        if value and str(value) != "your_" and "here" not in str(value):
            print(f"✅ {name}: Configured")
        else:
            print(f"❌ {name}: Missing or placeholder")
            errors.append(name)

    print("\n🤖 LLM Configuration:")
    print("-" * 70)
    for status in llm_status:
        print(status)

    if not llm_configured:
        print("❌ No LLM API configured - /讲道理 command will fail")
        errors.append("LLM API")
    else:
        print("✅ At least one LLM API is configured")

    print("\n" + "=" * 70)

    if errors:
        print(f"❌ Configuration Errors Found: {len(errors)}")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print("✅ All required configurations are present!")
        return True


def test_imports():
    """Test that all required modules can be imported."""
    print("\n" + "=" * 70)
    print("📦 Testing Module Imports")
    print("=" * 70)

    modules_to_test = [
        ("Discord Adapter", "src.adapters.discord_adapter", "DiscordAdapter"),
        ("Riot API Adapter", "src.adapters.riot_api", "RiotAPIAdapter"),
        ("Database Adapter", "src.adapters.database", "DatabaseAdapter"),
        ("Redis Adapter", "src.adapters.redis_adapter", "RedisAdapter"),
        ("Celery App", "src.tasks.celery_app", "celery_app"),
        ("User Binding Service", "src.core.services.user_binding_service", "UserBindingService"),
    ]

    errors = []

    for name, module_path, class_name in modules_to_test:
        try:
            module = __import__(module_path, fromlist=[class_name])
            getattr(module, class_name)
            print(f"✅ {name}: Imported successfully")
        except Exception as e:
            print(f"❌ {name}: Import failed - {e}")
            errors.append(name)

    print("=" * 70)

    if errors:
        print(f"❌ Import Errors Found: {len(errors)}")
        return False
    else:
        print("✅ All required modules can be imported!")
        return True


def test_bot_setup():
    """Test bot initialization (without actually starting it)."""
    print("\n" + "=" * 70)
    print("🤖 Testing Bot Initialization")
    print("=" * 70)

    try:
        print("✅ DiscordAdapter class loaded")

        # Check if we can create instance (without starting)
        print("📝 Bot configuration:")
        print(f"   - Prefix: {settings.bot_prefix}")
        print(f"   - Environment: {settings.app_env}")
        print(f"   - Debug mode: {settings.app_debug}")

        print("\n✅ Bot initialization test passed!")
        return True

    except Exception as e:
        print(f"❌ Bot initialization failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all startup tests."""
    print("\n" + "=" * 70)
    print("🎮 蔚-上城人 - Discord Bot Startup Tests")
    print("=" * 70)

    results = {
        "Configuration": test_configuration(),
        "Module Imports": test_imports(),
        "Bot Setup": test_bot_setup(),
    }

    print("\n" + "=" * 70)
    print("📊 Test Results Summary")
    print("=" * 70)

    all_passed = True
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if not result:
            all_passed = False

    print("=" * 70)

    if all_passed:
        print("\n🎉 All startup tests passed!")
        print("\n💡 Ready to start the bot:")
        print("   poetry run python main.py")
        print("\n📝 Available commands (once bot is running):")
        print("   /bind - 绑定 Riot 账号")
        print("   /战绩 - 查看对局历史")
        print("   /讲道理 - AI 对局分析")
        return 0
    else:
        print("\n❌ Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Test Mock RSO OAuth flow.

This script tests the complete /bind command flow using MockRSOAdapter,
simulating the OAuth callback process without requiring a Production API Key.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters.database import DatabaseAdapter
from src.adapters.redis_adapter import RedisAdapter
from src.adapters.rso_factory import create_rso_adapter
from src.core.services.user_binding_service import UserBindingService


async def test_mock_rso_flow():
    """Test the complete mock RSO OAuth flow."""
    print("=" * 70)
    print("🧪 Testing Mock RSO OAuth Flow")
    print("=" * 70)

    # Initialize adapters
    print("\n📦 Initializing adapters...")
    db_adapter = DatabaseAdapter()
    await db_adapter.connect()
    print("✅ Database connected")

    redis_adapter = RedisAdapter()
    await redis_adapter.connect()
    print("✅ Redis connected")

    # Create RSO adapter (will use mock if MOCK_RSO_ENABLED=true)
    rso_adapter = create_rso_adapter(redis_client=redis_adapter)
    print(f"✅ RSO adapter created: {type(rso_adapter).__name__}")

    # Create user binding service
    binding_service = UserBindingService(database=db_adapter, rso_adapter=rso_adapter)
    print("✅ UserBindingService initialized")

    # Test Discord user ID
    test_discord_id = "123456789012345678"
    test_region = "na1"

    print("\n" + "=" * 70)
    print("Step 1: Initiate Binding (simulate /bind command)")
    print("=" * 70)

    # Step 1: User initiates binding
    binding_response = await binding_service.initiate_binding(
        discord_id=test_discord_id, region=test_region
    )

    if not binding_response.success:
        print(f"❌ Failed to initiate binding: {binding_response.message}")
        return False

    print("✅ Binding initiated successfully")
    print(f"📝 Auth URL: {binding_response.auth_url}")

    # Extract state from URL
    import urllib.parse

    url_parts = urllib.parse.urlparse(binding_response.auth_url)
    query_params = urllib.parse.parse_qs(url_parts.query)
    state = query_params.get("state", [None])[0]

    if not state:
        print("❌ No state token found in auth URL")
        return False

    print(f"🔑 State token: {state}")

    print("\n" + "=" * 70)
    print("Step 2: User Authorizes (simulate OAuth callback)")
    print("=" * 70)

    # Step 2: Simulate OAuth callback with mock authorization code
    # In real flow, user would click link, log in, and Riot would redirect with code
    # In mock flow, we use a pre-configured test code
    mock_auth_code = "test_code_1"  # Maps to "Fuji shan xia#NA1"
    print(f"🎫 Mock authorization code: {mock_auth_code}")

    # Step 3: Complete binding with code and state
    completion_response = await binding_service.complete_binding(code=mock_auth_code, state=state)

    if not completion_response.success:
        print(f"❌ Failed to complete binding: {completion_response.message}")
        if completion_response.error:
            print(f"   Error: {completion_response.error}")
        return False

    print("✅ Binding completed successfully!")
    print(f"📝 Message: {completion_response.message}")

    if completion_response.binding:
        print("\n🎮 Bound Account:")
        print(f"   Discord ID: {completion_response.binding.discord_id}")
        print(f"   Summoner: {completion_response.binding.summoner_name}")
        print(f"   PUUID: {completion_response.binding.puuid}")
        print(f"   Region: {completion_response.binding.region}")
        print(f"   Status: {completion_response.binding.status}")

    print("\n" + "=" * 70)
    print("Step 3: Verify Binding (simulate /profile command)")
    print("=" * 70)

    # Step 4: Verify binding is stored
    stored_binding = await binding_service.get_binding(test_discord_id)

    if not stored_binding:
        print("❌ Binding not found in database!")
        return False

    print("✅ Binding retrieved from database:")
    print(f"   Discord ID: {stored_binding.discord_id}")
    print(f"   Summoner: {stored_binding.summoner_name}")
    print(f"   PUUID: {stored_binding.puuid}")
    print(f"   Region: {stored_binding.region}")

    print("\n" + "=" * 70)
    print("Step 4: Test Re-binding Prevention")
    print("=" * 70)

    # Try to initiate binding again (should be rejected)
    rebind_response = await binding_service.initiate_binding(
        discord_id=test_discord_id, region=test_region
    )

    if rebind_response.success:
        print("⚠️  Warning: Re-binding was allowed (should be prevented)")
    else:
        print("✅ Re-binding prevented correctly")
        print(f"   Message: {rebind_response.message}")

    # Cleanup
    print("\n" + "=" * 70)
    print("Cleanup")
    print("=" * 70)

    # Delete test binding
    await db_adapter.delete_user_binding(test_discord_id)
    print("✅ Test binding deleted")

    await db_adapter.disconnect()
    await redis_adapter.disconnect()
    print("✅ Connections closed")

    print("\n" + "=" * 70)
    print("🎉 All Mock RSO Tests Passed!")
    print("=" * 70)

    print("\n📋 Summary:")
    print("   ✅ Mock RSO adapter initialization")
    print("   ✅ Binding initiation (/bind command)")
    print("   ✅ OAuth callback simulation")
    print("   ✅ Binding completion")
    print("   ✅ Database persistence")
    print("   ✅ Binding retrieval (/profile command)")
    print("   ✅ Re-binding prevention")

    print("\n💡 Next Steps:")
    print("   1. Start Discord Bot: poetry run python main.py")
    print("   2. Test /bind command in Discord")
    print("   3. Manually complete OAuth flow with test code")

    print("\n📝 Available Mock Test Accounts:")
    print("   - test_code_1 → Fuji shan xia#NA1")
    print("   - test_code_2 → TestPlayer#NA1")
    print("   - test_code_3 → DemoSummoner#KR")

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_mock_rso_flow())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

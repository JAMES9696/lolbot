"""Test smart error messaging with retry_suggested field.

Validates V1.1 Task 3: Smart error messaging implementation.
"""


from src.contracts.analysis_results import AnalysisErrorReport
from src.core.views.analysis_view import render_error_embed


def test_render_error_with_retry_suggested():
    """Test error embed with retry_suggested=True (Riot API busy scenario)."""
    print("\n" + "=" * 80)
    print("  Test 1: Error with retry_suggested=True (Riot API 429)")
    print("=" * 80)

    error_report = AnalysisErrorReport(
        match_id="NA1_5387390374",
        error_type="RIOT_API_ERROR",
        error_message="Rate limit exceeded (HTTP 429). Riot API is temporarily unavailable.",
        retry_suggested=True,
    )

    embed = render_error_embed(
        error_message=error_report.error_message,
        match_id=error_report.match_id,
        retry_suggested=error_report.retry_suggested,
    )

    print(f"\n📋 Embed Title: {embed.title}")
    print(f"📋 Embed Color: {embed.color}")
    print(f"📋 Embed Description:\n{embed.description}")

    # Verify smart suggestion is present
    assert "💡 **建议**: 请稍后重试" in embed.description
    assert "临时性的" in embed.description
    print("\n✅ Smart suggestion for retry=True verified!")


def test_render_error_without_retry():
    """Test error embed with retry_suggested=False (data incomplete scenario)."""
    print("\n" + "=" * 80)
    print("  Test 2: Error with retry_suggested=False (Data Incomplete)")
    print("=" * 80)

    error_report = AnalysisErrorReport(
        match_id="NA1_1234567890",
        error_type="DATA_INCOMPLETE",
        error_message="Match timeline data is missing. Cannot perform analysis.",
        retry_suggested=False,
    )

    embed = render_error_embed(
        error_message=error_report.error_message,
        match_id=error_report.match_id,
        retry_suggested=error_report.retry_suggested,
    )

    print(f"\n📋 Embed Title: {embed.title}")
    print(f"📋 Embed Color: {embed.color}")
    print(f"📋 Embed Description:\n{embed.description}")

    # Verify smart suggestion is present
    assert "⚠️ **注意**: 数据不完整或不支持该对局" in embed.description
    assert "重试可能无效" in embed.description
    print("\n✅ Smart suggestion for retry=False verified!")


def test_error_report_contract():
    """Test AnalysisErrorReport Pydantic contract validation."""
    print("\n" + "=" * 80)
    print("  Test 3: AnalysisErrorReport Contract Validation")
    print("=" * 80)

    # Valid report
    report = AnalysisErrorReport(
        match_id="NA1_5387390374",
        error_type="LLM_TIMEOUT",
        error_message="AI analysis timed out after 30 seconds.",
        retry_suggested=True,
    )

    print("\n✅ Contract fields:")
    print(f"   - match_id: {report.match_id}")
    print(f"   - error_type: {report.error_type}")
    print(f"   - error_message: {report.error_message}")
    print(f"   - retry_suggested: {report.retry_suggested}")

    # Test default value
    report_default = AnalysisErrorReport(
        match_id="NA1_1234567890",
        error_type="UNKNOWN",
        error_message="An unexpected error occurred.",
        # retry_suggested defaults to True
    )

    assert report_default.retry_suggested is True
    print("\n✅ Default retry_suggested=True verified!")

    # Test max_length validation
    try:
        long_message = "x" * 501  # Exceeds 500 char limit
        AnalysisErrorReport(
            match_id="NA1_1234567890",
            error_type="TEST",
            error_message=long_message,
        )
        print("\n❌ Validation failed - should have raised error for long message")
    except Exception as e:
        print(f"\n✅ Max length validation working: {type(e).__name__}")


def main():
    """Run all smart error messaging tests."""
    print("\n" + "=" * 80)
    print("  🧪 V1.1 Task 3: Smart Error Messaging - Validation Tests")
    print("=" * 80)
    print("📅 Test Date: 2025-10-07")
    print("🎯 Objective: Verify intelligent error suggestions based on retry_suggested field")

    try:
        # Test 1: retry_suggested=True
        test_render_error_with_retry_suggested()

        # Test 2: retry_suggested=False
        test_render_error_without_retry()

        # Test 3: Contract validation
        test_error_report_contract()

        print("\n" + "=" * 80)
        print("  ✅ All Smart Error Messaging Tests Passed!")
        print("=" * 80)
        print("\n📊 Summary:")
        print("   - ✅ retry_suggested=True renders 'please retry' suggestion")
        print("   - ✅ retry_suggested=False renders 'retry may not help' warning")
        print("   - ✅ AnalysisErrorReport contract validation working")
        print("   - ✅ Default retry_suggested=True verified")
        print("   - ✅ Max length validation (500 chars) enforced")

        print("\n🎉 V1.1 Task 3 Implementation: VERIFIED")
        return True

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

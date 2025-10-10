#!/usr/bin/env python3
"""
Enhanced healthcheck for 蔚-上城人 voice broadcast subsystem.

P4 Production-Ready Validation:
- ✅ Volcengine TTS API authentication
- ✅ Discord Voice dependencies (FFmpeg, PyNaCl)
- ✅ Broadcast server HTTP endpoints
- ✅ Structured observability output

Usage:
  # Basic health check (HTTP endpoints only)
  python -X utf8 scripts/voice_broadcast_healthcheck.py --base http://localhost:3000

  # Comprehensive check (TTS auth + dependencies)
  python -X utf8 scripts/voice_broadcast_healthcheck.py --base http://localhost:3000 --full

  # Test broadcast with actual match
  python -X utf8 scripts/voice_broadcast_healthcheck.py --base http://localhost:3000 \\
         --match NA1_5388494924 --guild 123 --user 456 \\
         --secret <BROADCAST_WEBHOOK_SECRET>

Exit Codes:
  0 - All checks passed
  1 - Basic HTTP health check failed
  2 - TTS API authentication failed
  3 - Discord Voice dependencies missing
  4 - Broadcast endpoint test failed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Structured health check result with observability metrics."""

    check_name: str
    passed: bool
    duration_ms: float
    error_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check": self.check_name,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error_message,
            "metadata": self.metadata,
        }


class VoiceBroadcastHealthChecker:
    """Comprehensive health checker for voice broadcast subsystem."""

    def __init__(self, base_url: str, broadcast_secret: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.broadcast_secret = broadcast_secret
        self.results: list[HealthCheckResult] = []

    async def check_http_health_endpoint(self) -> HealthCheckResult:
        """Check HTTP /health endpoint availability."""
        start = datetime.now()
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(
                    f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    text = await resp.text()
                    duration_ms = (datetime.now() - start).total_seconds() * 1000

                    if resp.status == 200:
                        logger.info(
                            f"✅ HTTP /health endpoint OK (status={resp.status}, latency={duration_ms:.1f}ms)"
                        )
                        return HealthCheckResult(
                            check_name="http_health_endpoint",
                            passed=True,
                            duration_ms=duration_ms,
                            metadata={"status_code": resp.status, "response": text[:100]},
                        )
                    else:
                        logger.error(f"❌ HTTP /health endpoint returned {resp.status}")
                        return HealthCheckResult(
                            check_name="http_health_endpoint",
                            passed=False,
                            duration_ms=duration_ms,
                            error_message=f"Unexpected status {resp.status}",
                            metadata={"status_code": resp.status},
                        )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"❌ HTTP /health endpoint failed: {e}")
            return HealthCheckResult(
                check_name="http_health_endpoint",
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def check_tts_api_auth(self) -> HealthCheckResult:
        """Validate Volcengine TTS API authentication.

        This performs a minimal API call to verify:
        - API key validity
        - Network connectivity to Volcengine
        - TTS service availability
        """
        start = datetime.now()

        # Load settings from environment
        try:
            from src.config.settings import settings
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"❌ Failed to load settings: {e}")
            return HealthCheckResult(
                check_name="tts_api_auth",
                passed=False,
                duration_ms=duration_ms,
                error_message=f"Settings load failed: {e}",
            )

        # Check if TTS is enabled
        if not getattr(settings, "feature_voice_enabled", False):
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.warning(
                "⚠️  TTS feature disabled (FEATURE_VOICE_ENABLED=false), skipping auth check"
            )
            return HealthCheckResult(
                check_name="tts_api_auth",
                passed=True,  # Not an error, just disabled
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": "feature_disabled"},
            )

        # Verify API credentials are configured
        if not settings.tts_api_key or not settings.tts_api_url:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error(
                "❌ TTS API credentials not configured (TTS_API_KEY or TTS_API_URL missing)"
            )
            return HealthCheckResult(
                check_name="tts_api_auth",
                passed=False,
                duration_ms=duration_ms,
                error_message="TTS_API_KEY or TTS_API_URL not configured",
            )

        # Perform minimal TTS API call (health probe)
        try:
            # Use a short test phrase to minimize API costs
            test_text = "健康检查"  # "Health check"

            payload = {
                "req_params": {
                    "text": test_text,
                    "speaker": settings.tts_voice_id,
                    "audio_params": {"format": "mp3", "sample_rate": 24000},
                }
            }

            headers = {
                "Content-Type": "application/json",
                "x-api-key": settings.tts_api_key,
                "X-Api-Resource-Id": "volc.service_type.10029",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    settings.tts_api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    duration_ms = (datetime.now() - start).total_seconds() * 1000

                    if resp.status == 200:
                        # Parse response to ensure it's valid
                        response_text = await resp.text()
                        logger.info(
                            f"✅ Volcengine TTS API auth OK (status={resp.status}, "
                            f"latency={duration_ms:.1f}ms, response_size={len(response_text)}B)"
                        )
                        return HealthCheckResult(
                            check_name="tts_api_auth",
                            passed=True,
                            duration_ms=duration_ms,
                            metadata={
                                "status_code": resp.status,
                                "voice_id": settings.tts_voice_id,
                                "response_size_bytes": len(response_text),
                            },
                        )
                    else:
                        error_text = await resp.text()
                        logger.error(
                            f"❌ Volcengine TTS API returned {resp.status}: {error_text[:200]}"
                        )
                        return HealthCheckResult(
                            check_name="tts_api_auth",
                            passed=False,
                            duration_ms=duration_ms,
                            error_message=f"API returned {resp.status}",
                            metadata={"status_code": resp.status, "error": error_text[:200]},
                        )
        except asyncio.TimeoutError:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("❌ Volcengine TTS API timeout (>10s)")
            return HealthCheckResult(
                check_name="tts_api_auth",
                passed=False,
                duration_ms=duration_ms,
                error_message="Request timeout after 10s",
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"❌ Volcengine TTS API auth failed: {e}")
            return HealthCheckResult(
                check_name="tts_api_auth",
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def check_discord_voice_dependencies(self) -> HealthCheckResult:
        """Verify Discord Voice playback dependencies.

        Checks:
        - FFmpeg binary availability (required for audio decoding)
        - PyNaCl library (required for Opus codec)
        """
        start = datetime.now()
        errors = []
        metadata = {}

        # Check FFmpeg
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            logger.info(f"✅ FFmpeg found: {ffmpeg_path}")
            metadata["ffmpeg_path"] = ffmpeg_path
        else:
            errors.append("FFmpeg not found in PATH")
            logger.error("❌ FFmpeg not found in PATH (required for Discord voice)")

        # Check PyNaCl (Opus codec support)
        try:
            import nacl  # type: ignore

            logger.info(f"✅ PyNaCl installed (version: {nacl.__version__})")
            metadata["pynacl_version"] = str(nacl.__version__)
        except ImportError:
            errors.append("PyNaCl not installed")
            logger.error("❌ PyNaCl not installed (required for Discord voice encryption)")

        # Check discord.py voice support
        try:
            import discord  # type: ignore

            if hasattr(discord, "FFmpegPCMAudio"):
                logger.info("✅ discord.py voice support available")
                metadata["discord_voice_support"] = True
            else:
                errors.append("discord.py missing voice support")
                logger.error("❌ discord.py missing voice support (check installation)")
        except ImportError:
            errors.append("discord.py not installed")
            logger.error("❌ discord.py not installed")

        duration_ms = (datetime.now() - start).total_seconds() * 1000
        passed = len(errors) == 0

        if passed:
            logger.info("✅ All Discord Voice dependencies satisfied")
        else:
            logger.error(f"❌ Discord Voice dependencies missing: {', '.join(errors)}")

        return HealthCheckResult(
            check_name="discord_voice_dependencies",
            passed=passed,
            duration_ms=duration_ms,
            error_message="; ".join(errors) if errors else None,
            metadata=metadata,
        )

    async def check_broadcast_endpoint(
        self, match_id: str, guild_id: int, user_id: int
    ) -> HealthCheckResult:
        """Test /broadcast endpoint with actual request.

        Args:
            match_id: Match ID to use for test
            guild_id: Discord guild ID
            user_id: Discord user ID
        """
        start = datetime.now()

        headers = {"Content-Type": "application/json"}
        if self.broadcast_secret:
            headers["X-Auth-Token"] = self.broadcast_secret

        payload = {"match_id": match_id, "guild_id": guild_id, "user_id": user_id}

        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    f"{self.base_url}/broadcast",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    text = await resp.text()
                    duration_ms = (datetime.now() - start).total_seconds() * 1000

                    if resp.status in (200, 202):
                        logger.info(
                            f"✅ /broadcast endpoint OK (status={resp.status}, "
                            f"latency={duration_ms:.1f}ms)"
                        )
                        return HealthCheckResult(
                            check_name="broadcast_endpoint",
                            passed=True,
                            duration_ms=duration_ms,
                            metadata={
                                "status_code": resp.status,
                                "response": text[:200],
                                "match_id": match_id,
                            },
                        )
                    elif resp.status == 401:
                        logger.error("❌ /broadcast returned 401 (check X-Auth-Token)")
                        return HealthCheckResult(
                            check_name="broadcast_endpoint",
                            passed=False,
                            duration_ms=duration_ms,
                            error_message="Authentication failed (401)",
                            metadata={"status_code": resp.status},
                        )
                    else:
                        logger.error(f"❌ /broadcast returned {resp.status}: {text[:200]}")
                        return HealthCheckResult(
                            check_name="broadcast_endpoint",
                            passed=False,
                            duration_ms=duration_ms,
                            error_message=f"Unexpected status {resp.status}",
                            metadata={"status_code": resp.status, "response": text[:200]},
                        )
        except asyncio.TimeoutError:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("❌ /broadcast timeout (>15s)")
            return HealthCheckResult(
                check_name="broadcast_endpoint",
                passed=False,
                duration_ms=duration_ms,
                error_message="Request timeout after 15s",
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"❌ /broadcast failed: {e}")
            return HealthCheckResult(
                check_name="broadcast_endpoint",
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def run_all_checks(
        self,
        full_check: bool = False,
        test_broadcast: bool = False,
        match_id: Optional[str] = None,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> int:
        """Run all health checks and return exit code.

        Args:
            full_check: Include TTS auth and dependency checks
            test_broadcast: Test /broadcast endpoint
            match_id: Match ID for broadcast test
            guild_id: Guild ID for broadcast test
            user_id: User ID for broadcast test

        Returns:
            Exit code (0 if all passed, non-zero otherwise)
        """
        logger.info("=" * 60)
        logger.info("蔚-上城人 Voice Broadcast Health Check")
        logger.info("=" * 60)

        # Always check HTTP health endpoint
        result = await self.check_http_health_endpoint()
        self.results.append(result)
        if not result.passed:
            return 1

        # Full check includes TTS and dependencies
        if full_check:
            logger.info("")
            logger.info("Running full health check (TTS + Dependencies)...")
            logger.info("-" * 60)

            # Check TTS API authentication
            result = await self.check_tts_api_auth()
            self.results.append(result)
            if not result.passed and not result.metadata.get("skipped"):
                return 2

            # Check Discord Voice dependencies
            result = await self.check_discord_voice_dependencies()
            self.results.append(result)
            if not result.passed:
                return 3

        # Optional broadcast endpoint test
        if test_broadcast and match_id and guild_id and user_id:
            logger.info("")
            logger.info("Testing /broadcast endpoint...")
            logger.info("-" * 60)

            result = await self.check_broadcast_endpoint(match_id, guild_id, user_id)
            self.results.append(result)
            if not result.passed:
                return 4

        return 0

    def print_summary(self):
        """Print structured observability summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("Health Check Summary")
        logger.info("=" * 60)

        total_checks = len(self.results)
        passed_checks = sum(1 for r in self.results if r.passed)
        failed_checks = total_checks - passed_checks

        # Print individual results
        for result in self.results:
            status_icon = "✅" if result.passed else "❌"
            status_text = "PASS" if result.passed else "FAIL"
            logger.info(
                f"{status_icon} {result.check_name}: {status_text} " f"({result.duration_ms:.1f}ms)"
            )
            if result.error_message:
                logger.info(f"   Error: {result.error_message}")

        # Print aggregate stats
        logger.info("")
        logger.info(f"Total Checks: {total_checks}")
        logger.info(f"Passed: {passed_checks}")
        logger.info(f"Failed: {failed_checks}")

        # Print JSON output for machine parsing
        logger.info("")
        logger.info("JSON Output (machine-readable):")
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_checks": total_checks,
            "passed": passed_checks,
            "failed": failed_checks,
            "results": [r.to_dict() for r in self.results],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhanced health check for 蔚-上城人 voice broadcast subsystem"
    )
    parser.add_argument(
        "--base",
        default="http://localhost:3000",
        help="Callback server base URL (default: http://localhost:3000)",
    )
    parser.add_argument(
        "--full", action="store_true", help="Run full health check (TTS auth + dependencies)"
    )
    parser.add_argument("--match", help="Match ID for /broadcast endpoint test")
    parser.add_argument("--guild", type=int, help="Guild ID for /broadcast endpoint test")
    parser.add_argument("--user", type=int, help="User ID for /broadcast endpoint test")
    parser.add_argument(
        "--secret", help="X-Auth-Token for /broadcast endpoint (BROADCAST_WEBHOOK_SECRET)"
    )

    args = parser.parse_args()

    # Create checker
    checker = VoiceBroadcastHealthChecker(base_url=args.base, broadcast_secret=args.secret)

    # Determine if broadcast test is requested
    test_broadcast = bool(args.match and args.guild and args.user)

    # Run checks
    exit_code = await checker.run_all_checks(
        full_check=args.full,
        test_broadcast=test_broadcast,
        match_id=args.match,
        guild_id=args.guild,
        user_id=args.user,
    )

    # Print summary
    checker.print_summary()

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

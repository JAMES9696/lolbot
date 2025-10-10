"""RSO OAuth callback + Feedback HTTP server (aiohttp).

Endpoints:
- GET /callback            → Handles RSO OAuth callback
- GET /mock-oauth         → Dev helper page for Mock RSO flow (select test code)
- GET /health              → Liveness probe
- GET /metrics             → Prometheus exposition
- POST /api/v1/feedback    → Receives feedback events from CLI 1

Critical handlers are traced via `llm_debug_wrapper` for production
observability (RSO and feedback flows).
"""

import logging
from typing import Any

from aiohttp import web

from src.adapters.database import DatabaseAdapter
from src.adapters.redis_adapter import RedisAdapter
from src.adapters.rso_adapter import RSOAdapter
from src.adapters.tts_adapter import TTSAdapter, TTSError
from src.config.settings import get_settings
from src.core.observability import clear_correlation_id, llm_debug_wrapper, set_correlation_id

logger = logging.getLogger(__name__)


class RSOCallbackServer:
    """HTTP server for handling RSO OAuth callbacks."""

    def __init__(
        self,
        rso_adapter: RSOAdapter,
        db_adapter: DatabaseAdapter,
        redis_adapter: RedisAdapter,
        discord_adapter: Any | None = None,
    ) -> None:
        """Initialize callback server.

        Args:
            rso_adapter: RSO OAuth adapter
            db_adapter: Database adapter for storing bindings
            redis_adapter: Redis adapter for state validation
        """
        self.rso = rso_adapter
        self.db = db_adapter
        self.redis = redis_adapter
        self.app = web.Application()
        self.discord_adapter = discord_adapter
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup HTTP routes."""
        self.app.router.add_get("/callback", self.handle_callback)
        # Dev-only mock OAuth entry (used by MockRSOAdapter)
        # Renders a simple page to choose a test authorization code and redirects to /callback
        self.app.router.add_get("/mock-oauth", self.handle_mock_oauth)
        self.app.router.add_get("/health", self.health_check)
        # /metrics endpoint for Prometheus scraping
        self.app.router.add_get("/metrics", self.metrics)
        # Optional tournament callback/broadcast (dev/testing)
        self.app.router.add_post("/riot/tournament_callback", self.riot_tournament_callback)
        self.app.router.add_post("/broadcast", self.trigger_broadcast)
        # Alertmanager → Discord bridge (webhook translator)
        self.app.router.add_post("/alerts", self.alert_webhook)
        # Feedback collection endpoint (CLI 1 → CLI 2)
        self.app.router.add_post("/api/v1/feedback", self.handle_feedback)

        # Serve generated static assets (e.g., TTS audio) via callback server
        try:
            from pathlib import Path

            settings = get_settings()
            audio_dir = Path(settings.audio_storage_path)
            if not audio_dir.is_absolute():
                audio_dir = Path.cwd() / audio_dir
            if audio_dir.exists():
                # Mount at /static/audio/... so existing URLs keep working
                self.app.router.add_static("/static/audio/", audio_dir, show_index=False)
                logger.info(f"Serving static audio from {audio_dir}")
            else:
                logger.warning(
                    "Audio storage directory %s does not exist; static route not registered",
                    audio_dir,
                )
        except Exception as exc:
            logger.error(f"Failed to configure static audio route: {exc}")

    @llm_debug_wrapper(
        capture_result=False,
        capture_args=True,
        log_level="INFO",
        add_metadata={"flow": "rso_oauth", "endpoint": "/callback"},
        warn_over_ms=700,
    )
    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle RSO OAuth callback.

        This endpoint receives the authorization code from Riot and:
        1. Validates the state token (CSRF protection)
        2. Exchanges code for Riot account info
        3. Saves binding to database
        4. Returns success/error page
        """
        try:
            # Extract OAuth parameters
            code = request.query.get("code")
            state = request.query.get("state")
            error = request.query.get("error")

            # Check for OAuth errors
            if error:
                logger.warning(f"OAuth error: {error}")
                return web.Response(
                    text=self._error_page(f"Authorization failed: {error}"),
                    content_type="text/html",
                    status=400,
                )

            # Validate required parameters
            if not code or not state:
                logger.warning("Missing code or state parameter")
                return web.Response(
                    text=self._error_page("Invalid callback parameters"),
                    content_type="text/html",
                    status=400,
                )

            # Validate state token (CSRF protection)
            discord_id = await self.rso.validate_state(state)
            if not discord_id:
                logger.warning(f"Invalid state token: {state}")
                return web.Response(
                    text=self._error_page("Invalid or expired authorization request"),
                    content_type="text/html",
                    status=400,
                )

            logger.info(f"Valid callback for Discord ID {discord_id}")

            # Exchange code for Riot account info
            riot_account = await self.rso.exchange_code(code)
            if not riot_account:
                logger.error("Failed to exchange authorization code")
                return web.Response(
                    text=self._error_page("Failed to retrieve Riot account information"),
                    content_type="text/html",
                    status=500,
                )

            # Save binding to database
            summoner_name = f"{riot_account.game_name}#{riot_account.tag_line}"
            success = await self.db.save_user_binding(
                discord_id=discord_id,
                puuid=riot_account.puuid,
                summoner_name=summoner_name,
            )

            if not success:
                logger.error(f"Failed to save binding for {discord_id}")
                return web.Response(
                    text=self._error_page("Failed to save account binding"),
                    content_type="text/html",
                    status=500,
                )

            # Success! Return confirmation page
            logger.info(f"Successfully bound {discord_id} to {summoner_name}")
            return web.Response(
                text=self._success_page(summoner_name),
                content_type="text/html",
            )

        except Exception as e:
            logger.error(f"Unexpected error in callback handler: {e}", exc_info=True)
            return web.Response(
                text=self._error_page("An unexpected error occurred"),
                content_type="text/html",
                status=500,
            )

    async def handle_mock_oauth(self, request: web.Request) -> web.Response:
        """Render a mock OAuth selection page or fast-redirect to /callback.

        Query params (generated by MockRSOAdapter.generate_auth_url):
          - state: CSRF token stored in Redis for this auth flow
          - discord_id: (informational) user id initiating the bind
          - region: preferred region (unused by callback)
          - code (optional): if present, immediately redirect to /callback

        Behavior:
          - When ?code= is present, issue 302 to /callback with (code,state)
          - Otherwise, render a small HTML page listing available test codes
            (if adapter supports list_test_accounts()), and a manual input form
            that submits to /callback via GET.
        """
        try:
            state = (request.query.get("state") or "").strip()
            discord_id = (request.query.get("discord_id") or "").strip()
            region = (request.query.get("region") or "na1").strip()
            code = (request.query.get("code") or "").strip()

            # Minimal validation: state is required to proceed
            if not state:
                return web.Response(
                    text=self._error_page("Missing state parameter for mock OAuth"),
                    content_type="text/html",
                    status=400,
                )

            # Fast path: redirect to /callback when code provided
            if code:
                location = f"/callback?state={state}&code={code}"
                raise web.HTTPFound(location=location)

            # Try to enumerate available mock codes (if supported by adapter)
            mock_codes: list[tuple[str, str]] = []
            try:
                if hasattr(self.rso, "list_test_accounts"):
                    accounts = self.rso.list_test_accounts()
                    # (code, label) where label shows summoner for clarity
                    for c, acct in list(accounts.items())[:10]:
                        label = f"{getattr(acct, 'game_name', 'Test')}#{getattr(acct, 'tag_line', 'NA1')}"
                        mock_codes.append((c, label))
            except Exception:
                # Non-fatal: fall back to well-known defaults
                pass
            if not mock_codes:
                mock_codes = [
                    ("test_code_1", "TestAccount1#NA1"),
                    ("test_code_2", "TestAccount2#NA1"),
                    ("test_code_3", "DemoSummoner#KR"),
                ]

            # Render simple HTML with quick links and manual form
            links_html = "\n".join(
                [
                    f'<li><a href="/callback?state={state}&code={c}">Authorize as {label} (code: {c})</a></li>'
                    for c, label in mock_codes
                ]
            )

            page = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Mock OAuth – Select Test Account</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }}
    .wrap {{ max-width:720px; margin:40px auto; padding:24px; background:#111827; border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,.4); }}
    h1 {{ margin:0 0 8px; font-size:24px; }}
    p.meta {{ color:#94a3b8; margin:0 0 16px; font-size:14px; }}
    ul {{ line-height:1.8; }}
    a {{ color:#60a5fa; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    form {{ margin-top:16px; display:flex; gap:8px; }}
    input[type=text] {{ flex:1; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0b1220; color:#e2e8f0; }}
    button {{ padding:10px 16px; border-radius:8px; border:0; background:#3b82f6; color:white; cursor:pointer; }}
    button:hover {{ background:#2563eb; }}
    code {{ background:#0b1220; padding:2px 6px; border-radius:6px; }}
  </style>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <script>/* no scripts required */</script>
  </head>
<body>
  <div class=\"wrap\">
    <h1>Mock OAuth – Select Test Account</h1>
    <p class=\"meta\">state=<code>{state}</code> · discord_id=<code>{discord_id or 'unknown'}</code> · region=<code>{region}</code></p>
    <h3>Quick Picks</h3>
    <ul>
      {links_html}
    </ul>
    <h3>Or enter a mock code</h3>
    <form method=\"GET\" action=\"/callback\">
      <input type=\"hidden\" name=\"state\" value=\"{state}\" />
      <input type=\"text\" name=\"code\" placeholder=\"e.g. test_code_1 or test_abc\" required />
      <button type=\"submit\">Authorize</button>
    </form>
  </div>
</body>
</html>
"""
            return web.Response(text=page, content_type="text/html")
        except web.HTTPException:
            # Propagate redirects
            raise
        except Exception as e:
            logger.error(f"Unexpected error in mock-oauth handler: {e}", exc_info=True)
            return web.Response(
                text=self._error_page("An unexpected error occurred"),
                content_type="text/html",
                status=500,
            )

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    @llm_debug_wrapper(
        capture_result=True,
        capture_args=True,
        log_level="INFO",
        add_metadata={"flow": "feedback", "endpoint": "/api/v1/feedback"},
        warn_over_ms=400,
    )
    async def handle_feedback(self, request: web.Request) -> web.Response:
        """Receive and persist feedback events from CLI 1.

        Expected JSON payload (minimum fields):
            {
              "match_id": str,
              "user_id": str,
              "feedback_type": "up"|"down"|"star"|"thumbs_up"|"thumbs_down"|"report",
              "prompt_variant": "A"|"B",
              "interaction_id": str (optional),
              "comment": str (optional),
              "variant_id": str (optional)
            }
        """
        try:
            data = await request.json()

            match_id = str(data.get("match_id", "")).strip()
            user_id = str(data.get("user_id", data.get("discord_user_id", ""))).strip()
            fb_type_raw = str(data.get("feedback_type", "")).strip().lower()
            variant = data.get("prompt_variant")

            if not match_id or not user_id or not fb_type_raw:
                return web.json_response(
                    {"ok": False, "error": "missing required fields"}, status=400
                )

            mapping = {
                "up": "thumbs_up",
                "down": "thumbs_down",
                "star": "star",
                "thumbs_up": "thumbs_up",
                "thumbs_down": "thumbs_down",
                "report": "report",
            }
            fb_type = mapping.get(fb_type_raw)
            if fb_type is None:
                return web.json_response(
                    {"ok": False, "error": f"invalid feedback_type: {fb_type_raw}"}, status=400
                )

            value_map = {"thumbs_up": 1, "thumbs_down": -1, "star": 2}
            feedback_value = value_map.get(fb_type)

            payload = {
                "match_id": match_id,
                "discord_user_id": user_id,
                "feedback_type": fb_type,
                "prompt_variant": variant,
                "variant_id": data.get("variant_id"),
                "feedback_value": feedback_value,
                "feedback_comment": data.get("comment") or data.get("feedback_comment"),
                "interaction_id": data.get("interaction_id"),
            }

            ok = await self.db.insert_feedback_event(payload)
            if not ok:
                return web.json_response({"ok": False, "error": "db_error"}, status=500)

            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"Unexpected error in feedback handler: {e}", exc_info=True)
            return web.json_response({"ok": False, "error": "exception"}, status=500)

    async def metrics(self, request: web.Request) -> web.Response:
        """Prometheus metrics endpoint.

        KISS: Pull dynamic gauges on demand to avoid background schedulers.
        """
        try:
            from src.core.metrics import render_latest, update_dynamic_gauges

            # Refresh gauges that require external queries (e.g., Redis LLEN)
            await update_dynamic_gauges()

            payload, content_type = render_latest()
            return web.Response(body=payload, headers={"Content-Type": content_type})
        except Exception as e:  # pragma: no cover - metrics must not break server
            logger.error(f"/metrics handler error: {e}")
            return web.Response(status=500, text="metrics unavailable")

    def _authorize_broadcast(self, request: web.Request) -> bool:
        """Authorize broadcast/tournament callbacks using BROADCAST_WEBHOOK_SECRET."""
        settings = get_settings()
        token = request.headers.get("X-Auth-Token") or request.query.get("token")
        expected = getattr(settings, "broadcast_webhook_secret", None)
        return bool(expected and token and token == expected)

    def _authorize_alert(self, request: web.Request) -> bool:
        """Authorize Alertmanager webhooks using ALERT_WEBHOOK_SECRET.

        Supports both:
        - X-Auth-Token: <token>
        - Authorization: Bearer <token>
        and keeps `?token=` query fallback for compatibility.
        """
        settings = get_settings()
        # Header first (custom header)
        token = request.headers.get("X-Auth-Token")
        # Authorization: Bearer <token>
        if not token:
            auth = request.headers.get("Authorization")
            if isinstance(auth, str) and auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        # Query fallback (backward compatibility)
        if not token:
            token = request.query.get("token")

        expected = getattr(settings, "alert_webhook_secret", None)
        return bool(expected and token and token == expected)

    async def riot_tournament_callback(self, request: web.Request) -> web.Response:
        """Handle Riot Tournament callback (simplified).

        Expected JSON: {"match_id": "NA1_123", "guild_id": 123, "voice_channel_id": 456}
        Requires header X-Auth-Token to match BROADCAST_WEBHOOK_SECRET.
        """
        if not self._authorize_broadcast(request):
            return web.Response(status=401, text="unauthorized")

        data = await request.json()
        match_id = str(data.get("match_id"))
        guild_id = int(data.get("guild_id"))
        channel_id = int(data.get("voice_channel_id"))

        ok, msg = await self._broadcast_match_tts(guild_id, channel_id, match_id)
        return web.json_response({"ok": ok, "message": msg})

    async def trigger_broadcast(self, request: web.Request) -> web.Response:
        """Manual broadcast endpoint for testing.

        JSON body: {"audio_url": "https://...", "guild_id": 123, "voice_channel_id": 456}
        or:        {"match_id": "NA1_...", "guild_id": 123, "voice_channel_id": 456}
        or:        {"match_id"|"audio_url": ..., "guild_id": 123, "user_id": 789}  # join user's channel
        """
        correlation_token: str | None = None
        try:
            if not self._authorize_broadcast(request):
                return web.Response(status=401, text="unauthorized")

            data = await request.json()
            audio_url = data.get("audio_url")
            guild_id = int(data.get("guild_id"))
            channel_id_raw = data.get("voice_channel_id")
            channel_id = int(channel_id_raw) if channel_id_raw is not None else -1
            user_id = int(data.get("user_id")) if data.get("user_id") is not None else None

            match_for_trace = data.get("match_id") or audio_url or "unknown"
            correlation_token = f"broadcast:{guild_id}:{match_for_trace}"
            set_correlation_id(correlation_token)

            if audio_url:
                if channel_id > 0:
                    # Prefer per‑guild queue if available
                    if self.discord_adapter and self.discord_adapter.voice_broadcast:
                        success = await self.discord_adapter.enqueue_tts_playback(
                            guild_id=guild_id,
                            voice_channel_id=channel_id,
                            audio_url=audio_url,
                        )
                        if success:
                            logger.info(
                                "tts_url_enqueued_successfully",
                                extra={"guild_id": guild_id, "channel_id": channel_id},
                            )
                            return web.json_response({"ok": True, "queued": True})
                        logger.warning(
                            "voice_enqueue_failed_fallback_to_direct",
                            extra={"guild_id": guild_id, "channel_id": channel_id},
                        )
                        # Fallback to direct playback
                    ok = await self._play_audio(guild_id, channel_id, audio_url)
                    return web.json_response({"ok": ok, "queued": False})
                if user_id is not None:
                    if not self.discord_adapter:
                        return web.json_response({"ok": False, "error": "no_discord_adapter"})
                    ok = await self.discord_adapter.play_tts_to_user_channel(
                        guild_id=guild_id,
                        user_id=user_id,
                        audio_url=audio_url,
                    )
                    return web.json_response({"ok": ok, "by_user": True})
                return web.json_response({"ok": False, "error": "no_channel_or_user"})

            match_id = str(data.get("match_id"))
            logger.info(
                "broadcast_tts_request",
                extra={"match_id": match_id, "guild_id": guild_id, "channel_id": channel_id},
            )
            ok, msg = await self._broadcast_match_tts(guild_id, channel_id, match_id)
            logger.info(
                "broadcast_tts_result", extra={"match_id": match_id, "ok": ok, "status": msg}
            )
            return web.json_response({"ok": ok, "message": msg})
        finally:
            if correlation_token:
                clear_correlation_id()

    async def alert_webhook(self, request: web.Request) -> web.Response:
        """Accept Alertmanager webhook and forward to Discord webhook.

        Requires ALERT_WEBHOOK_SECRET via X-Auth-Token or token query param.
        """
        if not self._authorize_alert(request):
            return web.Response(status=401, text="unauthorized")

        settings = get_settings()
        if not settings or not getattr(settings, "alerts_discord_webhook", None):
            return web.Response(status=503, text="discord webhook not configured")

        payload = await request.json()
        alerts = payload.get("alerts", []) if isinstance(payload, dict) else []
        if not isinstance(alerts, list):
            alerts = []

        # Build Discord message content (compact)
        lines: list[str] = []
        status = payload.get("status")
        lines.append(f"Alertmanager status: {status}")
        for a in alerts[:10]:
            name = a.get("labels", {}).get("alertname", "alert")
            sev = a.get("labels", {}).get("severity", "info")
            svc = a.get("labels", {}).get("service", "-")
            summary = a.get("annotations", {}).get("summary", "")
            desc = a.get("annotations", {}).get("description", "")
            lines.append(f"[{sev}] {name} | service={svc} | {summary} — {desc}")

        content = "\n".join(lines)[:1800]

        # Send to Discord webhook
        try:
            import aiohttp

            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    settings.alerts_discord_webhook,
                    json={"content": content or "(empty alert)"},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status >= 300:
                        txt = await resp.text()
                        logger.error(f"Discord webhook failed: {resp.status} {txt}")
                        return web.Response(status=500, text="discord send failed")
        except Exception as e:
            logger.error(f"Discord webhook error: {e}")
            return web.Response(status=500, text="discord error")

        return web.json_response({"ok": True})

    async def _broadcast_match_tts(
        self, guild_id: int, channel_id: int, match_id: str
    ) -> tuple[bool, str]:
        """Lookup TTS audio by match and broadcast in a voice channel.

        If TTS not present, synthesize from stored narrative and persist URL.
        """
        logger.info(
            "_broadcast_match_tts_started",
            extra={"match_id": match_id, "guild_id": guild_id, "channel_id": channel_id},
        )
        # Fetch analysis
        analysis = await self.db.get_analysis_result(match_id)
        if not analysis:
            logger.warning("analysis_not_found", extra={"match_id": match_id})
            return False, "analysis_not_found"

        audio_url = None
        meta = analysis.get("llm_metadata") or {}
        if isinstance(meta, str):
            import json

            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        audio_url = meta.get("tts_audio_url") if isinstance(meta, dict) else None
        if audio_url:
            logger.info(
                "tts_audio_url_found_in_cache", extra={"match_id": match_id, "audio_url": audio_url}
            )

        # If no audio yet, try to synthesize from narrative
        if not audio_url:
            logger.info("tts_audio_url_missing_synthesizing", extra={"match_id": match_id})
            narrative = analysis.get("llm_narrative")
            tts_summary = None
            if isinstance(meta, dict):
                summary_candidate = meta.get("tts_summary")
                if isinstance(summary_candidate, str) and summary_candidate.strip():
                    tts_summary = summary_candidate.strip()
            if not narrative:
                logger.warning("no_narrative_for_tts", extra={"match_id": match_id})
                return False, "no_narrative"
            try:
                tts = TTSAdapter()
                logger.info("tts_synthesis_starting", extra={"match_id": match_id})
                # Prefer low-latency streaming if enabled
                if get_settings().feature_voice_streaming_enabled and self.discord_adapter:
                    logger.info("using_streaming_mode", extra={"match_id": match_id})
                    speech_source = tts_summary or narrative
                    audio_bytes: bytes | None = None
                    try:
                        audio_bytes = await tts.synthesize_speech_to_bytes(
                            speech_source, (meta or {}).get("emotion")
                        )
                    except TTSError as err:
                        logger.warning(
                            "TTS streaming mode timed out; falling back to URL",
                            extra={"match_id": match_id, "error": str(err)},
                        )
                    except Exception as e:
                        logger.error(
                            "TTS synthesis failed (streaming mode)",
                            extra={"match_id": match_id, "error": str(e)},
                            exc_info=True,
                        )
                    else:
                        # Enqueue via broadcast queue when available, otherwise play immediately
                        if self.discord_adapter.voice_broadcast:
                            logger.info(
                                "enqueueing_tts_to_broadcast_queue", extra={"match_id": match_id}
                            )
                            success = await self.discord_adapter.enqueue_tts_playback_bytes(
                                guild_id=guild_id,
                                voice_channel_id=channel_id,
                                audio_bytes=audio_bytes,
                            )
                            if success:
                                logger.info(
                                    "tts_enqueued_successfully", extra={"match_id": match_id}
                                )
                                return True, "stream_enqueued"
                            logger.warning(
                                "tts_enqueue_bytes_failed_fallback",
                                extra={"match_id": match_id, "guild_id": guild_id},
                            )
                            # Fall through to direct playback below
                        logger.info("playing_tts_bytes_directly", extra={"match_id": match_id})
                        ok = await self.discord_adapter.play_tts_bytes_in_voice_channel(
                            guild_id=guild_id,
                            voice_channel_id=channel_id,
                            audio_bytes=audio_bytes,
                        )
                        logger.info(
                            "tts_bytes_playback_result", extra={"match_id": match_id, "ok": ok}
                        )
                        return ok, ("ok" if ok else "voice_play_failed")

                # Fallback to URL-based synthesis and persistence
                logger.info("using_url_mode", extra={"match_id": match_id})
                speech_source = tts_summary or narrative
                audio_url = await tts.synthesize_speech_to_url(
                    speech_source, (meta or {}).get("emotion")
                )
                if audio_url:
                    logger.info(
                        "tts_url_synthesis_successful",
                        extra={"match_id": match_id, "audio_url": audio_url},
                    )
                    updated_meta: dict[str, Any] = {**(meta or {}), "tts_audio_url": audio_url}
                    if tts_summary:
                        updated_meta["tts_summary"] = tts_summary
                    await self.db.update_llm_narrative(
                        match_id,
                        llm_narrative=narrative,
                        llm_metadata=updated_meta,
                    )
            except TTSError as e:
                logger.warning(
                    "TTS synthesis failed (URL mode)",
                    extra={"match_id": match_id, "error": str(e)},
                )
                return False, "tts_failed"
            except Exception as e:
                logger.error(
                    "TTS synthesis failed (URL mode)",
                    extra={"match_id": match_id, "error": str(e)},
                    exc_info=True,
                )
                return False, "tts_failed"

        if not audio_url:
            logger.error("audio_still_missing_after_synthesis", extra={"match_id": match_id})
            return False, "audio_missing"

        logger.info(
            "attempting_audio_playback", extra={"match_id": match_id, "audio_url": audio_url}
        )
        ok = await self._play_audio(guild_id, channel_id, audio_url)
        return ok, ("ok" if ok else "voice_play_failed")

    async def _play_audio(self, guild_id: int, channel_id: int, audio_url: str) -> bool:
        if not self.discord_adapter:
            logger.error("Discord adapter not attached; cannot play audio")
            return False
        try:
            return await self.discord_adapter.play_tts_in_voice_channel(
                guild_id=guild_id, voice_channel_id=channel_id, audio_url=audio_url
            )
        except Exception:
            logger.exception("Discord voice playback failed")
            return False

    def _success_page(self, summoner_name: str) -> str:
        """Generate success HTML page."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Binding Successful</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .container {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
        }}
        .success-icon {{
            font-size: 4rem;
            margin-bottom: 1rem;
        }}
        h1 {{ color: #10b981; margin: 0.5rem 0; }}
        p {{ color: #6b7280; margin: 1rem 0; }}
        .summoner {{
            font-weight: bold;
            color: #667eea;
            font-size: 1.2rem;
        }}
        .close-btn {{
            margin-top: 1.5rem;
            padding: 0.75rem 2rem;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1rem;
        }}
        .close-btn:hover {{ background: #5568d3; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>Binding Successful!</h1>
        <p>Your Discord account has been linked to:</p>
        <p class="summoner">{summoner_name}</p>
        <p>You can now close this window and return to Discord.</p>
        <button class="close-btn" onclick="window.close()">Close Window</button>
    </div>
</body>
</html>
"""

    def _error_page(self, error_message: str) -> str:
        """Generate error HTML page."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Binding Failed</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}
        .container {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
        }}
        .error-icon {{
            font-size: 4rem;
            margin-bottom: 1rem;
        }}
        h1 {{ color: #ef4444; margin: 0.5rem 0; }}
        p {{ color: #6b7280; margin: 1rem 0; }}
        .retry-btn {{
            margin-top: 1.5rem;
            padding: 0.75rem 2rem;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1rem;
        }}
        .retry-btn:hover {{ background: #dc2626; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">✗</div>
        <h1>Binding Failed</h1>
        <p>{error_message}</p>
        <p>Please return to Discord and try again using <code>/bind</code>.</p>
        <button class="retry-btn" onclick="window.close()">Close Window</button>
    </div>
</body>
</html>
"""

    async def start(self, host: str = "0.0.0.0", port: int = 3000) -> None:
        """Start the HTTP server.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"RSO callback server started on {host}:{port}")

    async def stop(self) -> None:
        """Stop the HTTP server."""
        await self.app.cleanup()
        logger.info("RSO callback server stopped")

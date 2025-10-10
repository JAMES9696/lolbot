# Real RSO (Riot OAuth) – E2E Test Plan

This guide switches from Mock RSO to the real Riot OAuth flow and validates the end‑to‑end user journey: /bind → OAuth → /callback → DB upsert → /profile → /analyze → /team-analyze → webhook delivery.

## 0) Prereqs
- PostgreSQL and Redis running (see `docker-compose.yml`).
- Riot credentials issued (OAuth Client ID/Secret). Do NOT commit secrets.
- A valid `RIOT_API_KEY` (rate-limit aware).
- Discord bot added to a test guild with application commands enabled.

## 1) Configure `.env`
Set the following (example values shown as placeholders):

```
APP_ENV=development
APP_DEBUG=true
APP_LOG_LEVEL=INFO

MOCK_RSO_ENABLED=false
SECURITY_RSO_CLIENT_ID=<your_client_id>
SECURITY_RSO_CLIENT_SECRET=<your_client_secret>
# For local dev you may keep HTTP; consider HTTPS/ngrok for real users
SECURITY_RSO_REDIRECT_URI=http://localhost:3000/callback

RIOT_API_KEY=<your_riot_api_key>

DISCORD_BOT_TOKEN=<your_discord_bot_token>
DISCORD_APPLICATION_ID=<your_application_id>

# Enable V2 features for testing
FEATURE_AI_ANALYSIS_ENABLED=true
FEATURE_TEAM_ANALYSIS_ENABLED=true
FEATURE_V21_PRESCRIPTIVE_ENABLED=true
FEATURE_V22_PERSONALIZATION_ENABLED=true

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

Tip: In production set `APP_ENV=production` and `SECURITY_RSO_REDIRECT_URI` to an HTTPS domain that is whitelisted in the Riot Portal.

## 2) Align Riot Portal
Add the exact redirect URI to the Riot Developer Portal: `http://localhost:3000/callback` (or your HTTPS tunnel domain). Scopes: `openid offline_access` (optionally `cpid` per your app’s need).

## 3) Migrate and Start Services

```
# Alembic migrations (creates user_profiles and other tables if needed)
alembic upgrade head

# Start Redis/Postgres if not running
docker compose up -d redis postgres

# Start Celery worker (default + mapped queues)
celery -A src.tasks.celery_app.celery_app worker -l info -Q celery,matches,ai

# In another terminal: start the bot (starts callback server on :3000)
python -m main
```

## 4) Bind Flow (Real OAuth)
1. In Discord: `/bind` (pick region, default `na1`).
2. Click “Authorize with Riot” → complete Riot login/consent.
3. Callback hits `GET /callback?code=...&state=...`.
4. Success page should render (HTTP 200).
5. Verify DB: row upserted in `user_bindings` (discord_id, puuid, summoner_name, region).
6. In Discord: `/profile` shows binding.

## 5) Analyze (SR) – E2E Webhook
1. In Discord: `/analyze` (optionally `match_index=1`).
2. Expect deferred reply within 3s.
3. Within ~15m, webhook PATCH edits the original message with the final embed.
4. If rate-limited (429), retry after suggested cooldown.

## 6) Team Analyze (V2)
1. In Discord: `/team-analyze` (enable via `FEATURE_TEAM_ANALYSIS_ENABLED=true`).
2. Validate pagination and mode-aware UI (SR vision visible; ARAM vision hidden).
3. Fallback strategy renders friendly UI for unsupported modes.

## 7) Unbind
1. In Discord: `/unbind` → ephemeral confirmation.
2. `/profile` should now show “Not Linked”.

## 8) Troubleshooting
- 400 on /callback: ensure `code` & `state`, and state not expired (TTL=600s).
- 403 Riot API: check `RIOT_API_KEY` and portal permissions.
- Webhook 404: token expired (>15m) → re-run command.
- Missing features: check feature flags in `.env`.

## 9) Evidence Capture
Capture:
- Screenshots: bind, success page, profile, analyze/team-analyze results.
- Logs: `chimera_bot.log`, `logs/bot_latest.log`.
- Save under `docs/v2.4_test_evidence/REAL_RSO_*`.

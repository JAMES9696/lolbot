#!/usr/bin/env bash
set -euo pipefail

# Project Chimera - Deployment Environment Doctor
# - Validates required env vars from .env
# - Detects conflicts between current system environment and .env
# - Suggests using scripts/run_with_env.sh for isolated execution

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

cd "${ROOT_DIR}"

if [[ ! -f ".env" ]]; then
  echo "[ERROR] .env not found at ${ROOT_DIR}/.env" >&2
  echo "Create it from .env.example and fill in values." >&2
  exit 1
fi

echo "[INFO] Loading .env for validation..."

# Load .env in a subshell to avoid polluting current shell
set +u
source ".env"
set -u

# Required variables for typical production run
REQUIRED=(
  DISCORD_BOT_TOKEN
  DISCORD_APPLICATION_ID
  RIOT_API_KEY
  DATABASE_URL
  REDIS_URL
  CELERY_BROKER_URL
  CELERY_RESULT_BACKEND
  SECURITY_RSO_CLIENT_ID
  SECURITY_RSO_REDIRECT_URI
)

MISSING=()
for key in "${REQUIRED[@]}"; do
  if [[ -z "${!key-}" ]]; then
    MISSING+=("${key}")
  fi
done

if (( ${#MISSING[@]} > 0 )); then
  echo "[ERROR] Missing required variables in .env:" >&2
  for k in "${MISSING[@]}"; do echo "  - ${k}" >&2; done
  exit 2
fi

echo "[OK] Required variables present. Checking conflicts with current system environment..."

# Keys that we guard against accidental overrides from host env
GUARDED_PREFIXES=(DISCORD_ RIOT_ GEMINI_ REDIS_ DATABASE_URL SECURITY_RSO_ CELERY_ FEATURE_ TTS_ APP_)

CONFLICTS=()
for envline in $(env | sed 's/=.*//'); do
  for p in "${GUARDED_PREFIXES[@]}"; do
    if [[ "${envline}" == ${p}* ]]; then
      # Compare system env vs .env value
      sys_val="${!envline-}"
      file_val="$(grep -E "^${envline}=" .env | tail -n1 | cut -d'=' -f2- | tr -d '\r')"
      if [[ -n "${sys_val}" && -n "${file_val}" && "${sys_val}" != "${file_val}" ]]; then
        CONFLICTS+=("${envline}")
      fi
    fi
  done
done

if (( ${#CONFLICTS[@]} > 0 )); then
  echo "[WARN] Detected potential overrides from current system environment:" >&2
  for k in "${CONFLICTS[@]}"; do
    echo "  - ${k} (system != .env)" >&2
  done
  echo ""
  echo "Use sanitized launcher to avoid overrides:" >&2
  echo "  scripts/run_with_env.sh python main.py" >&2
  exit 3
fi

echo "[OK] No conflicting system env overrides detected."
exit 0

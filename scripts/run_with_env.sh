#!/usr/bin/env bash
set -euo pipefail

# Run a command in a sanitized environment where only .env variables apply.
# This prevents accidental overrides from the host/CI environment.

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

cd "${ROOT_DIR}"

if [[ ! -f ".env" ]]; then
  echo "[ERROR] .env not found at ${ROOT_DIR}/.env" >&2
  exit 1
fi

# Keep minimal safe vars; rebuild environment from scratch and source .env
SAFE_PATH="${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
SAFE_HOME="${HOME:-$ROOT_DIR}"
SAFE_SHELL="${SHELL:-/bin/bash}"
SAFE_TERM="${TERM:-xterm}"

exec env -i \
  PATH="${SAFE_PATH}" \
  HOME="${SAFE_HOME}" \
  SHELL="${SAFE_SHELL}" \
  TERM="${SAFE_TERM}" \
  bash -lc 'set -a; source .env; set +a; exec "$@"' bash "$@"

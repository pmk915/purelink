#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_CMD="${COMPOSE:-docker compose}"

load_env() {
  local env_file="$ROOT_DIR/.env"
  if [[ ! -f "$env_file" ]]; then
    env_file="$ROOT_DIR/.env.example"
  fi

  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

compose() {
  ${COMPOSE_CMD} "$@"
}

need_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    if [[ "$command_name" == "docker" ]]; then
      cat >&2 <<'EOF'
Docker was not found in this shell.

On Windows + WSL 2, enable Docker Desktop WSL integration for this distro,
then reopen the terminal. PureLink expects Docker Compose v2 through:

  docker compose
EOF
    else
      echo "Missing required command: $command_name" >&2
    fi
    exit 127
  fi
}

curl_url() {
  local url="$1"
  local args=(-fsS --max-time 5)
  case "$url" in
    http://localhost*|http://127.0.0.1*|http://0.0.0.0*)
      args+=(--noproxy '*')
      ;;
  esac
  curl "${args[@]}" "$url" >/dev/null
}

curl_text() {
  local url="$1"
  local args=(-fsS --max-time 5)
  case "$url" in
    http://localhost*|http://127.0.0.1*|http://0.0.0.0*)
      args+=(--noproxy '*')
      ;;
  esac
  curl "${args[@]}" "$url"
}

check_compose() {
  compose ps >/dev/null
}

check_api() {
  local api_base="${API_BASE_URL:-http://localhost:${APP_PORT:-8000}/api/v1}"
  api_base="${api_base%/}"
  curl_url "${API_HEALTH_URL:-$api_base/health}"
}

check_postgres() {
  compose exec -T db pg_isready \
    -U "${POSTGRES_USER:-purelink}" \
    -d "${POSTGRES_DB:-purelink}" >/dev/null
}

check_redis() {
  [[ "$(compose exec -T redis redis-cli ping)" == "PONG" ]]
}

check_worker() {
  compose ps --status running --services | grep -Fxq worker
}

check_frontend() {
  local frontend_url="${FRONTEND_BASE_URL:-http://localhost:${FRONTEND_PORT:-3000}}"
  curl_url "$frontend_url"
}

check_providers() {
  local api_base="${API_BASE_URL:-http://localhost:${APP_PORT:-8000}/api/v1}"
  api_base="${api_base%/}"
  local provider_status

  provider_status="$(curl_text "$api_base/system/providers")"
  PROVIDER_STATUS_JSON="$provider_status" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["PROVIDER_STATUS_JSON"])

labels = {
    "llm": "LLM provider",
    "embedding": "Embedding provider",
    "ocr": "OCR provider",
    "asr": "ASR provider",
    "reranker": "Reranker provider",
}
warnings = 0
failures = 0

for key in ("llm", "embedding", "ocr", "asr", "reranker"):
    item = payload.get(key, {})
    provider = item.get("provider", "<unknown>")
    mode = item.get("mode", "<unknown>")
    message = item.get("message", "")
    configured = bool(item.get("configured"))
    is_warning = False

    if key == "ocr" and mode != "disabled" and item.get("binary_available") is False:
        is_warning = True
    if key == "asr" and mode != "disabled" and not configured:
        is_warning = True

    if configured and not is_warning:
        print(f"[OK] {labels[key]}: {provider} ({mode})")
    elif is_warning:
        warnings += 1
        print(f"[WARN] {labels[key]}: {provider} ({message})")
    else:
        failures += 1
        print(f"[FAIL] {labels[key]}: {provider} ({message})")

if warnings:
    print(f"[WARN] Provider checks completed with {warnings} warning(s).")

sys.exit(1 if failures else 0)
PY
}

run_check() {
  local label="$1"
  shift

  printf '%-28s' "$label"
  if "$@"; then
    echo "OK"
    return 0
  fi

  echo "FAILED"
  return 1
}

main() {
  cd "$ROOT_DIR"
  load_env

  local compose_bin="${COMPOSE_CMD%% *}"
  need_command "$compose_bin"
  need_command curl
  need_command python3

  local failures=0
  local api_ready=0
  run_check "Docker Compose" check_compose || failures=$((failures + 1))
  if run_check "API health" check_api; then
    api_ready=1
  else
    failures=$((failures + 1))
  fi
  run_check "PostgreSQL" check_postgres || failures=$((failures + 1))
  run_check "Redis" check_redis || failures=$((failures + 1))
  run_check "Worker" check_worker || failures=$((failures + 1))
  run_check "Frontend" check_frontend || failures=$((failures + 1))

  echo
  if (( api_ready == 1 )); then
    if ! check_providers; then
      failures=$((failures + 1))
    fi
  else
    echo "[FAIL] Provider status: API is not reachable, skip provider checks."
  fi

  if (( failures > 0 )); then
    echo
    echo "One or more checks failed. Useful diagnostics:"
    echo "  docker compose ps"
    echo "  docker compose logs -f api"
    echo "  docker compose logs -f worker"
    echo "  docker compose logs -f redis"
    exit 1
  fi

  echo
  echo "PureLink stack checks passed."
}

main "$@"

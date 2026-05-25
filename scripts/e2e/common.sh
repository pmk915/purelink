#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
TMP_DIR="${TMP_DIR:-/tmp/purelink-e2e}"

mkdir -p "$TMP_DIR"

log() {
  echo
  echo "== $* =="
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

print_api_unreachable_hint() {
  echo "PureLink API is not reachable at $BASE_URL" >&2
  echo "Expected a running service on /api/v1/health before E2E starts." >&2
  echo >&2
  echo "Check these first:" >&2
  echo "1. Is the stack running? Try: docker compose ps" >&2
  echo "2. Can you reach the health endpoint manually?" >&2
  echo "   curl --noproxy '*' $BASE_URL/api/v1/health" >&2
  echo "3. If you use Docker Desktop + WSL, verify WSL integration is enabled for this distro." >&2
  echo "4. If the stack is not running, start it with:" >&2
  echo "   cp .env.example .env && docker compose up --build -d" >&2
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

need_cmd curl
need_cmd python3

curl_base_args() {
  local host
  host="$(python3 -c 'from urllib.parse import urlparse; import sys; print(urlparse(sys.argv[1]).hostname or "")' "$BASE_URL")"

  case "$host" in
    127.0.0.1|localhost|0.0.0.0|::1)
      printf '%s\n' --noproxy '*'
      ;;
  esac
}

json_get() {
  local key="$1"
  python3 -c '
import json
import sys

path = sys.argv[1]
data = json.load(sys.stdin)
current = data
for part in path.split("."):
    if isinstance(current, dict):
        current = current.get(part)
    elif isinstance(current, list) and part.isdigit():
        index = int(part)
        current = current[index] if 0 <= index < len(current) else None
    else:
        current = None
        break

if current is None:
    print("")
elif isinstance(current, (dict, list)):
    print(json.dumps(current, ensure_ascii=False))
else:
    print(current)
' "$key"
}

json_len() {
  python3 -c '
import json
import sys

data = json.load(sys.stdin)
if isinstance(data, (list, dict)):
    print(len(data))
else:
    print(0)
'
}

wait_api_ready() {
  local retries="${1:-30}"
  local sleep_sec="${2:-1}"
  local curl_args=()

  while IFS= read -r arg; do
    curl_args+=("$arg")
  done < <(curl_base_args)

  for _ in $(seq 1 "$retries"); do
    if curl "${curl_args[@]}" -sS --max-time 3 "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_sec"
  done

  print_api_unreachable_hint
  fail "PureLink API is not reachable at $BASE_URL"
}

http_json() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local token="${4:-}"
  local out_body="$TMP_DIR/resp_body.json"
  local out_code="$TMP_DIR/resp_code.txt"
  local curl_args=()

  while IFS= read -r arg; do
    curl_args+=("$arg")
  done < <(curl_base_args)

  rm -f "$out_body" "$out_code"

  if [[ -n "$body" && -n "$token" ]]; then
    curl "${curl_args[@]}" -sS \
      -X "$method" "$BASE_URL$path" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $token" \
      -d "$body" \
      -o "$out_body" \
      -w "%{http_code}" > "$out_code"
  elif [[ -n "$body" ]]; then
    curl "${curl_args[@]}" -sS \
      -X "$method" "$BASE_URL$path" \
      -H "Content-Type: application/json" \
      -d "$body" \
      -o "$out_body" \
      -w "%{http_code}" > "$out_code"
  elif [[ -n "$token" ]]; then
    curl "${curl_args[@]}" -sS \
      -X "$method" "$BASE_URL$path" \
      -H "Authorization: Bearer $token" \
      -o "$out_body" \
      -w "%{http_code}" > "$out_code"
  else
    curl "${curl_args[@]}" -sS \
      -X "$method" "$BASE_URL$path" \
      -o "$out_body" \
      -w "%{http_code}" > "$out_code"
  fi

  HTTP_CODE="$(cat "$out_code")"
  HTTP_BODY="$(cat "$out_body")"
  export HTTP_CODE HTTP_BODY
}

http_upload() {
  local path="$1"
  local file_path="$2"
  local token="$3"
  local out_body="$TMP_DIR/upload_body.json"
  local out_code="$TMP_DIR/upload_code.txt"
  local curl_args=()

  while IFS= read -r arg; do
    curl_args+=("$arg")
  done < <(curl_base_args)

  rm -f "$out_body" "$out_code"

  curl "${curl_args[@]}" -sS \
    -X POST "$BASE_URL$path" \
    -H "Authorization: Bearer $token" \
    -F "file=@${file_path}" \
    -o "$out_body" \
    -w "%{http_code}" > "$out_code"

  HTTP_CODE="$(cat "$out_code")"
  HTTP_BODY="$(cat "$out_body")"
  export HTTP_CODE HTTP_BODY
}

assert_code() {
  local expected="$1"
  [[ "${HTTP_CODE:-}" == "$expected" ]] || {
    echo "Expected HTTP $expected, got ${HTTP_CODE:-<empty>}"
    echo "Body: ${HTTP_BODY:-<empty>}"
    exit 1
  }
}

assert_contains() {
  local needle="$1"
  echo "${HTTP_BODY:-}" | grep -Fq "$needle" || {
    echo "Expected body to contain: $needle"
    echo "Body: ${HTTP_BODY:-<empty>}"
    exit 1
  }
}

register_user() {
  local email="$1"
  local username="$2"
  local password="$3"
  http_json POST /api/v1/auth/register "{\"email\":\"$email\",\"username\":\"$username\",\"password\":\"$password\"}"
}

login_user() {
  local identifier="$1"
  local password="$2"
  http_json POST /api/v1/auth/login "{\"identifier\":\"$identifier\",\"password\":\"$password\"}"
}

create_personal_kb() {
  local token="$1"
  local name="$2"
  local desc="$3"
  http_json POST /api/v1/knowledge-bases "{\"name\":\"$name\",\"description\":\"$desc\"}" "$token"
}

create_team() {
  local token="$1"
  local name="$2"
  local desc="$3"
  http_json POST /api/v1/teams "{\"name\":\"$name\",\"description\":\"$desc\"}" "$token"
}

create_team_invite() {
  local token="$1"
  local team_id="$2"
  local expires_days="${3:-7}"
  http_json POST "/api/v1/teams/$team_id/invites" "{\"expires_in_days\":$expires_days}" "$token"
}

join_team_by_code() {
  local token="$1"
  local code="$2"
  http_json POST /api/v1/team-invites/join "{\"code\":\"$code\"}" "$token"
}

create_team_kb() {
  local token="$1"
  local team_id="$2"
  local name="$3"
  local desc="$4"
  http_json POST "/api/v1/teams/$team_id/knowledge-bases" "{\"name\":\"$name\",\"description\":\"$desc\"}" "$token"
}

create_parse_task_personal() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  http_json POST "/api/v1/knowledge-bases/$kb_id/documents/$doc_id/parse-tasks" "" "$token"
}

create_chunk_task_personal() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  http_json POST "/api/v1/knowledge-bases/$kb_id/documents/$doc_id/chunk-tasks" "" "$token"
}

create_embed_task_personal() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  http_json POST "/api/v1/knowledge-bases/$kb_id/documents/$doc_id/embed-tasks" "" "$token"
}

create_parse_task_team() {
  local token="$1"
  local team_id="$2"
  local kb_id="$3"
  local doc_id="$4"
  http_json POST "/api/v1/teams/$team_id/knowledge-bases/$kb_id/documents/$doc_id/parse-tasks" "" "$token"
}

create_chunk_task_team() {
  local token="$1"
  local team_id="$2"
  local kb_id="$3"
  local doc_id="$4"
  http_json POST "/api/v1/teams/$team_id/knowledge-bases/$kb_id/documents/$doc_id/chunk-tasks" "" "$token"
}

create_embed_task_team() {
  local token="$1"
  local team_id="$2"
  local kb_id="$3"
  local doc_id="$4"
  http_json POST "/api/v1/teams/$team_id/knowledge-bases/$kb_id/documents/$doc_id/embed-tasks" "" "$token"
}

process_personal_document() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  http_json POST "/api/v1/knowledge-bases/$kb_id/documents/$doc_id/process" "" "$token"
}

process_team_document() {
  local token="$1"
  local team_id="$2"
  local kb_id="$3"
  local doc_id="$4"
  http_json POST "/api/v1/teams/$team_id/knowledge-bases/$kb_id/documents/$doc_id/process" "" "$token"
}

wait_processing_job_terminal() {
  local token="$1"
  local job_id="$2"
  local retries="${3:-60}"
  local sleep_sec="${4:-1}"

  for _ in $(seq 1 "$retries"); do
    http_json GET "/api/v1/processing-jobs/$job_id" "" "$token"
    assert_code 200
    local status
    status="$(echo "$HTTP_BODY" | json_get status)"
    if [[ "$status" == "succeeded" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "Processing job failed: $HTTP_BODY"
      return 1
    fi
    sleep "$sleep_sec"
  done

  echo "Processing job did not finish in time: $job_id"
  return 1
}

wait_personal_document_searchable() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  local retries="${4:-60}"
  local sleep_sec="${5:-1}"

  for _ in $(seq 1 "$retries"); do
    http_json GET "/api/v1/knowledge-bases/$kb_id/documents" "" "$token"
    assert_code 200
    local status
    status="$(
      echo "$HTTP_BODY" |
        python3 -c 'import json, sys; doc_id = int(sys.argv[1]); print(next((document.get("processing_status") or "" for document in json.load(sys.stdin) if document.get("id") == doc_id), ""))' "$doc_id"
    )"
    if [[ "$status" == "ready" || "$status" == "indexed" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "Document processing failed: $HTTP_BODY"
      return 1
    fi
    sleep "$sleep_sec"
  done

  echo "Document did not become searchable in time: $doc_id"
  return 1
}

document_rag_ready_from_body() {
  local doc_id="$1"
  python3 -c '
import json
import sys

doc_id = int(sys.argv[1])
data = json.load(sys.stdin)
if int(data.get("document_id") or 0) != doc_id:
    print("no")
    raise SystemExit(0)

status = data.get("processing_status") or ""
chunk_count = int(data.get("chunk_count") or 0)
citation_unit_count = int(data.get("citation_unit_count") or 0)
vector_index = data.get("vector_index") or {}
vector_status = vector_index.get("status") or ""
compatible = vector_index.get("compatible")
if (
    status in {"ready", "indexed"}
    and chunk_count > 0
    and citation_unit_count > 0
    and vector_status == "indexed"
    and compatible is not False
):
    print("yes")
else:
    print("no")
' "$doc_id"
}

wait_personal_document_rag_ready() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  local retries="${4:-90}"
  local sleep_sec="${5:-1}"
  local last_body=""

  for _ in $(seq 1 "$retries"); do
    http_json GET "/api/v1/knowledge-bases/$kb_id/documents/$doc_id/rag-debug" "" "$token"
    if [[ "$HTTP_CODE" != "200" ]]; then
      last_body="$HTTP_BODY"
      sleep "$sleep_sec"
      continue
    fi
    last_body="$HTTP_BODY"
    local ready
    ready="$(echo "$HTTP_BODY" | document_rag_ready_from_body "$doc_id")"
    if [[ "$ready" == "yes" ]]; then
      return 0
    fi

    local status
    status="$(echo "$HTTP_BODY" | json_get processing_status)"
    if [[ "$status" == "failed" ]]; then
      echo "Document processing failed:"
      echo "$HTTP_BODY"
      return 1
    fi
    sleep "$sleep_sec"
  done

  echo "Document did not become RAG-ready in time: $doc_id"
  echo "Last document RAG debug body:"
  echo "$last_body"
  return 1
}

wait_team_document_searchable() {
  local token="$1"
  local team_id="$2"
  local kb_id="$3"
  local doc_id="$4"
  local retries="${5:-60}"
  local sleep_sec="${6:-1}"

  for _ in $(seq 1 "$retries"); do
    http_json GET "/api/v1/teams/$team_id/knowledge-bases/$kb_id/documents" "" "$token"
    assert_code 200
    local status
    status="$(
      echo "$HTTP_BODY" |
        python3 -c 'import json, sys; doc_id = int(sys.argv[1]); print(next((document.get("processing_status") or "" for document in json.load(sys.stdin) if document.get("id") == doc_id), ""))' "$doc_id"
    )"
    if [[ "$status" == "ready" || "$status" == "indexed" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "Document processing failed: $HTTP_BODY"
      return 1
    fi
    sleep "$sleep_sec"
  done

  echo "Team document did not become searchable in time: $doc_id"
  return 1
}

wait_personal_document_indexed() {
  local token="$1"
  local kb_id="$2"
  local doc_id="$3"
  local retries="${4:-60}"
  local sleep_sec="${5:-1}"

  for _ in $(seq 1 "$retries"); do
    http_json GET "/api/v1/knowledge-bases/$kb_id/documents" "" "$token"
    assert_code 200
    local status
    status="$(
      echo "$HTTP_BODY" |
        python3 -c 'import json, sys; doc_id = int(sys.argv[1]); print(next((document.get("processing_status") or "" for document in json.load(sys.stdin) if document.get("id") == doc_id), ""))' "$doc_id"
    )"
    if [[ "$status" == "indexed" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "Document processing failed: $HTTP_BODY"
      return 1
    fi
    sleep "$sleep_sec"
  done

  echo "Document did not become indexed in time: $doc_id"
  return 1
}

wait_task_succeeded() {
  local token="$1"
  local task_id="$2"
  local retries="${3:-40}"
  local sleep_sec="${4:-1}"

  for _ in $(seq 1 "$retries"); do
    http_json GET "/api/v1/document-tasks/$task_id" "" "$token"
    assert_code 200
    local status
    status="$(echo "$HTTP_BODY" | json_get status)"
    if [[ "$status" == "succeeded" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "Task failed: $HTTP_BODY"
      return 1
    fi
    sleep "$sleep_sec"
  done

  echo "Task did not reach succeeded in time: $task_id"
  return 1
}

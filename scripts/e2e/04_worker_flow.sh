#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

wait_api_ready
log "worker flow"

RUN_ID="$(date +%s)_$RANDOM"
EMAIL="worker_${RUN_ID}@example.com"
USERNAME="worker_${RUN_ID}"
PASSWORD="StrongPass123"
FIXTURE="$ROOT_DIR/tests/fixtures/worker_sample.md"

log "register"
register_user "$EMAIL" "$USERNAME" "$PASSWORD"
assert_code 201

log "login"
login_user "$EMAIL" "$PASSWORD"
assert_code 200
TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"

log "create KB"
create_personal_kb "$TOKEN" "Worker KB $RUN_ID" "Worker test"
assert_code 201
KB_ID="$(echo "$HTTP_BODY" | json_get id)"

log "upload"
http_upload "/api/v1/knowledge-bases/$KB_ID/documents" "$FIXTURE" "$TOKEN"
assert_code 201
DOC_ID="$(echo "$HTTP_BODY" | json_get id)"

log "parse task"
create_parse_task_personal "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 201
PARSE_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$TOKEN" "$PARSE_TASK_ID"

log "chunk task"
create_chunk_task_personal "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 201
CHUNK_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$TOKEN" "$CHUNK_TASK_ID"

log "embed task"
create_embed_task_personal "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 201
EMBED_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$TOKEN" "$EMBED_TASK_ID"

log "check parsed artifact"
PARSED_FILE="$ROOT_DIR/data/parsed/personal/knowledge_base_${KB_ID}/document_${DOC_ID}.json"
[[ -f "$PARSED_FILE" ]] || fail "missing parsed file: $PARSED_FILE"

log "check chunk artifact"
CHUNK_FILE="$ROOT_DIR/data/chunks/personal/knowledge_base_${KB_ID}/document_${DOC_ID}.json"
[[ -f "$CHUNK_FILE" ]] || fail "missing chunk file: $CHUNK_FILE"

log "check vector artifact"
VECTOR_FILE="$ROOT_DIR/data/vector_store/personal/knowledge_base_${KB_ID}/index.json"
[[ -f "$VECTOR_FILE" ]] || fail "missing vector file: $VECTOR_FILE"

echo
echo "PASS: worker flow"
echo "parsed=$PARSED_FILE"
echo "chunk=$CHUNK_FILE"
echo "vector=$VECTOR_FILE"

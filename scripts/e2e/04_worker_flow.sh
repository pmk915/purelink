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

log "submit processing job"
process_personal_document "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 200
PROCESS_JOB_ID="$(echo "$HTTP_BODY" | json_get job_id)"
[[ -n "$PROCESS_JOB_ID" ]] || fail "empty processing job id"
wait_processing_job_terminal "$TOKEN" "$PROCESS_JOB_ID"
wait_personal_document_indexed "$TOKEN" "$KB_ID" "$DOC_ID"

log "check vector artifact"
VECTOR_FILE="$ROOT_DIR/data/vector_store/personal/knowledge_base_${KB_ID}/index.json"
[[ -f "$VECTOR_FILE" ]] || fail "missing vector file: $VECTOR_FILE"

log "check preview chunks"
http_json GET "/api/v1/knowledge-bases/$KB_ID/documents/$DOC_ID/preview" "" "$TOKEN"
assert_code 200
CHUNK_COUNT="$(echo "$HTTP_BODY" | json_get chunks | json_len)"
[[ "$CHUNK_COUNT" -ge 1 ]] || fail "preview returned no chunks"

echo
echo "PASS: worker flow"
echo "job_id=$PROCESS_JOB_ID"
echo "vector=$VECTOR_FILE"

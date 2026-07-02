#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

wait_api_ready
log "personal flow"

RUN_ID="$(date +%s)_$RANDOM"
EMAIL="personal_${RUN_ID}@example.com"
USERNAME="personal_${RUN_ID}"
PASSWORD="StrongPass123"
FIXTURE="$ROOT_DIR/tests/fixtures/personal_sample.txt"

log "register"
register_user "$EMAIL" "$USERNAME" "$PASSWORD"
assert_code 201
USER_ID="$(echo "$HTTP_BODY" | json_get id)"

log "login"
login_user "$EMAIL" "$PASSWORD"
assert_code 200
TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"
[[ -n "$TOKEN" ]] || fail "empty access token"

log "create personal kb"
create_personal_kb "$TOKEN" "Personal KB E2E" "Personal flow test"
assert_code 201
KB_ID="$(echo "$HTTP_BODY" | json_get id)"
[[ -n "$KB_ID" ]] || fail "empty knowledge base id"

log "reject unsupported upload"
UNSUPPORTED_FIXTURE="$TMP_DIR/unsupported_${RUN_ID}.zip"
printf 'not a supported document' > "$UNSUPPORTED_FIXTURE"
http_upload "/api/v1/knowledge-bases/$KB_ID/documents" "$UNSUPPORTED_FIXTURE" "$TOKEN"
assert_code 415
ERROR_CODE="$(echo "$HTTP_BODY" | json_get error.code)"
[[ "$ERROR_CODE" == "UNSUPPORTED_FILE_TYPE" ]] || fail "expected UNSUPPORTED_FILE_TYPE, got $ERROR_CODE"

log "reject empty upload"
EMPTY_FIXTURE="$TMP_DIR/empty_${RUN_ID}.txt"
: > "$EMPTY_FIXTURE"
http_upload "/api/v1/knowledge-bases/$KB_ID/documents" "$EMPTY_FIXTURE" "$TOKEN"
assert_code 400
ERROR_CODE="$(echo "$HTTP_BODY" | json_get error.code)"
[[ "$ERROR_CODE" == "VALIDATION_ERROR" ]] || fail "expected VALIDATION_ERROR, got $ERROR_CODE"

log "upload document"
http_upload "/api/v1/knowledge-bases/$KB_ID/documents" "$FIXTURE" "$TOKEN"
assert_code 201
DOC_ID="$(echo "$HTTP_BODY" | json_get id)"
[[ -n "$DOC_ID" ]] || fail "empty document id"

log "submit document processing"
process_personal_document "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 200
PROCESS_JOB_ID="$(echo "$HTTP_BODY" | json_get job_id)"
[[ -n "$PROCESS_JOB_ID" ]] || fail "empty processing job id"

log "processing jobs list"
http_json GET "/api/v1/knowledge-bases/$KB_ID/processing-jobs" "" "$TOKEN"
assert_code 200
JOB_TOTAL="$(echo "$HTTP_BODY" | json_get total)"
JOB_RUNNING="$(echo "$HTTP_BODY" | json_get running_count)"
[[ "$JOB_TOTAL" -ge 1 ]] || fail "expected at least one processing job"
[[ "$JOB_RUNNING" -ge 1 ]] || fail "expected at least one running processing job"

wait_processing_job_terminal "$TOKEN" "$PROCESS_JOB_ID"
wait_personal_document_rag_ready "$TOKEN" "$KB_ID" "$DOC_ID"

log "retrieve"
# Keep this query lexically aligned with tests/fixtures/personal_sample.txt.
# Smoke should validate the pipeline deterministically, not rely on subtle semantic retrieval behavior.
PRIMARY_RETRIEVE_PAYLOAD='{"query":"PureLink personal knowledge bases team knowledge bases document retrieval citation smoke test","top_k":3}'
FALLBACK_RETRIEVE_PAYLOAD='{"query":"AI-powered knowledge platform personal flow smoke document","top_k":3}'
http_json POST "/api/v1/knowledge-bases/$KB_ID/retrieve" "$PRIMARY_RETRIEVE_PAYLOAD" "$TOKEN"
assert_code 200
RET_COUNT="$(echo "$HTTP_BODY" | json_get results | json_len)"
if [[ "$RET_COUNT" -lt 1 ]]; then
  PRIMARY_RETRIEVE_BODY="$HTTP_BODY"
  echo "Primary retrieve response body:"
  echo "$PRIMARY_RETRIEVE_BODY"
  echo "Running fallback retrieve query."
  http_json POST "/api/v1/knowledge-bases/$KB_ID/retrieve" "$FALLBACK_RETRIEVE_PAYLOAD" "$TOKEN"
  assert_code 200
  RET_COUNT="$(echo "$HTTP_BODY" | json_get results | json_len)"
fi

if [[ "$RET_COUNT" -lt 1 ]]; then
  echo "Fallback retrieve response body:"
  echo "$HTTP_BODY"
  echo "kb_id=$KB_ID doc_id=$DOC_ID"
  echo "Document list:"
  http_json GET "/api/v1/knowledge-bases/$KB_ID/documents" "" "$TOKEN"
  echo "$HTTP_BODY"
  echo "Document RAG debug:"
  http_json GET "/api/v1/knowledge-bases/$KB_ID/documents/$DOC_ID/rag-debug" "" "$TOKEN" || true
  echo "$HTTP_BODY"
  echo "Document status:"
  http_json GET "/api/v1/knowledge-bases/$KB_ID/documents/$DOC_ID/status" "" "$TOKEN" || true
  echo "$HTTP_BODY"
  echo "KB RAG health:"
  http_json GET "/api/v1/knowledge-bases/$KB_ID/rag-health" "" "$TOKEN" || true
  echo "$HTTP_BODY"
  echo "Provider status:"
  http_json GET "/api/v1/system/providers" "" "" || true
  echo "$HTTP_BODY"
  fail "retrieval returned empty results"
fi
if [[ -n "${PRIMARY_RETRIEVE_BODY:-}" ]]; then
  echo "WARN: primary smoke query returned empty results, fallback query passed"
fi

log "ask"
http_json POST "/api/v1/knowledge-bases/$KB_ID/ask" '{"question":"What does this document say about PureLink personal and team knowledge bases?","top_k":3,"conversation_id":null}' "$TOKEN"
assert_code 200
ANSWER="$(echo "$HTTP_BODY" | json_get answer)"
CONV_ID="$(echo "$HTTP_BODY" | json_get conversation_id)"
[[ -n "$ANSWER" ]] || fail "empty answer"
[[ -n "$CONV_ID" ]] || fail "empty conversation_id"

log "conversation list"
http_json GET "/api/v1/conversations" "" "$TOKEN"
assert_code 200

log "conversation detail"
http_json GET "/api/v1/conversations/$CONV_ID" "" "$TOKEN"
assert_code 200
MSG_COUNT="$(echo "$HTTP_BODY" | json_get messages | json_len)"
[[ "$MSG_COUNT" -ge 2 ]] || fail "conversation does not contain expected messages"

echo
echo "PASS: personal flow"
echo "user_id=$USER_ID kb_id=$KB_ID doc_id=$DOC_ID conversation_id=$CONV_ID"

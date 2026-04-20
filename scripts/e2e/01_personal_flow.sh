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

log "upload document"
http_upload "/api/v1/knowledge-bases/$KB_ID/documents" "$FIXTURE" "$TOKEN"
assert_code 201
DOC_ID="$(echo "$HTTP_BODY" | json_get id)"
[[ -n "$DOC_ID" ]] || fail "empty document id"

log "create parse task"
create_parse_task_personal "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 201
PARSE_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$TOKEN" "$PARSE_TASK_ID"

log "create chunk task"
create_chunk_task_personal "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 201
CHUNK_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$TOKEN" "$CHUNK_TASK_ID"

log "create embed task"
create_embed_task_personal "$TOKEN" "$KB_ID" "$DOC_ID"
assert_code 201
EMBED_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$TOKEN" "$EMBED_TASK_ID"

log "retrieve"
http_json POST "/api/v1/knowledge-bases/$KB_ID/retrieve" '{"query":"What does this document say about PureLink?","top_k":3}' "$TOKEN"
assert_code 200
RET_COUNT="$(echo "$HTTP_BODY" | json_get results | json_len)"
[[ "$RET_COUNT" -ge 1 ]] || fail "retrieval returned empty results"

log "ask"
http_json POST "/api/v1/knowledge-bases/$KB_ID/ask" '{"question":"What is PureLink?","top_k":3,"conversation_id":null}' "$TOKEN"
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

#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

wait_api_ready
log "team review flow"

RUN_ID="$(date +%s)_$RANDOM"
ALICE_EMAIL="alice_${RUN_ID}@example.com"
ALICE_NAME="alice_${RUN_ID}"
BOB_EMAIL="bob_${RUN_ID}@example.com"
BOB_NAME="bob_${RUN_ID}"
PASSWORD="StrongPass123"
FIXTURE="$ROOT_DIR/tests/fixtures/team_sample.txt"

log "register alice"
register_user "$ALICE_EMAIL" "$ALICE_NAME" "$PASSWORD"
assert_code 201

log "login alice"
login_user "$ALICE_EMAIL" "$PASSWORD"
assert_code 200
ALICE_TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"

log "create team"
create_team "$ALICE_TOKEN" "Platform Team $RUN_ID" "Core collaboration team"
assert_code 201
TEAM_ID="$(echo "$HTTP_BODY" | json_get id)"

log "create team invite"
create_team_invite "$ALICE_TOKEN" "$TEAM_ID" 7
assert_code 201
INVITE_CODE="$(echo "$HTTP_BODY" | json_get code)"

log "register bob"
register_user "$BOB_EMAIL" "$BOB_NAME" "$PASSWORD"
assert_code 201

log "login bob"
login_user "$BOB_EMAIL" "$PASSWORD"
assert_code 200
BOB_TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"

log "bob joins team"
join_team_by_code "$BOB_TOKEN" "$INVITE_CODE"
assert_code 200

log "alice creates team kb"
create_team_kb "$ALICE_TOKEN" "$TEAM_ID" "Shared Engineering Docs $RUN_ID" "Team KB for E2E"
assert_code 201
KB_ID="$(echo "$HTTP_BODY" | json_get id)"

log "bob uploads team document"
http_upload "/api/v1/teams/$TEAM_ID/knowledge-bases/$KB_ID/documents" "$FIXTURE" "$BOB_TOKEN"
assert_code 201
DOC_ID="$(echo "$HTTP_BODY" | json_get id)"

log "bob lists team documents"
http_json GET "/api/v1/teams/$TEAM_ID/knowledge-bases/$KB_ID/documents" "" "$BOB_TOKEN"
assert_code 200
assert_contains "pending_review"

log "bob tries parse before approval"
create_parse_task_team "$BOB_TOKEN" "$TEAM_ID" "$KB_ID" "$DOC_ID"
assert_code 409

log "alice review tasks"
http_json GET "/api/v1/teams/$TEAM_ID/review-tasks" "" "$ALICE_TOKEN"
assert_code 200
assert_contains "\"id\""

log "alice approves document"
http_json POST "/api/v1/teams/$TEAM_ID/documents/$DOC_ID/approve" "" "$ALICE_TOKEN"
assert_code 200
assert_contains "approved"

log "bob creates parse task"
create_parse_task_team "$BOB_TOKEN" "$TEAM_ID" "$KB_ID" "$DOC_ID"
assert_code 201
PARSE_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$BOB_TOKEN" "$PARSE_TASK_ID"

log "bob creates chunk task"
create_chunk_task_team "$BOB_TOKEN" "$TEAM_ID" "$KB_ID" "$DOC_ID"
assert_code 201
CHUNK_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$BOB_TOKEN" "$CHUNK_TASK_ID"

log "bob creates embed task"
create_embed_task_team "$BOB_TOKEN" "$TEAM_ID" "$KB_ID" "$DOC_ID"
assert_code 201
EMBED_TASK_ID="$(echo "$HTTP_BODY" | json_get id)"
wait_task_succeeded "$BOB_TOKEN" "$EMBED_TASK_ID"

log "bob retrieval"
http_json POST "/api/v1/teams/$TEAM_ID/knowledge-bases/$KB_ID/retrieve" '{"query":"What is this team document about?","top_k":3}' "$BOB_TOKEN"
assert_code 200
RET_COUNT="$(echo "$HTTP_BODY" | json_get results | json_len)"
[[ "$RET_COUNT" -ge 1 ]] || fail "team retrieval returned empty results"

log "bob ask"
http_json POST "/api/v1/teams/$TEAM_ID/knowledge-bases/$KB_ID/ask" '{"question":"Summarize the onboarding document.","top_k":3,"conversation_id":null}' "$BOB_TOKEN"
assert_code 200
ANSWER="$(echo "$HTTP_BODY" | json_get answer)"
[[ -n "$ANSWER" ]] || fail "empty team answer"

echo
echo "PASS: team review flow"
echo "team_id=$TEAM_ID kb_id=$KB_ID doc_id=$DOC_ID"

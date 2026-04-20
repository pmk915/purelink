#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

wait_api_ready
log "permissions flow"

RUN_ID="$(date +%s)_$RANDOM"
A_EMAIL="perm_a_${RUN_ID}@example.com"
A_NAME="perm_a_${RUN_ID}"
B_EMAIL="perm_b_${RUN_ID}@example.com"
B_NAME="perm_b_${RUN_ID}"
C_EMAIL="perm_c_${RUN_ID}@example.com"
C_NAME="perm_c_${RUN_ID}"
PASSWORD="StrongPass123"
FIXTURE="$ROOT_DIR/tests/fixtures/permissions_sample.txt"

log "register/login A"
register_user "$A_EMAIL" "$A_NAME" "$PASSWORD"
assert_code 201
login_user "$A_EMAIL" "$PASSWORD"
assert_code 200
A_TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"

log "register/login B"
register_user "$B_EMAIL" "$B_NAME" "$PASSWORD"
assert_code 201
login_user "$B_EMAIL" "$PASSWORD"
assert_code 200
B_TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"

log "register/login C"
register_user "$C_EMAIL" "$C_NAME" "$PASSWORD"
assert_code 201
login_user "$C_EMAIL" "$PASSWORD"
assert_code 200
C_TOKEN="$(echo "$HTTP_BODY" | json_get access_token)"

log "A creates team"
create_team "$A_TOKEN" "Perm Team $RUN_ID" "Permissions test team"
assert_code 201
TEAM_ID="$(echo "$HTTP_BODY" | json_get id)"

log "A creates invite"
create_team_invite "$A_TOKEN" "$TEAM_ID" 7
assert_code 201
CODE="$(echo "$HTTP_BODY" | json_get code)"

log "B joins"
join_team_by_code "$B_TOKEN" "$CODE"
assert_code 200

log "A creates team KB"
create_team_kb "$A_TOKEN" "$TEAM_ID" "Perm KB $RUN_ID" "Permissions KB"
assert_code 201
KB_ID="$(echo "$HTTP_BODY" | json_get id)"

log "B cannot create team KB"
create_team_kb "$B_TOKEN" "$TEAM_ID" "Should Fail" "member should not create"
assert_code 403

log "C cannot list team KBs"
http_json GET "/api/v1/teams/$TEAM_ID/knowledge-bases" "" "$C_TOKEN"
assert_code 404

log "B uploads team doc"
http_upload "/api/v1/teams/$TEAM_ID/knowledge-bases/$KB_ID/documents" "$FIXTURE" "$B_TOKEN"
assert_code 201
DOC_ID="$(echo "$HTTP_BODY" | json_get id)"

log "B cannot approve"
http_json POST "/api/v1/teams/$TEAM_ID/documents/$DOC_ID/approve" "" "$B_TOKEN"
assert_code 403

log "C cannot see review tasks"
http_json GET "/api/v1/teams/$TEAM_ID/review-tasks" "" "$C_TOKEN"
assert_code 404

log "A approves"
http_json POST "/api/v1/teams/$TEAM_ID/documents/$DOC_ID/approve" "" "$A_TOKEN"
assert_code 200
assert_contains "approved"

echo
echo "PASS: permissions flow"
echo "team_id=$TEAM_ID kb_id=$KB_ID doc_id=$DOC_ID"

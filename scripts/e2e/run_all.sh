#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

chmod +x scripts/e2e/*.sh
source scripts/e2e/common.sh
wait_api_ready

scripts/e2e/01_personal_flow.sh
scripts/e2e/02_team_review_flow.sh
scripts/e2e/03_permissions_flow.sh
scripts/e2e/04_worker_flow.sh

echo
echo "ALL E2E SCRIPTS PASSED"

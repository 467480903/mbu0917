#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" db 10 "查询地图点位" "/humanoid/db/response/" safe

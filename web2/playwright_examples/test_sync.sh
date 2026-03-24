#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" sync 0 "读取变量" "/humanoid/sync/data/" safe

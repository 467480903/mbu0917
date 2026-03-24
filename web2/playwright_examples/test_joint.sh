#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" joint 0 "头部 3 关节" "/humanoid/done/" motion

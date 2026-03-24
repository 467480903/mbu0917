#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" base 0 "相对移动" "/humanoid/done/" motion

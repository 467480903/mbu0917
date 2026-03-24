#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" pose 0 "末端相对偏移" "/humanoid/done/" motion

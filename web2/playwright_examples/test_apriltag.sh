#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" apriltag 1 "检测已保存图片" "/humanoid/apriltag/response/" safe

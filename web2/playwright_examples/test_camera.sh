#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" camera 2 "读取图像" "/humanoid/camera/response/" safe

#!/usr/bin/env bash
set -euo pipefail
bash "$(dirname "$0")/run_module_test.sh" tts 2 "读取音量" "/humanoid/tts/response/" safe

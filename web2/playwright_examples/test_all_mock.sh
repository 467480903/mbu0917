#!/usr/bin/env bash
set -euo pipefail

example_dir="$(cd "$(dirname "$0")" && pwd)"
export PW_KEEP_OPEN=0

for example in \
  test_base.sh test_joint.sh test_pose.sh test_end_effector.sh \
  test_tts.sh test_camera.sh test_apriltag.sh test_database.sh test_sync.sh
do
  bash "${example_dir}/${example}"
done

echo "[PASS] 9 个模块的 Playwright 模拟测试全部完成"

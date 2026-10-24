#!/usr/bin/env bash
set -euo pipefail
pwcli="${CODEX_HOME:-$HOME/.codex}/skills/playwright/scripts/playwright_cli.sh"
url="http://${WEB2_HOST:-10.42.1.101}:${WEB2_PORT:-8003}/tests/pose-teaching.html"
delay="${PW_STEP_DELAY:-1}"
keep_open="${PW_KEEP_OPEN:-1}"
pw() { bash "${pwcli}" "$@"; }
step() { echo; echo "========== $1 =========="; sleep "${delay}"; }
pw close >/dev/null 2>&1 || true
step "1/6 打开简洁末端与夹爪页"
pw open "${url}" --headed
step "2/6 等待模拟 MQTT 读取左手坐标"
pw run-code "async (page) => { await page.getByText('已读取当前末端坐标').waitFor(); if (await page.locator('[data-pose]').count() !== 7) throw new Error('位姿字段不完整'); }"
step "3/6 创建左手坐标变量"
pw run-code "async (page) => { await page.locator('#pose-name').fill('playwright_left_pose'); await page.getByRole('button', {name: '创建当前坐标变量'}).click(); await page.getByText('已创建坐标变量：playwright_left_pose').waitFor(); }"
step "4/6 调整左右夹爪目标"
pw run-code "async (page) => { await page.locator('#left-gripper').fill('0.8'); await page.locator('#right-gripper').fill('0.3'); }"
step "5/6 在模拟 MQTT 下同时控制夹爪"
pw run-code "async (page) => { await page.getByRole('button', {name: '同时控制左右夹爪'}).click(); await page.getByText('左右夹爪运动完成').waitFor(); }"
pw snapshot
step "6/6 检查控制台"
pw console error
echo "[PASS] 末端读取、坐标变量与双夹爪模拟控制"
if [[ "${keep_open}" != "1" ]]; then pw close; fi

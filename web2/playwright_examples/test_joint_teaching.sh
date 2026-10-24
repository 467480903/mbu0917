#!/usr/bin/env bash
set -euo pipefail
pwcli="${CODEX_HOME:-$HOME/.codex}/skills/playwright/scripts/playwright_cli.sh"
url="http://${WEB2_HOST:-10.42.1.101}:${WEB2_PORT:-8003}/tests/joint-teaching.html"
delay="${PW_STEP_DELAY:-1}"
keep_open="${PW_KEEP_OPEN:-1}"
pw() { bash "${pwcli}" "$@"; }
step() { echo; echo "========== $1 =========="; sleep "${delay}"; }
pw close >/dev/null 2>&1 || true
step "1/6 打开简洁关节示教页"
pw open "${url}" --headed
step "2/6 等待模拟 MQTT 读取 22 个关节"
pw run-code "async (page) => { await page.getByText('已读取 22 个关节').waitFor(); if (await page.locator('#joint-rows tr').count() !== 22) throw new Error('关节行数错误'); }"
step "3/6 微调一个关节"
pw run-code "async (page) => { const before = await page.locator('[data-joint=idx01_body_joint1]').inputValue(); await page.locator('[data-adjust=\"+idx01_body_joint1\"]').click(); const after = await page.locator('[data-joint=idx01_body_joint1]').inputValue(); if (before === after) throw new Error('微调没有生效'); }"
step "4/6 创建任意单关节变量"
pw run-code "async (page) => { await page.locator('#scope').selectOption('single_joint'); await page.locator('#variable-name').fill('playwright_single_joint'); await page.getByRole('button', {name: '创建关节变量'}).click(); await page.getByText('已创建变量：playwright_single_joint').waitFor(); }"
step "5/6 在模拟 MQTT 下执行目标"
pw run-code "async (page) => { await page.getByRole('button', {name: '执行当前目标'}).click(); await page.getByText('关节运动完成').waitFor(); }"
pw snapshot
step "6/6 检查控制台"
pw console error
echo "[PASS] 关节读取、微调、单关节变量与模拟执行"
if [[ "${keep_open}" != "1" ]]; then pw close; fi

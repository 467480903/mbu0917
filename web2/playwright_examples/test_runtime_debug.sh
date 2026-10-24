#!/usr/bin/env bash
set -euo pipefail

skill_home="${CODEX_HOME:-$HOME/.codex}"
pwcli="${skill_home}/skills/playwright/scripts/playwright_cli.sh"
web2_host="${WEB2_HOST:-10.42.1.101}"
web2_port="${WEB2_PORT:-8003}"
step_delay="${PW_STEP_DELAY:-1}"
keep_open="${PW_KEEP_OPEN:-1}"
url="http://${web2_host}:${web2_port}/tests/runtime-debug.html"

pw() { bash "${pwcli}" "$@"; }
step() { echo; echo "========== $1 =========="; sleep "${step_delay}"; }

pw close >/dev/null 2>&1 || true

step "1/8 打开可见浏览器"
pw open "${url}" --headed
step "2/8 检查简洁测试页"
pw snapshot
step "3/8 读取 programs 目录"
pw run-code "async (page) => { await page.getByRole('button', {name: '读取程序列表'}).click(); await page.waitForFunction(() => Array.from(document.querySelector('#programs').options).some(option => option.value === 'debug_demo.py')); }"
step "4/8 选择并执行程序"
pw run-code "async (page) => { await page.getByLabel('程序文件').selectOption('debug_demo.py'); await page.getByRole('button', {name: '执行选中程序'}).click(); await page.waitForFunction(() => document.querySelector('#debug-status')?.textContent === 'completed'); const log = await page.locator('#log').innerText(); if (!log.includes('\"command\":\"copy\"') || !log.includes('\"command\":\"run\"')) throw new Error('选择执行没有依次发送 copy/run'); }"
step "5/8 读取 main.py"
pw run-code "async (page) => { await page.getByRole('button', {name: '读取 main.py'}).click(); await page.waitForFunction(() => document.querySelector('#source-code')?.textContent.includes('数字 = [1, 2, 3]')); }"
step "6/8 单步调试选中程序"
pw run-code "async (page) => { await page.getByRole('button', {name: '单步调试选中程序'}).click(); await page.getByText('等待下一步', {exact: true}).waitFor(); const line = await page.locator('#current-line').innerText(); if (line !== '3') throw new Error('首个调试行错误: ' + line); }"
step "7/8 执行下一步并检查行号变化"
pw run-code "async (page) => { await page.getByRole('button', {name: '下一步'}).click(); await page.waitForFunction(() => document.querySelector('#current-line')?.textContent === '4'); const log = await page.locator('#log').innerText(); if (!log.includes('/humanoid/programs/step')) throw new Error('缺少 step topic'); }"
pw snapshot
step "8/8 检查浏览器控制台错误"
pw console error

echo
echo "[PASS] runtime2 代码单步调试页面"
if [[ "${keep_open}" == "1" ]]; then
  echo "浏览器保持打开，便于继续人工查看。"
else
  sleep "${step_delay}"
  pw close
fi

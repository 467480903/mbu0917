#!/usr/bin/env bash
set -euo pipefail

module_name="${1:?module name is required}"
command_index="${2:?command index is required}"
command_label="${3:?command label is required}"
expected_topic="${4:?expected topic is required}"
motion_mode="${5:-safe}"

if ! command -v npx >/dev/null 2>&1; then
  echo "未找到 npx，请先安装 Node.js/npm。" >&2
  exit 1
fi

skill_home="${CODEX_HOME:-$HOME/.codex}"
pwcli="${skill_home}/skills/playwright/scripts/playwright_cli.sh"
web2_host="${WEB2_HOST:-10.42.1.101}"
web2_port="${WEB2_PORT:-8003}"
step_delay="${PW_STEP_DELAY:-2}"
keep_open="${PW_KEEP_OPEN:-1}"
live_mode="${PLAYWRIGHT_LIVE:-0}"

if [[ ! -f "${pwcli}" ]]; then
  echo "未找到 Playwright skill wrapper: ${pwcli}" >&2
  exit 1
fi
if [[ "${live_mode}" == "1" && "${motion_mode}" == "motion" ]]; then
  echo "拒绝自动执行真机运动测试：${module_name}/${command_label}" >&2
  echo "请打开真实页面，人工检查参数和机器人周围环境后操作。" >&2
  exit 2
fi

query=""
mode_text="模拟 MQTT，不控制机器人"
if [[ "${live_mode}" == "1" ]]; then
  query="?live=1"
  mode_text="真实 MQTT 联调"
fi
url="http://${web2_host}:${web2_port}/tests/${module_name}.html${query}"

pw() {
  bash "${pwcli}" "$@"
}

step() {
  echo
  echo "========== $1 =========="
  sleep "${step_delay}"
}

pw close >/dev/null 2>&1 || true

step "1/5 打开可见浏览器：${mode_text}"
pw open "${url}" --headed

step "2/5 生成页面快照，确认 ${module_name} 模块已加载"
pw snapshot

step "3/5 点击“${command_label}”的发送按钮"
pw run-code "async (page) => { await page.getByRole('button', {name: '发送'}).nth(${command_index}).click(); }"

step "4/5 等待 MQTT 反馈并校验页面成功状态"
pw run-code "async (page) => { await page.waitForTimeout(800); const body = await page.locator('body').innerText(); if (!body.includes('成功')) throw new Error('页面未显示成功状态'); if (!body.includes('${expected_topic}')) throw new Error('日志中缺少期望 topic'); }"
pw snapshot

step "5/5 检查浏览器控制台错误"
pw console error

echo
echo "[PASS] ${module_name} / ${command_label}"
if [[ "${keep_open}" == "1" ]]; then
  echo "浏览器保持打开，便于继续人工查看。"
else
  sleep "${step_delay}"
  pw close
fi

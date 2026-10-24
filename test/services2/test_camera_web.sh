#!/usr/bin/env bash
set -euo pipefail

skill_home="${CODEX_HOME:-$HOME/.codex}"
pwcli="${skill_home}/skills/playwright/scripts/playwright_cli.sh"
host="${WEB2_HOST:-10.42.1.101}"
port="${WEB2_PORT:-8003}"
delay="${PW_STEP_DELAY:-1.5}"
pw() { bash "${pwcli}" "$@"; }
step() { echo "[摄像头测试] $1"; sleep "${delay}"; }

command -v npx >/dev/null 2>&1 || { echo "未找到 npx" >&2; exit 1; }
[[ -f "${pwcli}" ]] || { echo "未找到 ${pwcli}" >&2; exit 1; }
pw close >/dev/null 2>&1 || true
step "打开真实摄像头测试页面"
pw open "http://${host}:${port}/service-tests/camera.html" --headed
pw snapshot
step "连接真实 MQTT"
pw run-code "async (page) => { await page.getByRole('button', {name: '连接', exact: true}).click(); await page.waitForFunction(() => document.body.innerText.includes('已连接'), null, {timeout: 30000}); }"

for camera in kHeadColor kHeadDepth kHandLeftColor kHandRightColor; do
  step "打开 ${camera} 并显示真实单帧"
  pw run-code "async (page) => { await page.locator('#open-${camera}').click(); await page.waitForFunction(value => document.querySelector('#status-' + value).textContent.includes('已打开'), '${camera}', {timeout: 120000}); const image = page.locator('#image-${camera}'); await image.waitFor({state: 'visible'}); if (await image.evaluate(node => node.naturalWidth) <= 0) throw new Error('${camera} 图片无效'); await page.waitForTimeout(1500); }"
  step "${camera} 拍照并验证双文件名"
  pw run-code "async (page) => { await page.locator('#capture-${camera}').click(); await page.waitForFunction(value => { const text = document.querySelector('#saved-' + value).textContent; return text.includes(value + '-') && text.includes(value + '-latest.jpg'); }, '${camera}', {timeout: 120000}); await page.waitForTimeout(1500); }"
  step "关闭 ${camera} 页面显示"
  pw run-code "async (page) => { await page.locator('#close-${camera}').click(); await page.waitForFunction(value => document.querySelector('#status-' + value).textContent === '已关闭', '${camera}'); if (!(await page.locator('#image-${camera}').isHidden())) throw new Error('${camera} 关闭后图片仍可见'); await page.waitForTimeout(1500); }"
done

step "全部四路相机拍照并保存"
pw run-code "async (page) => { await page.getByRole('button', {name: '全部拍照并保存', exact: true}).click(); await page.waitForFunction(() => document.querySelector('#operation-status').textContent === '全部拍照：成功', null, {timeout: 180000}); await page.waitForTimeout(1500); }"
pw snapshot
pw console error
echo "[PASS] 四路真实摄像头的打开、关闭、拍照和双文件保存测试通过"

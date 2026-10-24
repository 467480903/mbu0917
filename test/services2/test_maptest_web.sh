#!/usr/bin/env bash
set -euo pipefail

skill_home="${CODEX_HOME:-$HOME/.codex}"
pwcli="${skill_home}/skills/playwright/scripts/playwright_cli.sh"
host="${WEB2_HOST:-10.42.1.101}"
port="${WEB2_PORT:-8003}"
delay="${PW_STEP_DELAY:-1.5}"
pw() { bash "${pwcli}" "$@"; }
step() { echo "[地图测试] $1"; sleep "${delay}"; }

command -v npx >/dev/null 2>&1 || { echo "未找到 npx" >&2; exit 1; }
[[ -f "${pwcli}" ]] || { echo "未找到 ${pwcli}" >&2; exit 1; }
pw close >/dev/null 2>&1 || true
step "打开真实机器人地图页面"
pw open "http://${host}:${port}/service-tests/maptest.html" --headed
pw snapshot
step "连接真实 MQTT"
pw run-code "async (page) => { await page.getByRole('button', {name: '连接', exact: true}).click(); await page.waitForFunction(() => document.body.innerText.includes('已连接'), null, {timeout: 30000}); }"
for label in "读取全部" "读取地图" "读取激光点" "读取地图点位" "读取电量"; do
  step "点击 ${label}"
  pw run-code "async (page) => { await page.getByRole('button', {name: '${label}', exact: true}).click(); await page.waitForFunction(value => document.body.innerText.includes(value + '：成功'), '${label}', {timeout: 120000}); }"
done
step "隐藏地图图层"
pw run-code "async (page) => { const canvas = page.locator('#map-canvas'); const before = await canvas.evaluate(node => node.toDataURL()); await page.locator('#show-map').uncheck(); await page.waitForTimeout(1500); const after = await canvas.evaluate(node => node.toDataURL()); if (before === after) throw new Error('隐藏地图后画布没有变化'); }"
step "显示地图图层"
pw run-code "async (page) => { const canvas = page.locator('#map-canvas'); const before = await canvas.evaluate(node => node.toDataURL()); await page.locator('#show-map').check(); await page.waitForTimeout(1500); const after = await canvas.evaluate(node => node.toDataURL()); if (before === after) throw new Error('显示地图后画布没有变化'); }"
step "隐藏激光点图层"
pw run-code "async (page) => { const canvas = page.locator('#map-canvas'); const before = await canvas.evaluate(node => node.toDataURL()); await page.locator('#show-laser').uncheck(); await page.waitForTimeout(1500); const after = await canvas.evaluate(node => node.toDataURL()); if (before === after) throw new Error('隐藏激光点后画布没有变化'); }"
step "显示激光点图层"
pw run-code "async (page) => { await page.locator('#show-laser').check(); await page.waitForTimeout(1500); }"
step "放大地图"
pw run-code "async (page) => { await page.getByRole('button', {name: '放大', exact: true}).click(); await page.waitForTimeout(1500); if (await page.locator('#zoom-status').textContent() !== '125%') throw new Error('放大比例不正确'); }"
step "缩小地图"
pw run-code "async (page) => { await page.getByRole('button', {name: '缩小', exact: true}).click(); await page.waitForTimeout(1500); if (await page.locator('#zoom-status').textContent() !== '100%') throw new Error('缩小比例不正确'); }"
step "检查真实地图数据与只允许人工操作的按钮"
pw run-code "async (page) => { const text = await page.locator('body').innerText(); for (const value of ['机器人 GDK', '激光点：', '电量：', '位置：', '/humanoid/maptest/request/']) if (!text.includes(value)) throw new Error('缺少 ' + value); for (const label of ['前进', '后退', '左移', '右移', '逆时针', '顺时针', '立刻停止', '按当前位置保存', '同步机器人点位到 SQLite', '到点']) if (!(await page.getByRole('button', {name: label, exact: true}).isVisible())) throw new Error('按钮不可见：' + label); }"
pw snapshot
pw console error
echo "[PASS] 已显示真实地图、激光点、点位、电量和底盘地图位置"

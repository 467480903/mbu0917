#!/usr/bin/env bash
set -euo pipefail

skill_home="${CODEX_HOME:-$HOME/.codex}"
pwcli="${skill_home}/skills/playwright/scripts/playwright_cli.sh"
web2_host="${WEB2_HOST:-10.42.1.101}"
web2_port="${WEB2_PORT:-8003}"
step_delay="${PW_STEP_DELAY:-1}"
keep_open="${PW_KEEP_OPEN:-1}"
url="http://${web2_host}:${web2_port}/tests/urdf.html"

pw() { bash "${pwcli}" "$@"; }
step() { echo; echo "========== $1 =========="; sleep "${step_delay}"; }

pw close >/dev/null 2>&1 || true
step "1/6 打开简洁 URDF 功能测试页"
pw open "${url}" --headed
step "2/6 读取真实机器人 URDF 和 STL 网格"
pw run-code "async (page) => { await page.getByRole('button', {name: '读取机器人模型'}).click(); await page.waitForFunction(() => window.__URDF_TEST__?.state.loaded && window.__URDF_TEST__.state.meshCount > 0, null, {timeout: 30000}); const state = await page.evaluate(() => window.__URDF_TEST__.state); if (!state.jointCount || state.errors.length) throw new Error('模型解析结果异常: ' + JSON.stringify(state)); }"
pw snapshot
step "3/6 记录相机位置并模拟鼠标拖动"
pw run-code "async (page) => { const canvas = page.locator('canvas'); const box = await canvas.boundingBox(); if (!box) throw new Error('找不到 Three.js canvas'); const before = await page.evaluate(() => window.__URDF_TEST__.getCameraState()); await page.mouse.move(box.x + box.width * .45, box.y + box.height * .45); await page.mouse.down(); await page.mouse.move(box.x + box.width * .65, box.y + box.height * .55, {steps: 8}); await page.mouse.up(); await page.waitForTimeout(500); const after = await page.evaluate(() => window.__URDF_TEST__.getCameraState()); if (JSON.stringify(before) === JSON.stringify(after)) throw new Error('鼠标拖动后相机没有变化'); }"
step "4/6 模拟滚轮缩放"
pw run-code "async (page) => { const canvas = page.locator('canvas'); await canvas.hover(); const before = await page.evaluate(() => window.__URDF_TEST__.getCameraState()); await page.mouse.wheel(0, -600); await page.waitForTimeout(500); const after = await page.evaluate(() => window.__URDF_TEST__.getCameraState()); if (JSON.stringify(before.position) === JSON.stringify(after.position)) throw new Error('滚轮后相机距离没有变化'); }"
step "5/6 恢复视角并生成快照"
pw run-code "async (page) => { await page.getByRole('button', {name: '恢复视角'}).click(); }"
pw snapshot
step "6/6 检查浏览器控制台错误"
pw console error

echo "[PASS] URDF 解析、鼠标旋转与滚轮缩放"
if [[ "${keep_open}" != "1" ]]; then pw close; fi

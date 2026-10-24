#!/usr/bin/env bash
set -euo pipefail

pwcli="${CODEX_HOME:-$HOME/.codex}/skills/playwright/scripts/playwright_cli.sh"
host="${WEB2_HOST:-10.42.1.101}"
port="${WEB2_PORT:-8003}"
delay="${PW_STEP_DELAY:-1}"
keep_open="${PW_KEEP_OPEN:-1}"
pw() { bash "${pwcli}" "$@"; }
step() { echo; echo "========== $1 =========="; sleep "${delay}"; }

pw close >/dev/null 2>&1 || true
step "1/6 打开统一集成操作台"
pw open "http://${host}:${port}/?view=model&mock=1" --headed
step "2/6 检查工作流导航和居中功能区域"
pw run-code "async (page) => { const result = await page.evaluate(() => ({nav: document.querySelectorAll('.integrated-nav-item').length, frame: document.querySelector('.integrated-stage')?.getBoundingClientRect(), width: innerWidth})); if (result.nav < 9) throw new Error('工作流入口不完整'); if (!result.frame || result.frame.width >= result.width) throw new Error('功能区域没有居中留白'); }"
pw snapshot
step "3/6 切换到关节示教"
pw run-code "async (page) => { await page.getByRole('button', {name: '关节示教'}).click(); const frame = page.frameLocator('#function-frame'); await frame.getByRole('heading', {name: '关节示教功能测试'}).waitFor(); await frame.getByText('已读取 22 个关节').waitFor(); }"
step "4/6 验证集成模式样式注入且独立页控件可用"
pw run-code "async (page) => { const frame = page.frames().find(item => item.url().includes('joint-teaching.html')); const result = await frame.evaluate(() => ({style: Boolean(document.querySelector('style[data-integrated-style]')), rows: document.querySelectorAll('#joint-rows tr').length})); if (!result.style || result.rows !== 22) throw new Error('关节示教集成失败: ' + JSON.stringify(result)); }"
step "5/6 切换程序、地图、相机并检查页面入口"
pw run-code "async (page) => { for (const name of ['程序调试', '地图与底盘', '摄像头']) { await page.getByRole('button', {name}).click(); await page.waitForTimeout(700); const frame = page.locator('#function-frame'); if (!await frame.getAttribute('src')) throw new Error(name + ' 没有加载页面'); } }"
pw snapshot
step "6/6 检查浏览器控制台错误"
pw console error
echo "[PASS] 集成操作台导航、统一样式和功能装载"
if [[ "${keep_open}" != "1" ]]; then pw close; fi

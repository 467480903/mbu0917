import { modules, moduleByKey } from '../modules/index.js';
import { MqttTransport } from '../core/mqtt-transport.js';
import { MockTransport } from '../core/mock-transport.js';
import { ServiceClient } from '../core/service-client.js';

const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

export function mountPage(root, requestedModule) {
  const query = new URLSearchParams(location.search);
  const mockMode = query.get('live') !== '1'
    && (query.get('mock') === '1' || document.body.dataset.mock === 'true');
  let activeKey = requestedModule || query.get('module') || modules[0].key;
  let client = null;
  let connected = false;
  const logs = [];

  const render = () => {
    const active = moduleByKey(activeKey) || modules[0];
    root.innerHTML = `
      <div class="shell">
        <aside class="sidebar">
          <h2 class="brand">G2 / web2</h2>
          <p class="subtitle">面向测试的模块化控制台</p>
          <nav class="nav">${modules.map(module => `
            <a href="${requestedModule ? '../tests/' + module.key + '.html' : './index.html?module=' + module.key + (mockMode ? '&mock=1' : '')}"
               data-module="${module.key}" class="${module.key === active.key ? 'active' : ''}">
              <span>${escapeHtml(module.title)}</span><small>${module.commands.length}</small>
            </a>`).join('')}</nav>
        </aside>
        <main class="content">
          <div class="topbar">
            <div><div class="eyebrow">service / ${active.key}</div><h1>${escapeHtml(active.title)}</h1><p class="lead">${escapeHtml(active.description)}</p></div>
            <section class="connection">
              <div class="connection-row"><input id="broker" value="${location.hostname || '10.42.1.101'}" aria-label="MQTT 主机"><input id="port" value="9001" size="5" aria-label="MQTT 端口"><button class="connect" id="connect">连接</button></div>
              <div class="status"><i class="dot ${connected ? 'connected' : ''}"></i><span>${connected ? '已连接' : '未连接'}</span></div>
            </section>
          </div>
          <div class="toolbar"><span class="pill ${mockMode ? 'mock' : ''}">${mockMode ? '模拟 MQTT（不下发到机器人）' : '真实 MQTT'}</span><a class="test-link" href="${requestedModule ? '../index.html?module=' + active.key + '&mock=1' : './tests/index.html'}">测试页入口</a></div>
          <section class="cards">${active.commands.map((command, index) => commandCard(command, index)).join('')}</section>
          <section class="console"><header><span>MQTT 事件日志</span><button id="clear-log">清空</button></header><pre id="log">${escapeHtml(logs.join('\n'))}</pre></section>
        </main>
      </div>`;
    bind(active);
  };

  const commandCard = (command, index) => {
    const body = JSON.stringify({ cmd: command.cmd, ...command.payload }, null, 2);
    return `<article class="card" data-command="${command.cmd}"><div class="card-head"><div><h2>${escapeHtml(command.label)}</h2><p>cmd: ${command.cmd}</p></div>${command.motion ? '<span class="badge">机器人运动</span>' : ''}</div><textarea id="payload-${index}" aria-label="${escapeHtml(command.label)} JSON">${escapeHtml(body)}</textarea><div class="actions"><span class="result" id="result-${index}">尚未执行</span><button class="send" data-index="${index}">发送</button></div></article>`;
  };

  const bind = active => {
    root.querySelector('#connect').onclick = connect;
    root.querySelector('#clear-log').onclick = () => { logs.length = 0; root.querySelector('#log').textContent = ''; };
    root.querySelectorAll('.send').forEach(button => {
      button.onclick = () => execute(active, active.commands[Number(button.dataset.index)], Number(button.dataset.index), button);
    });
  };

  const appendLog = (direction, topic, payload) => {
    logs.push(`${new Date().toLocaleTimeString()} ${direction === 'send' ? '→' : '←'} ${topic}\n${JSON.stringify(payload)}`);
    if (logs.length > 80) logs.shift();
    const output = root.querySelector('#log');
    if (output) { output.textContent = logs.join('\n'); output.scrollTop = output.scrollHeight; }
  };

  async function connect() {
    if (connected) return;
    const host = root.querySelector('#broker').value.trim();
    const port = Number(root.querySelector('#port').value);
    const transport = mockMode ? new MockTransport() : new MqttTransport({ host, port });
    client = new ServiceClient(transport, appendLog);
    try { await client.connect(); connected = true; render(); }
    catch (error) { appendLog('receive', 'connection/error', { error: error.message }); }
  }

  async function execute(active, command, index, button) {
    const result = root.querySelector(`#result-${index}`);
    let payload;
    try { payload = JSON.parse(root.querySelector(`#payload-${index}`).value); }
    catch (error) { result.className = 'result error'; result.textContent = `JSON 错误: ${error.message}`; return; }
    if (!client || !connected) { result.className = 'result error'; result.textContent = '请先连接 MQTT'; return; }
    if (command.motion && !mockMode && !window.confirm('请确认机器人周围无人员和障碍物，是否继续？')) return;
    button.disabled = true; result.className = 'result'; result.textContent = '等待反馈…';
    try {
      const response = await client.send(active.key, payload, { waitFor: command.waitFor || 'response' });
      result.className = 'result ok'; result.textContent = `成功 · ${response.time}`;
    } catch (error) {
      result.className = 'result error'; result.textContent = error.message;
    } finally { button.disabled = false; }
  }

  render();
  if (mockMode) connect();
}

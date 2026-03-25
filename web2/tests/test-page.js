import { MockTransport } from '../js/core/mock-transport.js';
import { MqttTransport } from '../js/core/mqtt-transport.js';
import { ServiceClient } from '../js/core/service-client.js';
import { moduleByKey } from '../js/modules/index.js';

const moduleConfig = moduleByKey(document.body.dataset.module);
const query = new URLSearchParams(location.search);
const mockMode = query.get('live') !== '1';
const root = document.querySelector('#app');
const logs = [];
let client = null;

function appendLog(direction, topic, payload) {
  logs.push(`${direction} ${topic}\n${JSON.stringify(payload)}`);
  document.querySelector('#log').textContent = logs.join('\n\n');
}

async function connect() {
  const transport = mockMode
    ? new MockTransport()
    : new MqttTransport({
        host: document.querySelector('#broker').value,
        port: Number(document.querySelector('#port').value),
      });
  client = new ServiceClient(transport, appendLog);
  try {
    await client.connect();
    document.querySelector('#connection-status').textContent = '已连接';
  } catch (error) {
    document.querySelector('#connection-status').textContent = `连接失败: ${error.message}`;
  }
}

async function sendCommand(command, index) {
  const result = document.querySelector(`#result-${index}`);
  let payload;
  try {
    payload = JSON.parse(document.querySelector(`#payload-${index}`).value);
  } catch (error) {
    result.textContent = `JSON 错误: ${error.message}`;
    return;
  }
  if (!client) {
    result.textContent = '请先连接 MQTT';
    return;
  }
  if (command.motion && !mockMode
      && !window.confirm('请确认机器人周围安全，是否继续？')) {
    return;
  }
  result.textContent = '等待反馈…';
  try {
    const response = await client.send(moduleConfig.key, payload, {
      waitFor: command.waitFor || 'response',
    });
    result.textContent = `成功: ${response.time}`;
  } catch (error) {
    result.textContent = `失败: ${error.message}`;
  }
}

function commandSection(command, index) {
  const payload = JSON.stringify({ cmd: command.cmd, ...command.payload }, null, 2);
  return `
    <section>
      <h2>${command.label}</h2>
      <p>cmd: <code>${command.cmd}</code>${command.motion ? '（机器人运动）' : ''}</p>
      <textarea id="payload-${index}" rows="8" cols="70">${payload}</textarea>
      <p>
        <button data-command-index="${index}">发送</button>
        <span id="result-${index}">尚未执行</span>
      </p>
    </section>
    <hr>
  `;
}

root.innerHTML = `
  <h1>${moduleConfig.title}模块测试</h1>
  <p>${moduleConfig.description}</p>
  <p><strong>模式：</strong>${mockMode ? '模拟 MQTT，不会向机器人下发命令' : '真实 MQTT'}</p>

  <fieldset>
    <legend>MQTT 连接</legend>
    <label>Broker <input id="broker" value="${location.hostname || '10.42.1.101'}"></label>
    <label>WebSocket 端口 <input id="port" value="9001" size="6"></label>
    <button id="connect">连接</button>
    <span id="connection-status">未连接</span>
  </fieldset>

  ${moduleConfig.commands.map(commandSection).join('')}

  <h2>MQTT 日志</h2>
  <pre id="log"></pre>
`;

document.querySelector('#connect').addEventListener('click', connect);
document.querySelectorAll('[data-command-index]').forEach(button => {
  const index = Number(button.dataset.commandIndex);
  button.addEventListener('click', () => sendCommand(moduleConfig.commands[index], index));
});

if (mockMode) {
  connect();
}

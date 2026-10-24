import { MockTransport } from '../js/core/mock-transport.js';
import { MqttTransport } from '../js/core/mqtt-transport.js';
import { ServiceClient } from '../js/core/service-client.js';

const groups = {
  waist: ['idx01_body_joint1', 'idx02_body_joint2', 'idx03_body_joint3', 'idx04_body_joint4', 'idx05_body_joint5'],
  head: ['idx11_head_joint1', 'idx12_head_joint2', 'idx13_head_joint3'],
  left_arm: ['idx21_arm_l_joint1', 'idx22_arm_l_joint2', 'idx23_arm_l_joint3', 'idx24_arm_l_joint4', 'idx25_arm_l_joint5', 'idx26_arm_l_joint6', 'idx27_arm_l_joint7'],
  right_arm: ['idx61_arm_r_joint1', 'idx62_arm_r_joint2', 'idx63_arm_r_joint3', 'idx64_arm_r_joint4', 'idx65_arm_r_joint5', 'idx66_arm_r_joint6', 'idx67_arm_r_joint7'],
};
const labels = { waist: '腰部', head: '头部', left_arm: '左臂', right_arm: '右臂' };
const allJoints = Object.values(groups).flat();
const query = new URLSearchParams(location.search);
const mockMode = query.get('live') !== '1';
const values = Object.fromEntries(allJoints.map(name => [name, 0]));
const logs = [];
let client = null;

const element = id => document.querySelector(`#${id}`);
element('mode').textContent = mockMode ? '模式：模拟 MQTT，不控制机器人' : '模式：真实 MQTT';
element('broker').value = location.hostname || '10.42.1.101';

function appendLog(direction, topic, payload) {
  logs.push(`${direction === 'send' ? '发送' : '接收'} ${topic} ${JSON.stringify(payload)}`);
  element('log').textContent = logs.join('\n');
}

function setStatus(message) { element('status').textContent = message; }
function requireClient() { if (!client) throw new Error('请先连接 MQTT'); return client; }

function renderRows() {
  element('joint-rows').innerHTML = Object.entries(groups).flatMap(([group, names]) => names.map(name => `
    <tr>
      <td>${labels[group]}</td>
      <td>${name}</td>
      <td><input type="number" data-joint="${name}" value="${values[name].toFixed(4)}" step="0.01"></td>
      <td><button type="button" data-adjust="-${name}">−</button> <button type="button" data-adjust="+${name}">+</button></td>
    </tr>`)).join('');
  document.querySelectorAll('[data-joint]').forEach(input => {
    input.addEventListener('change', () => { values[input.dataset.joint] = Number(input.value); });
  });
  document.querySelectorAll('[data-adjust]').forEach(button => {
    button.addEventListener('click', () => {
      const direction = button.dataset.adjust[0] === '+' ? 1 : -1;
      const name = button.dataset.adjust.slice(1);
      values[name] += direction * Number(element('step').value);
      renderRows();
    });
  });
}

async function connect() {
  const transport = mockMode ? new MockTransport() : new MqttTransport({
    host: element('broker').value.trim(), port: Number(element('port').value),
  });
  client = new ServiceClient(transport, appendLog);
  await client.connect();
  element('connection-status').textContent = '已连接';
}

async function readCurrent() {
  try {
    const response = await requireClient().send('joint', { cmd: 'get_current_angles' });
    for (const name of allJoints) if (Object.hasOwn(response.result || {}, name)) values[name] = Number(response.result[name]);
    renderRows();
    setStatus(`已读取 ${Object.keys(response.result || {}).length} 个关节`);
  } catch (error) { setStatus(`读取失败：${error.message}`); }
}

function selectedDefinition() {
  const scope = element('scope').value;
  if (scope === 'single_joint') {
    const name = element('single-joint').value;
    return { scope, names: [name], payload: { cmd: 'single_joint', name, value: values[name], speed: Number(element('speed').value) } };
  }
  const names = scope === 'wbc' ? allJoints : groups[scope];
  const selected = Object.fromEntries(names.map(name => [name, values[name]]));
  const joints = scope === 'wbc' ? selected : names.map(name => values[name]);
  return { scope, names, payload: { cmd: scope, joints, speed: Number(element('speed').value) } };
}

async function execute() {
  try {
    const definition = selectedDefinition();
    if (!mockMode && !confirm(`将执行 ${definition.scope} 关节运动，确认机器人周围安全？`)) return;
    setStatus('正在执行关节运动…');
    await requireClient().send('joint', definition.payload, { waitFor: 'done' });
    setStatus('关节运动完成');
  } catch (error) { setStatus(`执行失败：${error.message}`); }
}

async function saveVariable() {
  try {
    const name = element('variable-name').value.trim();
    if (!name) throw new Error('请输入变量名');
    const definition = selectedDefinition();
    const value = Object.fromEntries(definition.names.map(joint => [joint, values[joint]]));
    await requireClient().send('db', { cmd: 'addJoint', type: definition.scope, name, value });
    setStatus(`已创建变量：${name}`);
  } catch (error) { setStatus(`保存失败：${error.message}`); }
}

element('single-joint').innerHTML = allJoints.map(name => `<option value="${name}">${name}</option>`).join('');
element('scope').addEventListener('change', () => { element('single-wrap').hidden = element('scope').value !== 'single_joint'; });
element('connect').addEventListener('click', async () => { try { await connect(); setStatus('MQTT 已连接'); } catch (error) { setStatus(`连接失败：${error.message}`); } });
element('read').addEventListener('click', readCurrent);
element('execute').addEventListener('click', execute);
element('save').addEventListener('click', saveVariable);
renderRows();
if (mockMode) connect().then(readCurrent);

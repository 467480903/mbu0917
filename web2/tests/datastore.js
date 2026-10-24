import { MockTransport } from '../js/core/mock-transport.js';
import { MqttTransport } from '../js/core/mqtt-transport.js';
import { ServiceClient } from '../js/core/service-client.js';

const query = new URLSearchParams(location.search);
const mockMode = query.get('live') !== '1';
const logs = [];
let client = null;
let variables = [];
let selectedKey = null;

const WHOLE_BODY_JOINTS = [
  'idx01_body_joint1', 'idx02_body_joint2', 'idx03_body_joint3',
  'idx04_body_joint4', 'idx05_body_joint5',
  'idx11_head_joint1', 'idx12_head_joint2', 'idx13_head_joint3',
  'idx21_arm_l_joint1', 'idx22_arm_l_joint2', 'idx23_arm_l_joint3',
  'idx24_arm_l_joint4', 'idx25_arm_l_joint5', 'idx26_arm_l_joint6',
  'idx27_arm_l_joint7',
  'idx61_arm_r_joint1', 'idx62_arm_r_joint2', 'idx63_arm_r_joint3',
  'idx64_arm_r_joint4', 'idx65_arm_r_joint5', 'idx66_arm_r_joint6',
  'idx67_arm_r_joint7',
];
const LEFT_ARM_JOINTS = WHOLE_BODY_JOINTS.filter(name => name.includes('_arm_l_'));
const RIGHT_ARM_JOINTS = WHOLE_BODY_JOINTS.filter(name => name.includes('_arm_r_'));

const variableTypes = [
  { key: 'whole_body', label: '全身关节', storageType: 'wbc', source: 'joint', joints: WHOLE_BODY_JOINTS },
  { key: 'left_arm', label: '左手关节', storageType: 'left_arm', source: 'joint', joints: LEFT_ARM_JOINTS },
  { key: 'right_arm', label: '右手关节', storageType: 'right_arm', source: 'joint', joints: RIGHT_ARM_JOINTS },
  { key: 'left_pose', label: '左手姿态位置', storageType: 'left', source: 'pose', side: 'left' },
  { key: 'right_pose', label: '右手姿态位置', storageType: 'right', source: 'pose', side: 'right' },
];

document.querySelector('#mode').textContent = mockMode
  ? '模式：模拟 MQTT，不读取或移动机器人'
  : '模式：真实 MQTT';
document.querySelector('#broker').value = location.hostname || '10.42.1.101';
document.querySelector('#save-actions').innerHTML = variableTypes.map(type => `
  <p>
    <label>${type.label}变量名
      <input id="name-${type.key}" placeholder="请输入变量名">
    </label>
    <button type="button" data-save="${type.key}">保存当前${type.label}</button>
  </p>
`).join('');

function setStatus(message) {
  document.querySelector('#operation-status').textContent = message;
}

function appendLog(direction, topic, payload) {
  logs.push(`${direction === 'send' ? '发送' : '接收'} ${topic} ${JSON.stringify(payload)}`);
  document.querySelector('#log').textContent = logs.join('\n');
}

async function connect() {
  const transport = mockMode
    ? new MockTransport()
    : new MqttTransport({
        host: document.querySelector('#broker').value.trim(),
        port: Number(document.querySelector('#port').value),
      });
  client = new ServiceClient(transport, appendLog);
  try {
    await client.connect();
    document.querySelector('#connection-status').textContent = '已连接';
    await refreshVariables();
  } catch (error) {
    client = null;
    document.querySelector('#connection-status').textContent = `连接失败：${error.message}`;
  }
}

function requireClient() {
  if (!client) throw new Error('请先连接 MQTT');
}

function jointValues(allValues, names) {
  const missing = names.filter(name => !Object.hasOwn(allValues, name));
  if (missing.length) throw new Error(`未读取到关节：${missing.join(', ')}`);
  return Object.fromEntries(names.map(name => [name, Number(allValues[name])]));
}

function positionValue(pose) {
  if (!Array.isArray(pose.position) || pose.position.length !== 3
      || !Array.isArray(pose.orientation) || pose.orientation.length !== 4) {
    throw new Error('当前末端位姿格式不正确');
  }
  let [rx, ry, rz, rw] = pose.orientation.map(Number);
  const norm = Math.hypot(rx, ry, rz, rw);
  if (!Number.isFinite(norm) || norm === 0) throw new Error('当前末端姿态四元数无效');
  [rx, ry, rz, rw] = [rx / norm, ry / norm, rz / norm, rw / norm];
  if (rw < 0) [rx, ry, rz] = [-rx, -ry, -rz];
  return {
    x: Number(pose.position[0]),
    y: Number(pose.position[1]),
    z: Number(pose.position[2]),
    rx,
    ry,
    rz,
  };
}

async function saveCurrent(typeKey) {
  try {
    requireClient();
    const type = variableTypes.find(item => item.key === typeKey);
    const name = document.querySelector(`#name-${type.key}`).value.trim();
    if (!name) throw new Error('请填写变量名');
    if (variables.some(item => item.name === name)) throw new Error(`变量名已存在：${name}`);
    setStatus(`正在读取当前${type.label}…`);

    let value;
    let command;
    if (type.source === 'joint') {
      const response = await client.send('joint', { cmd: 'get_current_angles' });
      value = jointValues(response.result, type.joints);
      command = { cmd: 'addJoint', type: type.storageType, name, value };
    } else {
      const response = await client.send('pose', { cmd: 'get_current_pose', side: type.side });
      value = positionValue(response.result);
      command = { cmd: 'addPosition', type: type.storageType, name, value };
    }
    await client.send('db', command);
    setStatus(`已保存：${name}（${type.label}）`);
    await refreshVariables();
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  }
}

async function refreshVariables() {
  try {
    requireClient();
    const [jointResponse, positionResponse] = await Promise.all([
      client.send('db', { cmd: 'getJoints' }),
      client.send('db', { cmd: 'getPositions' }),
    ]);
    const joints = (jointResponse.result || [])
      .filter(item => ['wbc', 'left_arm', 'right_arm'].includes(item.type))
      .map(item => ({ ...item, storage: 'joint' }));
    const positions = (positionResponse.result || [])
      .filter(item => ['left', 'right'].includes(item.type))
      .map(item => ({ ...item, storage: 'position' }));
    variables = [...joints, ...positions].sort((a, b) => a.name.localeCompare(b.name));
    if (!variables.some(item => itemKey(item) === selectedKey)) selectedKey = null;
    renderVariables();
    setStatus(`已读取 ${variables.length} 个变量`);
  } catch (error) {
    setStatus(`读取失败：${error.message}`);
  }
}

function itemKey(item) {
  return `${item.storage}:${item.type}:${item.name}`;
}

function typeLabel(item) {
  return variableTypes.find(type => type.storageType === item.type)?.label || item.type;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function renderVariables() {
  const body = document.querySelector('#variables');
  if (!variables.length) {
    body.innerHTML = '<tr><td colspan="4">暂无变量</td></tr>';
  } else {
    body.innerHTML = variables.map(item => {
      const key = itemKey(item);
      const checked = key === selectedKey ? ' checked' : '';
      return `
        <tr data-variable-key="${escapeHtml(key)}">
          <td><input type="radio" name="variable" value="${escapeHtml(key)}"${checked}></td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(typeLabel(item))}</td>
          <td><details><summary>查看变量值</summary><pre>${escapeHtml(JSON.stringify(item.value, null, 2))}</pre></details></td>
        </tr>
      `;
    }).join('');
  }
  body.querySelectorAll('input[name="variable"]').forEach(input => {
    input.addEventListener('change', () => selectVariable(input.value));
  });
  body.querySelectorAll('details').forEach(details => {
    details.addEventListener('click', event => event.stopPropagation());
  });
  body.querySelectorAll('[data-variable-key]').forEach(row => {
    row.addEventListener('click', () => selectVariable(row.dataset.variableKey));
  });
  const selected = variables.find(item => itemKey(item) === selectedKey);
  document.querySelector('#selected-name').textContent = selected
    ? `${selected.name}（${typeLabel(selected)}）`
    : '无';
  document.querySelector('#move').disabled = !selected;
}

function selectVariable(key) {
  selectedKey = key;
  renderVariables();
}

async function moveSelected() {
  try {
    requireClient();
    const selected = variables.find(item => itemKey(item) === selectedKey);
    if (!selected) throw new Error('请先选择一个变量');
    if (!mockMode && !window.confirm(`机器人将运动到“${selected.name}”，确认周围环境安全并继续？`)) return;
    setStatus(`正在执行：${selected.name}`);
    const cmd = selected.storage === 'joint' ? 'moveJoint' : 'movePosition';
    await client.send('db', { cmd, name: selected.name });
    setStatus(`动作完成：${selected.name}`);
  } catch (error) {
    setStatus(`执行失败：${error.message}`);
  }
}

document.querySelector('#connect').addEventListener('click', connect);
document.querySelector('#refresh').addEventListener('click', refreshVariables);
document.querySelector('#move').addEventListener('click', moveSelected);
document.querySelectorAll('[data-save]').forEach(button => {
  button.addEventListener('click', () => saveCurrent(button.dataset.save));
});

if (mockMode) connect();

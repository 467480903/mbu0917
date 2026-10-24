import { MockTransport } from '../js/core/mock-transport.js';
import { MqttTransport } from '../js/core/mqtt-transport.js';
import { ServiceClient } from '../js/core/service-client.js';

const query = new URLSearchParams(location.search);
const mockMode = query.get('live') !== '1';
const fields = ['x', 'y', 'z', 'qx', 'qy', 'qz', 'qw'];
const pose = { x: 0.4, y: 0.2, z: 1, qx: 0, qy: 0, qz: 0, qw: 1 };
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

function renderPose() {
  element('pose-fields').innerHTML = fields.map(name => `<tr><th>${name}</th><td><input type="number" data-pose="${name}" value="${pose[name]}" step="0.01"></td></tr>`).join('');
  document.querySelectorAll('[data-pose]').forEach(input => input.addEventListener('change', () => { pose[input.dataset.pose] = Number(input.value); }));
}

async function connect() {
  const transport = mockMode ? new MockTransport() : new MqttTransport({ host: element('broker').value.trim(), port: Number(element('port').value) });
  client = new ServiceClient(transport, appendLog);
  await client.connect();
  element('connection-status').textContent = '已连接';
}

async function readPose() {
  try {
    const response = await requireClient().send('pose', { cmd: 'get_current_pose', side: element('side').value });
    const [x, y, z] = response.result.position;
    const [qx, qy, qz, qw] = response.result.orientation;
    Object.assign(pose, { x, y, z, qx, qy, qz, qw });
    renderPose();
    setStatus('已读取当前末端坐标');
  } catch (error) { setStatus(`读取失败：${error.message}`); }
}

async function movePose() {
  try {
    if (!mockMode && !confirm('将执行末端运动，确认机器人周围安全？')) return;
    await requireClient().send('pose', {
      cmd: element('side').value,
      position: [pose.x, pose.y, pose.z],
      orientation: [pose.qx, pose.qy, pose.qz, pose.qw],
    }, { waitFor: 'done' });
    setStatus('末端运动完成');
  } catch (error) { setStatus(`运动失败：${error.message}`); }
}

async function savePose() {
  try {
    const name = element('pose-name').value.trim();
    if (!name) throw new Error('请输入变量名');
    await requireClient().send('db', {
      cmd: 'addPosition', type: element('side').value, name,
      value: { x: pose.x, y: pose.y, z: pose.z, rx: pose.qx, ry: pose.qy, rz: pose.qz },
    });
    setStatus(`已创建坐标变量：${name}`);
  } catch (error) { setStatus(`保存失败：${error.message}`); }
}

async function moveGrippers() {
  try {
    if (!mockMode && !confirm('将控制左右夹爪，确认夹爪周围安全？')) return;
    await requireClient().send('ee', {
      cmd: 'both_grippers',
      left: Number(element('left-gripper').value),
      right: Number(element('right-gripper').value),
    }, { waitFor: 'done' });
    setStatus('左右夹爪运动完成');
  } catch (error) { setStatus(`夹爪控制失败：${error.message}`); }
}

for (const side of ['left', 'right']) element(`${side}-gripper`).addEventListener('input', event => { element(`${side}-value`).textContent = Number(event.target.value).toFixed(1); });
element('connect').addEventListener('click', async () => { try { await connect(); setStatus('MQTT 已连接'); } catch (error) { setStatus(`连接失败：${error.message}`); } });
element('read-pose').addEventListener('click', readPose);
element('move-pose').addEventListener('click', movePose);
element('save-pose').addEventListener('click', savePose);
element('move-grippers').addEventListener('click', moveGrippers);
renderPose();
if (mockMode) connect().then(readPose);

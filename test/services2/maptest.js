import { MqttTransport } from '/js/core/mqtt-transport.js';
import { ServiceClient } from '/js/core/service-client.js';

const state = {
  client: null,
  map: null,
  laser: null,
  points: [],
  pose: null,
  showMap: true,
  showLaser: true,
  zoom: 1,
};
const logs = [];

const element = id => document.querySelector(`#${id}`);
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function appendLog(direction, topic, payload) {
  logs.push(`${direction} ${topic}\n${JSON.stringify(payload)}`);
  element('log').textContent = logs.join('\n\n');
}

function requireClient() {
  if (!state.client) throw new Error('请先连接 MQTT');
  return state.client;
}

async function connect() {
  const transport = new MqttTransport({
    host: element('broker').value,
    port: Number(element('port').value),
  });
  state.client = new ServiceClient(transport, appendLog);
  try {
    await state.client.connect();
    element('connection-status').textContent = '已连接';
  } catch (error) {
    state.client = null;
    element('connection-status').textContent = `连接失败：${error.message}`;
  }
}

async function runOperation(label, action) {
  element('operation-status').textContent = `${label}：执行中`;
  try {
    const value = await action();
    element('operation-status').textContent = `${label}：成功`;
    return value;
  } catch (error) {
    element('operation-status').textContent = `${label}：失败，${error.message}`;
    return null;
  }
}

async function mapCommand(cmd, payload = {}) {
  const response = await requireClient().send('maptest', { cmd, ...payload });
  return response.result;
}

async function decodeMap(map) {
  if (!map?.data_b64) return map;
  const bytes = Uint8Array.from(atob(map.data_b64), character => character.charCodeAt(0));
  if (map.data_encoding === 'gzip-base64') {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    map.cells = new Uint8Array(await new Response(stream).arrayBuffer());
  } else {
    map.cells = bytes;
  }
  return map;
}

async function applySnapshot(snapshot) {
  await decodeMap(snapshot.map);
  state.map = snapshot.map;
  state.laser = snapshot.laser;
  state.points = snapshot.points || [];
  state.pose = snapshot.pose;
  updateMapStatus();
  updateLaserStatus();
  updatePoints();
  updatePose();
  updateBattery(snapshot.battery);
  draw();
}

function updateMapStatus() {
  const map = state.map;
  element('map-status').textContent = map
    ? `${map.name || map.id}，${map.width}×${map.height}，${map.resolution} m/格`
    : '未读取';
}

function updateLaserStatus() {
  const laser = state.laser;
  element('laser-status').textContent = laser
    ? `${laser.count}（前 ${laser.front}，后 ${laser.back}）`
    : '未读取';
}

function updatePose() {
  if (!state.pose) return;
  const [x, y] = state.pose.position;
  element('pose-status').textContent = `X=${x.toFixed(3)}，Y=${y.toFixed(3)}，Yaw=${state.pose.yaw.toFixed(3)}`;
}

function updateBattery(battery) {
  element('battery-status').textContent = battery?.soc == null
    ? '未读取'
    : `${battery.soc}%（${battery.batteries.length} 组）`;
}

function updatePoints() {
  element('point-rows').innerHTML = state.points.map((point, index) => `
    <tr>
      <td><input type="radio" name="selected-point" value="${point.name}" ${index === 0 ? 'checked' : ''}></td>
      <td>${point.name}</td>
      <td>${point.source}</td>
      <td>${Number(point.position[0]).toFixed(3)}</td>
      <td>${Number(point.position[1]).toFixed(3)}</td>
      <td>${Number(point.position[2] || 0).toFixed(3)}</td>
    </tr>
  `).join('');
}

function mapGeometry(canvas) {
  const map = state.map;
  if (!map) return null;
  const worldWidth = map.width * map.resolution;
  const worldHeight = map.height * map.resolution;
  const scale = Math.min(canvas.width / worldWidth, canvas.height / worldHeight)
    * 0.92
    * state.zoom;
  const originX = map.origin.position[0];
  const originY = map.origin.position[1];
  const left = (canvas.width - worldWidth * scale) / 2;
  const bottom = (canvas.height + worldHeight * scale) / 2;
  return {
    scale,
    worldToCanvas(x, y) {
      return [left + (x - originX) * scale, bottom - (y - originY) * scale];
    },
  };
}

function drawGrid(context, geometry) {
  const map = state.map;
  const bytes = map.cells || new Uint8Array();
  const cellSize = Math.max(1, map.resolution * geometry.scale);
  for (let row = 0; row < map.height; row += 1) {
    for (let column = 0; column < map.width; column += 1) {
      const raw = bytes[row * map.width + column];
      const value = raw > 127 ? raw - 256 : raw;
      context.fillStyle = value < 0 ? '#ddd' : (value >= 65 ? '#333' : '#fff');
      const x = map.origin.position[0] + column * map.resolution;
      const y = map.origin.position[1] + (row + 1) * map.resolution;
      const [px, py] = geometry.worldToCanvas(x, y);
      context.fillRect(px, py, cellSize, cellSize);
    }
  }
}

function drawMarker(context, geometry, x, y, color, label, radius = 4) {
  const [px, py] = geometry.worldToCanvas(x, y);
  context.fillStyle = color;
  context.beginPath();
  context.arc(px, py, radius, 0, Math.PI * 2);
  context.fill();
  if (label) context.fillText(label, px + radius + 2, py - radius - 2);
}

function draw() {
  const canvas = element('map-canvas');
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = '#eee';
  context.fillRect(0, 0, canvas.width, canvas.height);
  const geometry = mapGeometry(canvas);
  if (!geometry) return;
  if (state.showMap) drawGrid(context, geometry);
  context.font = '12px sans-serif';
  state.points.forEach(point => drawMarker(
    context, geometry, point.position[0], point.position[1], '#06c', point.name, 5));
  if (state.pose) {
    const [robotX, robotY] = state.pose.position;
    const yaw = state.pose.yaw;
    if (state.showLaser) {
      (state.laser?.points || []).forEach(point => {
        const x = robotX + point[0] * Math.cos(yaw) - point[1] * Math.sin(yaw);
        const y = robotY + point[0] * Math.sin(yaw) + point[1] * Math.cos(yaw);
        drawMarker(context, geometry, x, y, point[3] === 'front' ? '#d00' : '#f80', '', 2);
      });
    }
    drawMarker(context, geometry, robotX, robotY, '#080', '机器人', 7);
    const [px, py] = geometry.worldToCanvas(robotX, robotY);
    context.strokeStyle = '#080';
    context.beginPath();
    context.moveTo(px, py);
    context.lineTo(px + Math.cos(yaw) * 24, py - Math.sin(yaw) * 24);
    context.stroke();
  }
}

async function readAll() {
  const snapshot = await mapCommand('snapshot');
  if (snapshot) await applySnapshot(snapshot);
}

async function readMap() {
  state.map = await mapCommand('map');
  await decodeMap(state.map);
  updateMapStatus();
  draw();
}

async function readLaser() {
  state.laser = await mapCommand('laser');
  updateLaserStatus();
  draw();
}

async function readPoints() {
  state.points = await mapCommand('points');
  updatePoints();
  draw();
}

async function readBattery() {
  updateBattery(await mapCommand('battery'));
}

async function moveBase(values, label) {
  if (!window.confirm(`确认机器人周围安全，执行“${label}”？`)) return;
  await requireClient().send('base', { cmd: 'relative', x: 0, y: 0, rotate: 0, ...values }, { waitFor: 'done' });
}

function selectedPoint() {
  return document.querySelector('input[name="selected-point"]:checked')?.value;
}

element('broker').value = location.hostname || '10.42.1.101';
element('connect').addEventListener('click', () => runOperation('连接 MQTT', connect));
element('read-all').addEventListener('click', () => runOperation('读取全部', readAll));
element('read-map').addEventListener('click', () => runOperation('读取地图', readMap));
element('read-laser').addEventListener('click', () => runOperation('读取激光点', readLaser));
element('read-points').addEventListener('click', () => runOperation('读取地图点位', readPoints));
element('read-battery').addEventListener('click', () => runOperation('读取电量', readBattery));

element('show-map').addEventListener('change', event => {
  state.showMap = event.target.checked;
  draw();
});
element('show-laser').addEventListener('change', event => {
  state.showLaser = event.target.checked;
  draw();
});

function setZoom(zoom) {
  state.zoom = Math.min(4, Math.max(0.25, zoom));
  element('zoom-status').textContent = `${Math.round(state.zoom * 100)}%`;
  draw();
}

element('zoom-in').addEventListener('click', () => setZoom(state.zoom * 1.25));
element('zoom-out').addEventListener('click', () => setZoom(state.zoom / 1.25));

element('move-step').addEventListener('input', event => {
  element('move-step-value').textContent = `${event.target.value} mm`;
});
element('rotate-step').addEventListener('input', event => {
  element('rotate-step-value').textContent = `${event.target.value}°`;
});

const distance = () => Number(element('move-step').value);
const angle = () => Number(element('rotate-step').value);
element('move-forward').addEventListener('click', () => runOperation('前进', () => moveBase({ x: distance() }, '前进')));
element('move-backward').addEventListener('click', () => runOperation('后退', () => moveBase({ x: -distance() }, '后退')));
element('move-left').addEventListener('click', () => runOperation('左移', () => moveBase({ y: distance() }, '左移')));
element('move-right').addEventListener('click', () => runOperation('右移', () => moveBase({ y: -distance() }, '右移')));
element('rotate-ccw').addEventListener('click', () => runOperation('逆时针', () => moveBase({ rotate: angle() }, '逆时针')));
element('rotate-cw').addEventListener('click', () => runOperation('顺时针', () => moveBase({ rotate: -angle() }, '顺时针')));
element('stop').addEventListener('click', () => runOperation('立刻停止', () => requireClient().send('base', { cmd: 'stop' })));

element('save-current').addEventListener('click', () => runOperation('保存当前位置', async () => {
  const name = element('point-name').value.trim();
  if (!name) throw new Error('请输入点位名称');
  await mapCommand('save_current', { name });
}));
element('sync-points').addEventListener('click', () => runOperation('同步地图点位', async () => {
  const result = await mapCommand('sync_points');
  element('operation-status').textContent = `同步地图点位：新增 ${result.added}，更新 ${result.updated}`;
  await delay(0);
}));
element('goto-point').addEventListener('click', () => runOperation('到点', async () => {
  const name = selectedPoint();
  if (!name) throw new Error('请先选择点位');
  if (!window.confirm(`确认机器人周围安全，运动到点位“${name}”？`)) return;
  await requireClient().send('base', { cmd: 'point', name }, { waitFor: 'done' });
}));

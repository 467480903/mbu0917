import { MqttTransport } from '/js/core/mqtt-transport.js';
import { ServiceClient } from '/js/core/service-client.js';

const cameras = [
  'kHeadColor',
  'kHeadDepth',
  'kHandLeftColor',
  'kHandRightColor',
];
const state = { client: null, opened: new Set() };
const logs = [];
const element = id => document.querySelector(`#${id}`);

function printablePayload(payload) {
  const copy = { ...payload };
  if (typeof copy.result === 'string' && copy.result.length > 200) {
    copy.result = `[JPEG Base64，${copy.result.length} 字符]`;
  }
  return copy;
}

function appendLog(direction, topic, payload) {
  logs.push(`${direction} ${topic}\n${JSON.stringify(printablePayload(payload))}`);
  element('log').textContent = logs.join('\n\n');
}

function requireClient() {
  if (!state.client) throw new Error('请先连接 MQTT');
  return state.client;
}

function waitForImage(image) {
  if (image.complete && image.naturalWidth > 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error('图片加载失败'));
  });
}

async function connect() {
  const transport = new MqttTransport({
    host: element('broker').value,
    port: Number(element('port').value),
  });
  const client = new ServiceClient(transport, appendLog);
  await client.connect();
  state.client = client;
  element('connection-status').textContent = '已连接';
}

async function runOperation(label, action) {
  element('operation-status').textContent = `${label}：执行中`;
  try {
    await action();
    element('operation-status').textContent = `${label}：成功`;
  } catch (error) {
    element('operation-status').textContent = `${label}：失败，${error.message}`;
  }
}

async function openCamera(camera) {
  const response = await requireClient().send('camera', { cmd: 'get_image', camera });
  if (!response.result) throw new Error(`${camera} 没有图像数据`);
  const image = element(`image-${camera}`);
  image.hidden = false;
  image.src = `data:image/jpeg;base64,${response.result}`;
  await waitForImage(image);
  state.opened.add(camera);
  element(`status-${camera}`).textContent =
    `已打开，${image.naturalWidth}×${image.naturalHeight}`;
}

function closeCamera(camera) {
  const image = element(`image-${camera}`);
  image.removeAttribute('src');
  image.hidden = true;
  state.opened.delete(camera);
  element(`status-${camera}`).textContent = '已关闭';
}

async function captureCamera(camera) {
  if (!state.opened.has(camera)) throw new Error('请先打开该相机');
  const response = await requireClient().send('camera', { cmd: 'capture', camera });
  const filename = response.result;
  if (!filename) throw new Error('服务端没有返回保存文件名');
  const latest = `${camera}-latest.jpg`;
  const image = element(`image-${camera}`);
  image.hidden = false;
  image.src = `/images/${encodeURIComponent(filename)}?time=${Date.now()}`;
  await waitForImage(image);
  element(`saved-${camera}`).textContent = `已保存：${filename}；最新图片：${latest}`;
}

async function captureAll() {
  const response = await requireClient().send('camera', { cmd: 'capture_all' });
  const results = Array.isArray(response.result) ? response.result : [];
  if (results.length !== cameras.length) {
    throw new Error(`只保存成功 ${results.length}/${cameras.length} 路相机`);
  }
  for (const result of results) {
    element(`saved-${result.camera}`).textContent =
      `已保存：${result.file}；最新图片：${result.camera}-latest.jpg`;
  }
}

element('broker').value = location.hostname || '10.42.1.101';
element('connect').addEventListener('click', () => runOperation('连接 MQTT', connect));
element('capture-all').addEventListener('click', () => runOperation('全部拍照', captureAll));

for (const camera of cameras) {
  element(`open-${camera}`).addEventListener(
    'click', () => runOperation(`${camera} 打开`, () => openCamera(camera)));
  element(`close-${camera}`).addEventListener(
    'click', () => runOperation(`${camera} 关闭`, () => closeCamera(camera)));
  element(`capture-${camera}`).addEventListener(
    'click', () => runOperation(`${camera} 拍照`, () => captureCamera(camera)));
}

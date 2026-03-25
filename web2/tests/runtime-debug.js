const TOPICS = {
  control: '/humanoid/programs/control',
  step: '/humanoid/programs/step',
  codes: '/humanoid/programs/codes',
  files: '/humanoid/programs/files',
  status: '/humanoid/programs/status',
};

const query = new URLSearchParams(location.search);
const mockMode = query.get('live') !== '1';
const logs = [];
let client = null;
let connected = false;
let mockStep = 0;
let pendingStart = null;

const mockCode = `from runtime2 import G2

数字 = [1, 2, 3]
合计 = sum(数字)
print(f"计算结果: {合计}")
`;
const mockLines = [
  [3, '数字 = [1, 2, 3]'],
  [4, '合计 = sum(数字)'],
  [5, 'print(f"计算结果: {合计}")'],
];

function appendLog(direction, topic, payload) {
  logs.push(`${direction} ${topic}\n${JSON.stringify(payload)}`);
  document.querySelector('#log').textContent = logs.join('\n\n');
}

function receive(topic, payload) {
  appendLog('接收', topic, payload);
  if (topic === TOPICS.files) {
    const select = document.querySelector('#programs');
    select.replaceChildren(...payload.files.map(filename => new Option(filename, filename)));
  } else if (topic === TOPICS.codes) {
    document.querySelector('#source-code').textContent = payload.code;
  } else if (topic === TOPICS.step) {
    document.querySelector('#current-line').textContent = String(payload.lineno);
    document.querySelector('#current-code').textContent = payload.code;
    document.querySelector('#debug-status').textContent = payload.waiting ? '等待下一步' : '运行中';
  } else if (topic === TOPICS.status) {
    document.querySelector('#debug-status').textContent = payload.state || '未知';
    if (payload.state === 'copied' && pendingStart
        && payload.filename === pendingStart.filename) {
      const command = pendingStart.command;
      pendingStart = null;
      send(command);
    } else if (payload.state === 'error') {
      pendingStart = null;
    }
  }
}

function mockReceive(command, data) {
  if (command === 'read_files') {
    receive(TOPICS.files, {
      command,
      success: true,
      files: ['debug_demo.py', 'demo.py', 'long_action_test.py'],
    });
  } else if (command === 'copy') {
    receive(TOPICS.status, { command, success: true, state: 'copied', filename: data });
  } else if (command === 'codes') {
    receive(TOPICS.codes, { command, success: true, filename: 'main.py', code: mockCode });
  } else if (command === 'run') {
    receive(TOPICS.status, { command, success: true, state: 'running' });
    setTimeout(() => {
      receive(TOPICS.status, { command, success: true, state: 'completed' });
    }, 30);
  } else if (command === 'debug') {
    mockStep = 0;
    receive(TOPICS.status, { command, success: true, state: 'debugging' });
    const [lineno, code] = mockLines[mockStep];
    receive(TOPICS.step, { command, filename: 'main.py', lineno, code, waiting: true });
  } else if (command === 'next') {
    mockStep += 1;
    if (mockStep < mockLines.length) {
      const [lineno, code] = mockLines[mockStep];
      receive(TOPICS.step, { command: 'debug', filename: 'main.py', lineno, code, waiting: true });
    } else {
      receive(TOPICS.status, { command: 'debug', success: true, state: 'completed' });
    }
  } else if (command === 'stop') {
    receive(TOPICS.status, { command, success: true, state: 'stopped' });
  }
}

function send(command, data = undefined) {
  if (!connected) {
    document.querySelector('#debug-status').textContent = '请先连接 MQTT';
    return;
  }
  const payload = { command };
  if (data !== undefined) payload.data = data;
  appendLog('发送', TOPICS.control, payload);
  if (mockMode) {
    setTimeout(() => mockReceive(command, data), 20);
    return;
  }
  const message = new window.Paho.Message(JSON.stringify(payload));
  message.destinationName = TOPICS.control;
  message.qos = 2;
  client.send(message);
}

function startSelected(command) {
  const filename = document.querySelector('#programs').value;
  if (!filename) {
    document.querySelector('#debug-status').textContent = '请先读取并选择程序';
    return;
  }
  if (!mockMode && !window.confirm(
    `即将${command === 'run' ? '执行' : '单步调试'} ${filename}。请确认机器人周围安全，是否继续？`,
  )) {
    return;
  }
  pendingStart = { command, filename };
  send('copy', filename);
}

function connect() {
  if (mockMode) {
    connected = true;
    document.querySelector('#connection-status').textContent = '已连接';
    return;
  }
  const host = document.querySelector('#broker').value;
  const port = Number(document.querySelector('#port').value);
  client = new window.Paho.Client(host, port, `runtime_debug_${Date.now()}`);
  client.onMessageArrived = message => {
    receive(message.destinationName, JSON.parse(message.payloadString));
  };
  client.onConnectionLost = () => {
    connected = false;
    document.querySelector('#connection-status').textContent = '连接已断开';
  };
  client.connect({
    useSSL: false,
    timeout: 5,
    onSuccess: () => {
      connected = true;
      Object.values(TOPICS).filter(topic => topic !== TOPICS.control)
        .forEach(topic => client.subscribe(topic, { qos: 2 }));
      document.querySelector('#connection-status').textContent = '已连接';
    },
    onFailure: error => {
      document.querySelector('#connection-status').textContent = `连接失败: ${error.errorMessage}`;
    },
  });
}

document.querySelector('#mode').textContent = mockMode
  ? '模式：模拟 MQTT，不执行机器人程序'
  : '模式：真实 MQTT';
document.querySelector('#broker').value = location.hostname || '10.42.1.101';
document.querySelector('#connect').addEventListener('click', connect);
document.querySelector('#read-files').addEventListener('click', () => send('read_files'));
document.querySelector('#copy').addEventListener('click', () => {
  const filename = document.querySelector('#programs').value;
  if (filename) send('copy', filename);
});
document.querySelector('#run-selected').addEventListener('click', () => startSelected('run'));
document.querySelector('#debug-selected').addEventListener('click', () => startSelected('debug'));
document.querySelector('#read-code').addEventListener('click', () => send('codes'));
document.querySelector('#debug').addEventListener('click', () => send('debug'));
document.querySelector('#next').addEventListener('click', () => send('next'));
document.querySelector('#stop').addEventListener('click', () => send('stop'));

if (mockMode) connect();

const groups = [
  {
    title: '概览',
    items: [
      { id: 'model', label: '机器人模型', description: '查看真实 URDF 模型，支持旋转与缩放。', src: '/tests/urdf.html' },
    ],
  },
  {
    title: '示教',
    items: [
      { id: 'joint-teaching', label: '关节示教', description: '读取、微调和保存全身、左右臂或单关节变量。', src: '/tests/joint-teaching.html' },
      { id: 'pose-teaching', label: '末端与夹爪', description: '读取和控制左右末端位姿，同时控制双夹爪。', src: '/tests/pose-teaching.html' },
    ],
  },
  {
    title: '数据与程序',
    items: [
      { id: 'variables', label: '变量管理', description: '按类型查看 SQLite 变量，并创建或执行变量。', src: '/tests/datastore.html' },
      { id: 'programs', label: '程序调试', description: '管理程序文件，运行并逐行单步调试。', src: '/tests/runtime-debug.html' },
    ],
  },
  {
    title: '设备',
    items: [
      { id: 'map', label: '地图与底盘', description: '显示地图、激光、机器人位置和地图点位。', src: '/service-tests/maptest.html', realOnly: true },
      { id: 'camera', label: '摄像头', description: '打开、关闭和拍摄机器人相机画面。', src: '/service-tests/camera.html', realOnly: true },
    ],
  },
  {
    title: '维护',
    items: [
      { id: 'diagnostics', label: '服务诊断', description: '直接编辑 JSON，检查所有 serivces2 MQTT 命令。', src: '/console.html?mock=1' },
      { id: 'tests', label: '功能测试目录', description: '打开所有互相独立的简洁功能测试页面。', src: '/tests/index.html' },
    ],
  },
];

const items = groups.flatMap(group => group.items);
const query = new URLSearchParams(location.search);
const forceMock = query.get('mock') === '1';
const initialId = query.get('view');
let active = items.find(item => item.id === initialId) || items[0];

const root = document.querySelector('#app');

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

function sourceFor(item) {
  if (item.realOnly || item.id === 'model' || item.id === 'tests' || item.id === 'diagnostics') return item.src;
  if (forceMock) return item.src;
  return `${item.src}${item.src.includes('?') ? '&' : '?'}live=1`;
}

function render() {
  root.innerHTML = `
    <div class="integrated-shell">
      <aside class="integrated-sidebar">
        <div class="integrated-brand"><strong>G2</strong><span>集成操作台</span></div>
        ${groups.map(group => `
          <section class="integrated-nav-group">
            <h2>${escapeHtml(group.title)}</h2>
            ${group.items.map(item => `
              <button type="button" class="integrated-nav-item ${item.id === active.id ? 'active' : ''}" data-view="${item.id}">
                ${escapeHtml(item.label)}
              </button>`).join('')}
          </section>`).join('')}
      </aside>
      <main class="integrated-main">
        <header class="integrated-header">
          <div>
            <div class="eyebrow">G2 / ${escapeHtml(active.id)}</div>
            <h1>${escapeHtml(active.label)}</h1>
            <p>${escapeHtml(active.description)}</p>
          </div>
          <div class="integrated-state">
            <span class="dot connected"></span>
            ${active.realOnly ? '真实机器人数据' : 'MQTT 功能页面'}
          </div>
        </header>
        <section class="integrated-stage">
          <iframe id="function-frame" title="${escapeHtml(active.label)}" src="${sourceFor(active)}"></iframe>
        </section>
        <footer class="integrated-actions">
          <span>独立页面保持简洁；这里仅在集成模式下应用统一样式。</span>
          <button type="button" id="reload-view">刷新当前功能</button>
          <a id="open-view" href="${sourceFor(active)}" target="_blank" rel="noopener">独立打开</a>
        </footer>
      </main>
    </div>`;

  root.querySelectorAll('[data-view]').forEach(button => {
    button.addEventListener('click', () => selectView(button.dataset.view));
  });
  root.querySelector('#reload-view').addEventListener('click', () => {
    const frame = root.querySelector('#function-frame');
    frame.src = frame.src;
  });
  root.querySelector('#function-frame').addEventListener('load', applyIntegratedStyle);
}

function selectView(id) {
  const next = items.find(item => item.id === id);
  if (!next) return;
  active = next;
  query.set('view', id);
  history.replaceState(null, '', `?${query.toString()}`);
  render();
}

function applyIntegratedStyle(event) {
  const doc = event.target.contentDocument;
  if (!doc || doc.querySelector('style[data-integrated-style]')) return;
  const style = doc.createElement('style');
  style.dataset.integratedStyle = 'true';
  style.textContent = `
    :root { font-family: Inter, "Noto Sans SC", system-ui, sans-serif; color: #172033; }
    body { max-width: 1080px; margin: 0 auto; padding: 24px; background: #fff; }
    h1 { font-size: 24px; margin-top: 0; }
    h2 { margin-top: 28px; font-size: 18px; }
    fieldset { margin: 14px 0; padding: 16px; border: 1px solid #dfe3ea; border-radius: 10px; }
    button, input, select, textarea { font: inherit; }
    button { padding: 8px 13px; border: 1px solid #b9cdfb; border-radius: 7px; color: #1d4ed8; background: #f7faff; cursor: pointer; }
    button:hover { background: #e8f0ff; }
    button:disabled { color: #98a2b3; border-color: #dfe3ea; background: #f5f6f8; }
    input, select, textarea { padding: 7px 9px; border: 1px solid #cfd5df; border-radius: 6px; }
    table { width: 100%; margin: 16px auto; border-collapse: collapse; }
    th, td { padding: 9px; border: 1px solid #dfe3ea; text-align: left; }
    th { background: #f8fafc; }
    canvas, img { display: block; max-width: 100%; margin: 16px auto; }
    pre { padding: 12px; overflow: auto; background: #f8fafc; border: 1px solid #dfe3ea; border-radius: 8px; }
  `;
  doc.head.appendChild(style);
}

render();

import { mqttClient } from './mqtt-client.js';

const CAMERA_NAMES = [
    ['kHeadColor', '头部RGB'], ['kHeadDepth', '头部深度'],
    ['kHandLeftColor', '左手腕'], ['kHandRightColor', '右手腕'],
];

export default {
    name: 'CameraView',
    props: { active: { type: Boolean, default: false } },
    data() {
        return {
            cameras: CAMERA_NAMES.map(([key, name]) => ({ key, name, image: '',
                streaming: false, continuous: false, busy: false, method: 'apriltag',
                analysisBusy: false, message: '未开启', frameAt: 0 })),
            floating: '', resultCamera: '', results: {}, pending: {},
            onChannel: null, ticker: null, lastConnected: false, now: Date.now(),
            floatBounds: { live: null, result: null }, floatGesture: null,
            frontFloat: 'live', onViewportResize: null,
        };
    },
    computed: {
        floatingCamera() { return this.cameras.find(cam => cam.key === this.floating); },
        selectedResult() { return this.results[this.resultCamera]; },
    },
    watch: {
        floating() { this.$nextTick(this.fitFloats); },
        resultCamera() { this.$nextTick(this.fitFloats); },
    },
    template: `
    <section v-show="active" class="camera1-panel">
      <div class="camera1-grid">
        <article v-for="cam in cameras" :key="cam.key" class="camera1-card" :aria-label="cam.name">
          <header><strong>{{ cam.name }}</strong><span>{{ liveLabel(cam) }}</span></header>
          <div class="camera1-picture">
            <img v-if="cam.image" :src="'data:image/jpeg;base64,' + cam.image" :alt="cam.name + '画面'" />
            <span v-else>等待画面</span>
          </div>
          <div class="camera1-tools">
            <button @click="command(cam, 'start')" :disabled="cam.busy || cam.streaming"><ui-icon name="power"/>开启</button>
            <button @click="command(cam, 'stop')" :disabled="cam.busy || (!cam.streaming && !cam.continuous)"><ui-icon name="stop"/>停止</button>
            <button @click="command(cam, 'capture')" :disabled="cam.busy"><ui-icon name="camera"/>拍摄</button>
            <button @click="command(cam, cam.continuous ? 'continuous_stop' : 'continuous_start')" :disabled="cam.busy" :aria-pressed="cam.continuous"><ui-icon name="repeat"/>{{ cam.continuous ? '停止连拍' : '连续拍照' }}</button>
            <button @click="floating = floating === cam.key ? '' : cam.key" :aria-pressed="floating === cam.key"><ui-icon name="camera"/>悬浮</button>
            <div class="camera1-analysis">
              <select v-model="cam.method" :aria-label="cam.name + '识别类型'" :disabled="cam.analysisBusy">
                <option value="apriltag">Apriltag 码识别</option><option value="llm">LLM 识别</option>
              </select>
              <button @click="analyze(cam)" :disabled="cam.analysisBusy || cam.busy"><ui-icon name="scan"/>{{ cam.analysisBusy ? '识别中' : '识别' }}</button>
            </div>
          </div>
          <p class="camera1-message" role="status">{{ cam.message }}</p>
        </article>
      </div>
      <p class="camera1-note">四路独立控制。连续拍照约 0.5 秒/张；LLM 会将所选相机的本次照片上传到硅基流，结果仅供观察。</p>
    </section>
    <Teleport to="body">
      <aside v-if="floatingCamera" ref="liveFloat" class="camera1-float camera1-live" :style="floatStyle('live')" @pointerdown="frontFloat = 'live'" aria-label="悬浮摄像头">
        <header class="camera1-drag" title="拖动标题栏移动窗口" @pointerdown="beginFloat($event, 'live', 'drag')" @pointermove="moveFloat" @pointerup="endFloat" @pointercancel="endFloat" @lostpointercapture="endFloat"><strong>{{ floatingCamera.name }} · 悬浮画面</strong><button @click="floating = ''" aria-label="关闭悬浮画面"><ui-icon name="x"/></button></header>
        <img v-if="floatingCamera.image" :src="'data:image/jpeg;base64,' + floatingCamera.image" :alt="floatingCamera.name + '悬浮画面'" draggable="false" />
        <p v-else>请先开启该摄像头</p>
        <footer>{{ liveLabel(floatingCamera) }} · 切换菜单不关闭</footer>
        <button class="camera1-resize" aria-label="调整悬浮画面大小" title="拖动调整大小；方向键也可调整" @pointerdown="beginFloat($event, 'live', 'resize')" @pointermove="moveFloat" @pointerup="endFloat" @pointercancel="endFloat" @lostpointercapture="endFloat" @keydown="resizeFloatKey($event, 'live')"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13L13 3M8 13L13 8"/></svg></button>
      </aside>
      <aside v-if="selectedResult" ref="resultFloat" class="camera1-float camera1-result" :style="floatStyle('result')" @pointerdown="frontFloat = 'result'" aria-label="图像识别结果">
        <header class="camera1-drag" title="拖动标题栏移动窗口" @pointerdown="beginFloat($event, 'result', 'drag')" @pointermove="moveFloat" @pointerup="endFloat" @pointercancel="endFloat" @lostpointercapture="endFloat"><strong>{{ selectedResult.name }} · {{ selectedResult.method === 'llm' ? 'LLM' : 'Apriltag' }} 结果</strong><button @click="resultCamera = ''" aria-label="关闭识别结果"><ui-icon name="x"/></button></header>
        <img v-if="selectedResult.image" :src="'data:image/jpeg;base64,' + selectedResult.image" alt="本次识别图片及标注" draggable="false" />
        <p role="status">{{ selectedResult.message }}</p>
        <pre v-if="selectedResult.details">{{ selectedResult.details }}</pre>
        <button class="camera1-resize" aria-label="调整识别结果大小" title="拖动调整大小；方向键也可调整" @pointerdown="beginFloat($event, 'result', 'resize')" @pointermove="moveFloat" @pointerup="endFloat" @pointercancel="endFloat" @lostpointercapture="endFloat" @keydown="resizeFloatKey($event, 'result')"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13L13 3M8 13L13 8"/></svg></button>
      </aside>
    </Teleport>
    `,
    mounted() {
        this.onViewportResize = () => this.fitFloats();
        window.addEventListener('resize', this.onViewportResize);
        this.onChannel = (topic, data) => this.receive(topic, data);
        mqttClient.addCameraChannelCallback(this.onChannel);
        this.ticker = setInterval(() => {
            this.now = Date.now();
            const connected = mqttClient.connected;
            if (connected && !this.lastConnected) {
                this.cameras.forEach(cam => this.command(cam, 'status', true));
            }
            if (!connected) this.cameras.forEach(cam => { cam.message = 'MQTT 未连接，状态未知'; });
            this.lastConnected = connected;
            if (connected && Math.floor(this.now / 1000) % 10 === 0) {
                this.cameras.forEach(cam => {
                    this.command(cam, cam.streaming || cam.continuous ? 'keepalive' : 'status', true);
                });
            }
            for (const [id, task] of Object.entries(this.pending)) {
                if (this.now > task.deadline) {
                    delete this.pending[id];
                    const cam = this.cameras.find(c => c.key === task.camera);
                    cam.busy = false;
                    cam.message = '请求超时，请检查后台服务';
                    if (task.method) this.analysisError(cam, '识别超时，请检查后台服务');
                }
            }
        }, 1000);
    },
    beforeUnmount() {
        this.endFloat();
        window.removeEventListener('resize', this.onViewportResize);
        clearInterval(this.ticker);
        mqttClient.removeCameraChannelCallback(this.onChannel);
        this.cameras.forEach(cam => {
            if (cam.streaming || cam.continuous) this.command(cam, 'stop', true);
        });
    },
    methods: {
        floatStyle(kind) {
            const bounds = this.floatBounds[kind];
            return { zIndex: this.frontFloat === kind ? 1101 : 1100,
                ...(bounds ? { left: bounds.x + 'px', top: bounds.y + 'px',
                    width: bounds.width + 'px', height: bounds.height + 'px', right: 'auto', bottom: 'auto' } : {}) };
        },
        clampFloat(bounds) {
            const pad = 8, top = Math.min(76, window.innerHeight / 4);
            const maxWidth = Math.max(1, window.innerWidth - pad * 2);
            const maxHeight = Math.max(1, window.innerHeight - top - pad);
            const width = Math.max(Math.min(260, maxWidth), Math.min(bounds.width, maxWidth));
            const height = Math.max(Math.min(200, maxHeight), Math.min(bounds.height, maxHeight));
            return { width, height,
                x: Math.max(pad, Math.min(bounds.x, window.innerWidth - width - pad)),
                y: Math.max(top, Math.min(bounds.y, window.innerHeight - height - pad)) };
        },
        fitFloats() {
            for (const kind of ['live', 'result']) {
                const element = this.$refs[kind + 'Float'];
                if (!element) continue;
                const rect = element.getBoundingClientRect();
                this.floatBounds[kind] = this.clampFloat(this.floatBounds[kind] ||
                    { x: rect.x, y: rect.y, width: rect.width, height: rect.height });
            }
        },
        beginFloat(event, kind, mode) {
            if (event.button !== 0 || this.floatGesture || (mode === 'drag' && event.target.closest('button'))) return;
            event.preventDefault();
            this.fitFloats();
            this.frontFloat = kind;
            this.floatGesture = { kind, mode, pointerId: event.pointerId, target: event.currentTarget,
                startX: event.clientX, startY: event.clientY, bounds: { ...this.floatBounds[kind] } };
            event.currentTarget.setPointerCapture(event.pointerId);
        },
        moveFloat(event) {
            const gesture = this.floatGesture;
            if (!gesture || gesture.pointerId !== event.pointerId) return;
            const dx = event.clientX - gesture.startX, dy = event.clientY - gesture.startY;
            const bounds = { ...gesture.bounds };
            if (gesture.mode === 'drag') { bounds.x += dx; bounds.y += dy; }
            else {
                bounds.width = Math.min(bounds.width + dx, window.innerWidth - bounds.x - 8);
                bounds.height = Math.min(bounds.height + dy, window.innerHeight - bounds.y - 8);
            }
            this.floatBounds[gesture.kind] = this.clampFloat(bounds);
        },
        endFloat(event) {
            const gesture = this.floatGesture;
            if (!gesture || (event && event.pointerId !== gesture.pointerId)) return;
            // 快速拖动时最后一个 move 可能合并，使用松开位置完成本次操作。
            if (event?.type === 'pointerup') this.moveFloat(event);
            this.floatGesture = null;
            if (gesture.target.hasPointerCapture(gesture.pointerId)) gesture.target.releasePointerCapture(gesture.pointerId);
        },
        resizeFloatKey(event, kind) {
            const changes = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] };
            if (!changes[event.key]) return;
            event.preventDefault();
            this.fitFloats();
            const bounds = { ...this.floatBounds[kind] }, [dx, dy] = changes[event.key];
            bounds.width = Math.min(bounds.width + dx, window.innerWidth - bounds.x - 8);
            bounds.height = Math.min(bounds.height + dy, window.innerHeight - bounds.y - 8);
            this.floatBounds[kind] = this.clampFloat(bounds);
        },
        liveLabel(cam) {
            if (!mqttClient.connected) return '连接断开 / 状态未知';
            if (cam.continuous) return '连续拍照中';
            if (!cam.streaming) return '已停止（保留末帧）';
            return this.now - cam.frameAt < 4000 ? '实时画面' : '等待新帧';
        },
        send(topic, payload) {
            if (!mqttClient.connected) throw new Error('MQTT 未连接');
            mqttClient.publishToTopic(topic, payload);
        },
        command(cam, cmd, quiet = false, method = '') {
            const id = crypto.randomUUID ? crypto.randomUUID() : `camera-${Date.now()}-${Math.random()}`;
            try {
                this.send(`/humanoid/camera/${cam.key}/request`, { cmd, time: id });
                this.pending[id] = { camera: cam.key, cmd, method, quiet, deadline: Date.now() + 15000 };
                if (!quiet) cam.busy = true;
            } catch (error) {
                cam.message = error.message;
                if (method) this.analysisError(cam, error.message);
            }
        },
        analyze(cam) {
            cam.analysisBusy = true;
            this.resultCamera = cam.key;
            this.results[cam.key] = { name: cam.name, method: cam.method, image: '', details: '', message: '正在拍摄本次识别图片…' };
            this.command(cam, 'capture', false, cam.method);
        },
        analysisError(cam, message) {
            cam.analysisBusy = false;
            cam.message = message;
            if (this.results[cam.key]) this.results[cam.key].message = message;
        },
        receive(topic, data) {
            if (!data) return;
            if (topic.endsWith('/frame')) {
                const cam = this.cameras.find(c => c.key === data.camera);
                if (cam && cam.streaming && typeof data.image === 'string') {
                    cam.image = data.image;
                    cam.frameAt = Date.now();
                }
                return;
            }
            const task = this.pending[data.time];
            if (!task) return;
            const expected = task.cmd === 'detect_file'
                ? (task.method === 'llm' ? '/humanoid/vision/llm/result' : '/humanoid/apriltag/response/')
                : `/humanoid/camera/${task.camera}/response`;
            if (topic !== expected) return;
            delete this.pending[data.time];
            const cam = this.cameras.find(c => c.key === task.camera);
            if (!task.quiet) cam.busy = false;
            if (!data.success) {
                cam.message = data.error || '请求失败';
                if (task.method) this.analysisError(cam, cam.message);
                return;
            }
            if (data.state) {
                cam.streaming = data.state.streaming;
                cam.continuous = data.state.continuous;
                cam.message = cam.continuous ? `连拍中，已保存 ${data.state.saved_count} 张` : (cam.streaming ? '采集中' : '已停止');
            }
            if (task.cmd === 'capture') {
                cam.image = data.image;
                cam.message = `已保存：${data.file}`;
                if (task.method) {
                    const result = this.results[cam.key];
                    result.image = data.image;
                    result.message = '已拍照，正在识别…';
                    const destination = task.method === 'llm' ? '/humanoid/vision/llm/request' : '/humanoid/apriltag/request/';
                    this.pending[data.time] = { ...task, cmd: 'detect_file', deadline: Date.now() + 140000 };
                    try {
                        this.send(destination, { cmd: task.method === 'llm' ? 'detect_file' : 'detect_saved',
                            time: data.time, camera: cam.key, file: data.file });
                    } catch (error) {
                        delete this.pending[data.time];
                        this.analysisError(cam, error.message);
                    }
                }
            } else if (task.cmd === 'detect_file') {
                cam.analysisBusy = false;
                const result = this.results[cam.key];
                if (task.method === 'llm') {
                    const { image, ...details } = data.result;
                    result.image = image;
                    result.details = JSON.stringify(details, null, 2);
                    result.message = data.result.found ? '识别完成：蓝线为模型估算结果，不用于运动控制' : '未找到目标线段';
                } else {
                    result.message = `识别完成：${data.result.length} 个 Apriltag`;
                    result.details = JSON.stringify(data.result.map(tag => ({ id: tag.id, center: tag.center, corners: tag.corners })), null, 2);
                    this.drawTags(result, data.result);
                }
                cam.message = result.message;
            }
        },
        drawTags(result, tags) {
            const photo = new Image();
            photo.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = photo.naturalWidth; canvas.height = photo.naturalHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(photo, 0, 0);
                ctx.strokeStyle = '#00499d'; ctx.lineWidth = 4; ctx.font = '22px sans-serif';
                tags.forEach(tag => {
                    if (!Array.isArray(tag.corners) || tag.corners.length !== 4) return;
                    ctx.beginPath(); tag.corners.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p));
                    ctx.closePath(); ctx.stroke();
                    ctx.fillStyle = '#ffffff'; ctx.fillRect(tag.center[0], tag.center[1] - 24, 90, 28);
                    ctx.fillStyle = '#00499d'; ctx.fillText(`ID ${tag.id}`, tag.center[0] + 3, tag.center[1]);
                });
                result.image = canvas.toDataURL('image/jpeg', .9).split(',')[1];
            };
            photo.src = 'data:image/jpeg;base64,' + result.image;
        },
    },
};

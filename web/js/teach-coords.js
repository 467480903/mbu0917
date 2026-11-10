// teach-coords.js
// 示教（坐标）组件：左右手末端坐标 XYZ + RX RY RZ
// 左上角：左手/右手坐标系下拉菜单
// 右下角：保存末端位姿按钮

import { mqttClient } from './mqtt-client.js';

export default {
    name: 'TeachCoords',
    props: { canManage: { type: Boolean, default: false } },
    watch: { canManage(allowed) { if (!allowed) this.showSaveDialog = false; } },
    inject: ['getRobotStatus'],
    template: `
    <div class="panel tc-panel">
        <div class="tc-content">
        <div class="tc-hands-wrap">
            <!-- 左手 -->
            <div class="tc-hand-group tc-hand-left">
                <h6 class="tc-hand-title">左手</h6>
                <div class="coord-row" v-for="ax in axes" :key="'L_'+ax">
                    <span class="axis-label">{{ ax.toUpperCase() }}</span>
                    <button class="minus" aria-label="减小" @click="step('left', ax, -stepFor(ax))"><ui-icon name="minus"></ui-icon></button>
                    <span class="val">{{ format(left[ax]) }}</span>
                    <button class="plus" aria-label="增加" @click="step('left', ax,  stepFor(ax))"><ui-icon name="plus"></ui-icon></button>
                </div>
                <!-- 左手夹爪 -->
                <div class="gripper-row">
                    <span class="gripper-label">夹爪</span>
                    <div class="gripper-slider-wrap">
                        <span class="gripper-end-label">开</span>
                        <input type="range"
                               class="gripper-slider"
                               min="-0.75" max="0" step="0.01"
                               v-model.number="leftGripper"
                               @change="setGripper('left', leftGripper)" />
                        <span class="gripper-end-label">合</span>
                        <span class="gripper-val">{{ formatGripper(leftGripper) }}</span>
                    </div>
                </div>
            </div>

            <!-- 右手 -->
            <div class="tc-hand-group tc-hand-right">
                <h6 class="tc-hand-title">右手</h6>
                <div class="coord-row" v-for="ax in axes" :key="'R_'+ax">
                    <span class="axis-label">{{ ax.toUpperCase() }}</span>
                    <button class="minus" aria-label="减小" @click="step('right', ax, -stepFor(ax))"><ui-icon name="minus"></ui-icon></button>
                    <span class="val">{{ format(right[ax]) }}</span>
                    <button class="plus" aria-label="增加" @click="step('right', ax,  stepFor(ax))"><ui-icon name="plus"></ui-icon></button>
                </div>
                <!-- 右手夹爪 -->
                <div class="gripper-row">
                    <span class="gripper-label">夹爪</span>
                    <div class="gripper-slider-wrap">
                        <span class="gripper-end-label">开</span>
                        <input type="range"
                               class="gripper-slider"
                               min="-0.75" max="0" step="0.01"
                               v-model.number="rightGripper"
                               @change="setGripper('right', rightGripper)" />
                        <span class="gripper-end-label">合</span>
                        <span class="gripper-val">{{ formatGripper(rightGripper) }}</span>
                    </div>
                </div>
            </div>

            <!-- 腰腿：基座坐标系下 X 前后、Z 上下 -->
            <div class="tc-hand-group tc-waist-group">
                <h6 class="tc-hand-title">腰腿</h6>
                <div class="coord-row waist-coord-row">
                    <span class="axis-label">X</span>
                    <button class="minus" aria-label="腰腿向后"
                            @click="moveWaist('forward', -stepSize)">
                        <ui-icon name="down"></ui-icon>后
                    </button>
                    <span class="val">{{ format(waist.x) }}</span>
                    <button class="plus" aria-label="腰腿向前"
                            @click="moveWaist('forward', stepSize)">
                        <ui-icon name="up"></ui-icon>前
                    </button>
                </div>
                <div class="coord-row waist-coord-row">
                    <span class="axis-label">Z</span>
                    <button class="minus" aria-label="腰腿向下"
                            @click="moveWaist('up', -stepSize)">
                        <ui-icon name="down"></ui-icon>下
                    </button>
                    <span class="val">{{ format(waist.z) }}</span>
                    <button class="plus" aria-label="腰腿向上"
                            @click="moveWaist('up', stepSize)">
                        <ui-icon name="up"></ui-icon>上
                    </button>
                </div>
                <p class="tc-waist-note">基座坐标系 · 保持上身俯仰姿态</p>
            </div>
        </div>
        </div>

        <!-- 底部操作栏：按钮组 + 右侧功能描述 -->
        <div class="tc-actionbar">
            <div class="tc-actions">
                <button v-if="canManage" class="djc-btn djc-btn-read" @click="showSaveDialog = true">
                    <ui-icon name="save"></ui-icon>保存
                </button>
                <div class="tc-frame-controls">
                    <div class="coord-sys-row">
                        <label class="coord-sys-label">左手坐标系</label>
                        <select v-model="leftFrame" class="coord-sys-select">
                            <option value="base">base</option>
                            <option value="ltool0">ltool0</option>
                            <option value="lobj0">lobj0</option>
                        </select>
                    </div>
                    <div class="coord-sys-row">
                        <label class="coord-sys-label">右手坐标系</label>
                        <select v-model="rightFrame" class="coord-sys-select">
                            <option value="base">base</option>
                            <option value="rtool0">rtool0</option>
                            <option value="robj0">robj0</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="tc-info">
                <span class="tc-info-item">
                    <span class="tc-info-label">步长</span>
                    <input type="number" v-model.number="stepSize" step="0.01" min="0.001" class="tc-step-input">
                    <span class="tc-info-unit">(米)</span>
                </span>
                <span class="tc-info-item">
                    <span class="tc-info-label">旋转步长</span>
                    <input type="number" v-model.number="rotStepSize" step="0.01" min="0.001" class="tc-step-input">
                    <span class="tc-info-unit">(弧度)</span>
                </span>
                <span class="tc-status">
                    <span class="tc-conn-dot"></span>
                    <span class="tc-conn-text">已连接实时状态</span>
                </span>
            </div>
        </div>

        <!-- 保存弹窗 -->
        <div v-if="canManage && showSaveDialog" class="save-overlay" @click.self="showSaveDialog = false">
            <div class="save-dialog">
                <h6 style="color:#00499d; margin-bottom:16px;">保存姿态变量</h6>

                <div class="form-row">
                    <label>名称</label>
                    <input type="text" v-model="saveName" placeholder="例如 pick"
                           @keyup.enter="doSave" />
                </div>

                <div style="margin-bottom:16px;">
                    <label style="display:block; color:#606266; font-size:14px; margin-bottom:8px;">类型</label>
                    <div class="radio-group">
                        <label v-for="t in saveTypes" :key="t.value">
                            <input type="radio" :value="t.value" v-model="saveType" /> {{ t.label }}
                        </label>
                    </div>
                </div>

                <div class="step-actions">
                    <button class="nav-btn" @click="showSaveDialog = false"><ui-icon name="x"></ui-icon>取消</button>
                    <button class="nav-btn start-btn" @click="doSave" :disabled="!saveName"><ui-icon name="save"></ui-icon>保存</button>
                </div>
            </div>
        </div>
    </div>
    `,
    data() {
        return {
            stepSize: 0.02,
            rotStepSize: 0.02,
            axes: ['x', 'y', 'z', 'rx', 'ry', 'rz'],
            left:  { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 },
            right: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 },
            waist: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 },
            leftGripper: -0.75,
            rightGripper: -0.75,
            // 坐标系
            leftFrame: 'base',
            rightFrame: 'base',
            // 保存弹窗
            showSaveDialog: false,
            saveName: '',
            saveType: 'both',
            saveTypes: [
                { value: 'left', label: '左手' },
                { value: 'right', label: '右手' },
                { value: 'both', label: '左右手' },
                { value: 'waist', label: '腰部' },
            ],
            _unwatch: null
        };
    },
    methods: {
        // 根据轴类型返回对应步长：XYZ 用 stepSize（米），RX/RY/RZ 用 rotStepSize（弧度）
        stepFor(axis) {
            return ['x', 'y', 'z'].includes(axis) ? this.stepSize : this.rotStepSize;
        },
        step(side, axis, delta) {
            this[side][axis] += delta;
            // 发布 offset_move 命令
            this.publishOffset(side, axis, delta);
        },
        format(v) {
            return v.toFixed(3);
        },
        // 发布末端相对移动命令
        publishOffset(side, axis, delta) {
            const isTranslation = ['x', 'y', 'z'].includes(axis);
            // 平移：米→毫米；旋转：弧度→度
            const value = isTranslation ? delta * 1000 : delta * (180 / Math.PI);
            const key = side === 'left' ? 'l' + axis : 'r' + axis;
            const data = { [key]: value };
            mqttClient.publishCommand('offset_move', data);
        },
        // 腰腿平面运动：forward 对应基座 X，up 对应基座 Z，单位米。
        moveWaist(axis, delta) {
            const data = { forward: 0, up: 0 };
            data[axis] = Number(delta);
            mqttClient.publishCommand('waist_move', data);
        },
        // 设置夹爪开合度（滑动条 @change 触发）
        setGripper(side, pos) {
            const data = side === 'left' ? { left: pos } : { right: pos };
            mqttClient.publishCommand('grab', data);
            console.log(`[夹爪] ${side} pos=${pos.toFixed(2)}`);
        },
        formatGripper(v) {
            return v.toFixed(2);
        },
        // 从 MQTT 状态刷新末端坐标
        syncFromStatus(status) {
            if (!status) return;
            if (status.left_ee) {
                const p = status.left_ee.position || [];
                const o = status.left_ee.orientation || [];
                this.left.x  = p[0] || 0;
                this.left.y  = p[1] || 0;
                this.left.z  = p[2] || 0;
                this.left.rx = o[0] || 0;
                this.left.ry = o[1] || 0;
                this.left.rz = o[2] || 0;
            }
            if (status.right_ee) {
                const p = status.right_ee.position || [];
                const o = status.right_ee.orientation || [];
                this.right.x  = p[0] || 0;
                this.right.y  = p[1] || 0;
                this.right.z  = p[2] || 0;
                this.right.rx = o[0] || 0;
                this.right.ry = o[1] || 0;
                this.right.rz = o[2] || 0;
            }
            if (status.waist_pose) {
                this.waist.x = Number(status.waist_pose.x) || 0;
                this.waist.y = Number(status.waist_pose.y) || 0;
                this.waist.z = Number(status.waist_pose.z) || 0;
                this.waist.rx = Number(status.waist_pose.rx) || 0;
                this.waist.ry = Number(status.waist_pose.ry ?? status.waist_pose.pitch) || 0;
                this.waist.rz = Number(status.waist_pose.rz) || 0;
            }
        },
        // 收集当前末端位姿
        collectData() {
            if (this.saveType === 'left') {
                return { ...this.left };
            } else if (this.saveType === 'right') {
                return { ...this.right };
            } else if (this.saveType === 'waist') {
                return { ...this.waist };
            } else {
                // both
                return {
                    left:  { ...this.left },
                    right: { ...this.right }
                };
            }
        },
        // 保存末端位姿到服务端
        doSave() {
            if (!this.canManage) return;
            if (!this.saveName) return;
            const data = this.collectData();
            mqttClient.publishDataSave({
                command: 'save_position',
                type: this.saveType,
                name: this.saveName,
                data: data
            });
            console.log(`[保存位姿] type=${this.saveType}, name=${this.saveName}`);
            this.showSaveDialog = false;
            this.saveName = '';
        }
    },
    mounted() {
        this._unwatch = this.$watch(
            () => this.getRobotStatus(),
            (newStatus) => {
                this.syncFromStatus(newStatus);
            },
            { immediate: true }
        );
    },
    beforeUnmount() {
        if (this._unwatch) this._unwatch();
    }
};

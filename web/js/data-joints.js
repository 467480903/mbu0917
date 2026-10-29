// data-joints.js
// 关节角度轴数据管理页面：读取、到位、更新、删除
// 只处理 joints 数据，不处理坐标和地图点位

import { mqttClient } from './mqtt-client.js';

export default {
    name: 'DataJoints',
    inject: ['getRobotStatus'],
    template: `
    <div class="panel djc-panel">
        <div class="djc-table-wrap" v-if="items.length > 0">
            <table class="djc-table">
                <thead>
                    <tr>
                        <th>分类</th>
                        <th>类型</th>
                        <th>名称</th>
                        <th>数据摘要</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-for="(item, idx) in items" :key="idx"
                        :class="{ 'djc-row-selected': selectedIdx === idx }"
                        @click="selectRow(idx)">
                        <td>关节</td>
                        <td>{{ formatType(item) }}</td>
                        <td>{{ item.name }}</td>
                        <td class="djc-summary">{{ summarize(item) }}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div v-else class="djc-empty">
            点击右下角「读取」加载关节角度轴数据
        </div>

        <!-- 底部固定操作栏 -->
        <div class="djc-actionbar">
            <div class="djc-left-info">
                <span v-if="items.length > 0" class="djc-count-bar">共 {{ items.length }} 条</span>
                <span v-if="selectedItem" class="djc-sel-info">
                    选中: 关节 · {{ formatType(selectedItem) }} · {{ selectedItem.name }}
                </span>
            </div>
            <div class="djc-actions">
                <div class="djc-speed-control">
                    <span class="djc-speed-label">速度</span>
                    <button class="djc-speed-btn" aria-label="减小速度"
                            @click="adjustSpeed(-speedStep)"><ui-icon name="minus"></ui-icon></button>
                    <input class="djc-speed-input" type="number"
                           v-model.number="jointSpeed"
                           :min="minSpeed" :max="maxSpeed" :step="speedStep"
                           @change="normalizeSpeed" />
                    <button class="djc-speed-btn" aria-label="增加速度"
                            @click="adjustSpeed(speedStep)"><ui-icon name="plus"></ui-icon></button>
                    <span class="djc-speed-unit">rad/s</span>
                </div>
                <button class="djc-btn djc-btn-read" @click="readData"><ui-icon name="refresh"></ui-icon>读取</button>
                <button class="djc-btn djc-btn-go" :disabled="!selectedItem" @click="confirmGoTo"><ui-icon name="crosshair"></ui-icon>到位</button>
                <button class="djc-btn djc-btn-update" :disabled="!selectedItem" @click="confirmUpdate"><ui-icon name="edit"></ui-icon>更新</button>
                <button class="djc-btn djc-btn-delete" :disabled="!selectedItem" @click="confirmDelete"><ui-icon name="trash"></ui-icon>删除</button>
            </div>
        </div>

        <!-- 确认弹窗 -->
        <div v-if="confirmDialog.visible" class="djc-overlay" @click.self="cancelConfirm">
            <div class="djc-dialog">
                <div class="djc-dialog-header">
                    <span :class="['djc-dialog-icon', confirmDialog.iconClass]">{{ confirmDialog.icon }}</span>
                    <span class="djc-dialog-title">{{ confirmDialog.title }}</span>
                </div>
                <div class="djc-dialog-body">
                    {{ confirmDialog.message }}
                </div>
                <div class="djc-dialog-footer">
                    <button class="djc-btn djc-btn-cancel" @click="cancelConfirm"><ui-icon name="x"></ui-icon>取消</button>
                    <button :class="['djc-btn', confirmDialog.confirmClass]" @click="executeConfirm"><ui-icon name="check"></ui-icon>确定</button>
                </div>
            </div>
        </div>
    </div>
    `,
    data() {
        return {
            items: [],          // 只保留 category === 'joints' 的条目
            selectedIdx: -1,
            jointSpeed: 0.2,
            minSpeed: 0.05,
            maxSpeed: 1.0,
            speedStep: 0.05,
            confirmDialog: {
                visible: false,
                title: '',
                message: '',
                icon: '',
                iconClass: '',
                confirmClass: '',
                action: null,
            },
        };
    },
    computed: {
        selectedItem() {
            return this.selectedIdx >= 0 ? this.items[this.selectedIdx] : null;
        }
    },
    methods: {
        readData() {
            mqttClient.publishDataReq('read');
            console.log('[关节数据] 已请求读取');
        },
        selectRow(idx) {
            this.selectedIdx = this.selectedIdx === idx ? -1 : idx;
        },
        normalizeSpeed() {
            const value = Number(this.jointSpeed);
            const safeValue = Number.isFinite(value) ? value : 0.2;
            this.jointSpeed = Number(
                Math.min(this.maxSpeed, Math.max(this.minSpeed, safeValue)).toFixed(2)
            );
        },
        adjustSpeed(delta) {
            this.jointSpeed = Number((Number(this.jointSpeed) + delta).toFixed(2));
            this.normalizeSpeed();
        },
        summarize(item) {
            const v = item.value;
            if (!v) return '-';
            if (item.type === 'single_joint') {
                const jointName = item.joint_name || Object.keys(v)[0];
                const value = jointName ? v[jointName] : undefined;
                return value === undefined ? jointName || '-' : `${jointName}: ${Number(value).toFixed(4)} rad`;
            }
            if (typeof v === 'object') {
                const keys = Object.keys(v);
                return `${keys.length} 项: ${keys.slice(0, 3).join(', ')}${keys.length > 3 ? '...' : ''}`;
            }
            return String(v);
        },
        formatType(item) {
            const labels = {
                whole_body: '全身',
                left_arm: '左手',
                right_arm: '右手',
                single_joint: '单轴',
            };
            if (!item) return '-';
            const label = labels[item.type] || item.type;
            return item.type === 'single_joint' && item.joint_name
                ? `${label}（${item.joint_name}）`
                : label;
        },
        onDataResp(data) {
            if (data && data.command === 'response' && Array.isArray(data.data)) {
                // 只保留关节数据
                this.items = data.data.filter(it => it.category === 'joints');
                this.selectedIdx = -1;
                console.log('[关节数据] 收到', this.items.length, '条数据');
            }
        },
        showConfirm(title, message, icon, iconClass, confirmClass, action) {
            this.confirmDialog = {
                visible: true,
                title,
                message,
                icon,
                iconClass,
                confirmClass,
                action,
            };
        },
        cancelConfirm() {
            this.confirmDialog.visible = false;
            this.confirmDialog.action = null;
        },
        executeConfirm() {
            if (this.confirmDialog.action) {
                this.confirmDialog.action();
            }
            this.cancelConfirm();
        },
        confirmGoTo() {
            const item = this.selectedItem;
            if (!item) return;
            this.normalizeSpeed();
            this.showConfirm(
                '确认到位',
                `确定要让机器人以 ${this.jointSpeed.toFixed(2)} rad/s 运动到关节「${this.formatType(item)}/${item.name}」吗？请确保周围环境安全。`,
                '▶',
                'djc-icon-go',
                'djc-btn-go',
                () => this.doGoTo()
            );
        },
        doGoTo() {
            const item = this.selectedItem;
            if (!item) return;
            this.normalizeSpeed();
            mqttClient.publishJointCommand(item.type, item.name, this.jointSpeed);
            console.log('[关节数据] 到位', item.type, item.name, `speed=${this.jointSpeed}`);
        },
        confirmUpdate() {
            const item = this.selectedItem;
            if (!item) return;
            this.showConfirm(
                '确认更新',
                `确定要用当前机器人姿态更新关节「${this.formatType(item)}/${item.name}」吗？原有数据将被覆盖。`,
                '↻',
                'djc-icon-update',
                'djc-btn-update',
                () => this.doUpdate()
            );
        },
        doUpdate() {
            const item = this.selectedItem;
            if (!item) return;
            const status = this.getRobotStatus();
            if (!status || !status.joints) {
                alert('未收到机器人状态数据');
                return;
            }
            const joints = status.joints;
            const typeJointKeys = {
                whole_body: [
                    'idx01_body_joint1','idx02_body_joint2','idx03_body_joint3','idx04_body_joint4','idx05_body_joint5',
                    'idx11_head_joint1','idx12_head_joint2','idx13_head_joint3',
                    'idx21_arm_l_joint1','idx22_arm_l_joint2','idx23_arm_l_joint3','idx24_arm_l_joint4','idx25_arm_l_joint5','idx26_arm_l_joint6','idx27_arm_l_joint7',
                    'idx61_arm_r_joint1','idx62_arm_r_joint2','idx63_arm_r_joint3','idx64_arm_r_joint4','idx65_arm_r_joint5','idx66_arm_r_joint6','idx67_arm_r_joint7',
                ],
                left_arm: ['idx21_arm_l_joint1','idx22_arm_l_joint2','idx23_arm_l_joint3','idx24_arm_l_joint4','idx25_arm_l_joint5','idx26_arm_l_joint6','idx27_arm_l_joint7'],
                right_arm: ['idx61_arm_r_joint1','idx62_arm_r_joint2','idx63_arm_r_joint3','idx64_arm_r_joint4','idx65_arm_r_joint5','idx66_arm_r_joint6','idx67_arm_r_joint7'],
                single_joint: [item.joint_name],
            };
            const keys = typeJointKeys[item.type];
            if (!keys || keys.some(key => !key || joints[key] === undefined)) {
                alert('当前机器人状态缺少该变量所需的关节数据');
                return;
            }
            const dataToSend = {};
            keys.forEach(key => { dataToSend[key] = joints[key]; });
            mqttClient.publishDataReq('update', {
                category: 'joints',
                type: item.type,
                name: item.name,
                joint_name: item.joint_name || null,
                data: dataToSend
            });
            item.value = dataToSend;
            console.log('[关节数据] 更新', item.type, item.name, Object.keys(dataToSend).length, '项');
        },
        confirmDelete() {
            const item = this.selectedItem;
            if (!item) return;
            this.showConfirm(
                '确认删除',
                `确定要删除关节「${this.formatType(item)}/${item.name}」吗？此操作不可恢复。`,
                '✕',
                'djc-icon-delete',
                'djc-btn-delete',
                () => this.doDelete()
            );
        },
        doDelete() {
            const item = this.selectedItem;
            if (!item) return;
            mqttClient.publishDataReq('delete', {
                category: 'joints',
                type: item.type,
                name: item.name
            });
            this.items.splice(this.selectedIdx, 1);
            this.selectedIdx = -1;
            console.log('[关节数据] 删除', item.type, item.name);
        }
    },
    mounted() {
        mqttClient.addDataRespCallback(this.onDataResp);
        // 自动读取一次
        this.readData();
    },
    beforeUnmount() {
        mqttClient.removeDataRespCallback(this.onDataResp);
    }
};

// vue_app.js
// 主 Vue 应用入口

import { createApp } from 'vue';
import { UrdfViewer } from './urdf-viewer.js';
import { mqttClient } from './mqtt-client.js';
import TeachJoints     from './teach-joints.js';
import TeachCoords     from './teach-coords.js';
import ProgramView     from './program-view.js';
import MapView         from './map-view.js';
import CameraView      from './camera-view.js';
import DataJoints       from './data-joints.js';
import DataCoords       from './data-coords.js';
import DataMapPoints    from './data-map-points.js';
import SynchroView      from './synchro.js';
import ChassisControl  from './chassis-control.js';

const UiIcon = {
    props: { name: { type: String, required: true } },
    template: `
        <svg class="btn-icon" aria-hidden="true">
            <use :href="'#ui-icon-' + name"></use>
        </svg>
    `
};


const App = {
    data() {
        return {
            currentMenu: '',          // 当前选中的菜单项 id
            openDropdown: '',         // 当前展开的下拉父菜单 id
            emergencyPressed: false,  // 全局软急停状态
            emergencyPending: false,
            isLoggedIn: false,        // 是否已登录管理模式
            loginDialog: {            // 登录弹窗
                visible: false,
                username: '',
                password: '',
                error: ''
            },
            menus: [
                {
                    id: 'teach', label: '示教', icon: 'teach', children: [
                        { id: 'teach_joints', label: '角度轴', icon: 'joint' },
                        { id: 'teach_coords', label: '末端坐标', icon: 'crosshair' },
                    ]
                },
                {
                    id: 'data', label: '数据', icon: 'data', children: [
                        { id: 'data_joints',     label: '关节', icon: 'joint' },
                        { id: 'data_coords',     label: '坐标', icon: 'crosshair' },
                        { id: 'data_map_points', label: '地图点位', icon: 'pin' },
                        { id: 'data_modbus',     label: '同步', icon: 'sync' },
                    ]
                },
                { id: 'program', label: '程序', icon: 'program' },
                {
                    id: 'map', label: '地图', icon: 'map' , children: [
                        { id: 'map_scan',    label: '扫图建图', icon: 'scan' },
                        { id: 'map_chassis', label: '底盘控制', icon: 'chassis' },
                    ]
                },
                {
                    id: 'camera', label: '相机', icon: 'camera', children: [
                        { id: 'cam_capture', label: '采集', icon: 'camera' },
                    ]
                },
            ],
            urdfViewer: null,
            robotStatus: null   // 共享的机器人状态
        };
    },
    components: { TeachJoints, TeachCoords, ProgramView, MapView, CameraView, DataJoints, DataCoords, DataMapPoints, SynchroView, ChassisControl },
    provide() {
        return {
            getUrdfViewer: () => this.urdfViewer,
            getRobotStatus: () => this.robotStatus,
            isLoggedIn: () => this.isLoggedIn
        };
    },
    computed: {
        // 根据登录状态过滤可见菜单（未登录时隐藏 地图、相机）
        visibleMenus() {
            if (this.isLoggedIn) return this.menus;
            return this.menus.filter(m => m.id !== 'map' && m.id !== 'camera');
        },
        // 导航栏右侧显示的层级面包屑
        navBreadcrumb() {
            if (this.currentMenu === 'program') {
                const pv = this.$refs.programView;
                const name = pv ? pv.currentFileName : 'main.py';
                return ['程序', name];
            }
            const paths = {
                'teach_joints': ['示教', '关节角度轴'],
                'teach_coords': ['示教', '末端坐标'],
                'data_joints': ['数据', '关节角度轴'],
                'data_coords': ['数据', '坐标点位'],
                'data_map_points': ['数据', '地图点位'],
                'data_modbus': ['数据', '同步'],
                'map_scan': ['地图', '扫图建图'],
                'map_chassis': ['地图', '底盘控制'],
                'cam_capture': ['相机', '采集'],
            };
            return paths[this.currentMenu] || [];
        }
    },
    template: `
    <div @click="closeDropdown">
        <canvas id="bg-canvas" ref="bgCanvas"></canvas>

        <!-- 本地单色 SVG 图标：风格接近 Font Awesome，不依赖外网字体。 -->
        <svg class="ui-icon-sprite" aria-hidden="true">
            <symbol id="ui-icon-stop" viewBox="0 0 24 24"><path d="M7 2h10l5 5v10l-5 5H7l-5-5V7z"/><rect x="8" y="8" width="8" height="8" rx="1"/></symbol>
            <symbol id="ui-icon-joint" viewBox="0 0 24 24"><path d="M4 6h7M15 6h5M4 12h3M11 12h9M4 18h10M18 18h2"/><circle cx="13" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="16" cy="18" r="2"/></symbol>
            <symbol id="ui-icon-crosshair" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"/><path d="M12 2v6M12 16v6M2 12h6M16 12h6"/></symbol>
            <symbol id="ui-icon-pin" viewBox="0 0 24 24"><path d="M12 22s7-6.3 7-13a7 7 0 1 0-14 0c0 6.7 7 13 7 13z"/><circle cx="12" cy="9" r="2.3"/></symbol>
            <symbol id="ui-icon-sync" viewBox="0 0 24 24"><path d="M20 7h-5V2M4 17h5v5M19 12a7 7 0 0 0-12-5L4 10M5 12a7 7 0 0 0 12 5l3-3"/></symbol>
            <symbol id="ui-icon-scan" viewBox="0 0 24 24"><path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M7 14c3-3 7-3 10 0M9 11c2-2 4-2 6 0"/></symbol>
            <symbol id="ui-icon-chassis" viewBox="0 0 24 24"><rect x="4" y="7" width="16" height="9" rx="2"/><circle cx="8" cy="18" r="2"/><circle cx="16" cy="18" r="2"/><path d="M8 7l2-3h4l2 3"/></symbol>
            <symbol id="ui-icon-camera" viewBox="0 0 24 24"><path d="M4 7h4l2-2h4l2 2h4v12H4z"/><circle cx="12" cy="13" r="4"/></symbol>
            <symbol id="ui-icon-teach" viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="11" rx="4"/><path d="M8 10v5M5.5 12.5h5M16 11h.01M18.5 14h.01"/></symbol>
            <symbol id="ui-icon-data" viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></symbol>
            <symbol id="ui-icon-program" viewBox="0 0 24 24"><path d="M6 2h9l4 4v16H6zM14 2v5h5M10 12l-2 2 2 2M15 12l2 2-2 2"/></symbol>
            <symbol id="ui-icon-map" viewBox="0 0 24 24"><path d="M3 5l6-3 6 3 6-3v17l-6 3-6-3-6 3zM9 2v17M15 5v17"/></symbol>
            <symbol id="ui-icon-lock" viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></symbol>
            <symbol id="ui-icon-unlock" viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 7-2"/></symbol>
            <symbol id="ui-icon-save" viewBox="0 0 24 24"><path d="M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-7h8v7"/></symbol>
            <symbol id="ui-icon-refresh" viewBox="0 0 24 24"><path d="M20 6v5h-5M4 18v-5h5M18 9a7 7 0 0 0-12-2l-2 4M6 15a7 7 0 0 0 12 2l2-4"/></symbol>
            <symbol id="ui-icon-edit" viewBox="0 0 24 24"><path d="M4 20l4-1 11-11-3-3L5 16zM14 7l3 3"/></symbol>
            <symbol id="ui-icon-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 3h6l1 4H8zM7 7l1 14h8l1-14M10 11v6M14 11v6"/></symbol>
            <symbol id="ui-icon-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
            <symbol id="ui-icon-check" viewBox="0 0 24 24"><path d="M5 12l4 4L19 6"/></symbol>
            <symbol id="ui-icon-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
            <symbol id="ui-icon-minus" viewBox="0 0 24 24"><path d="M5 12h14"/></symbol>
            <symbol id="ui-icon-up" viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></symbol>
            <symbol id="ui-icon-down" viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6"/></symbol>
            <symbol id="ui-icon-left" viewBox="0 0 24 24"><path d="M19 12H5M11 6l-6 6 6 6"/></symbol>
            <symbol id="ui-icon-right" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></symbol>
            <symbol id="ui-icon-rotate-left" viewBox="0 0 24 24"><path d="M4 8V3M4 3h5M4 3l4 4M5 12a7 7 0 1 0 2-5"/></symbol>
            <symbol id="ui-icon-rotate-right" viewBox="0 0 24 24"><path d="M20 8V3M20 3h-5M20 3l-4 4M19 12a7 7 0 1 1-2-5"/></symbol>
            <symbol id="ui-icon-folder" viewBox="0 0 24 24"><path d="M3 6h7l2 2h9v12H3z"/></symbol>
            <symbol id="ui-icon-folder-open" viewBox="0 0 24 24"><path d="M3 6h7l2 2h9v3H7L3 20z"/></symbol>
            <symbol id="ui-icon-play" viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></symbol>
            <symbol id="ui-icon-next" viewBox="0 0 24 24"><path d="M5 4l10 8-10 8zM18 5v14"/></symbol>
            <symbol id="ui-icon-bug" viewBox="0 0 24 24"><rect x="7" y="6" width="10" height="13" rx="5"/><path d="M9 6V3M15 6V3M4 10h3M17 10h3M4 15h3M17 15h3M12 9v7"/></symbol>
            <symbol id="ui-icon-upload" viewBox="0 0 24 24"><path d="M12 16V3M7 8l5-5 5 5M4 15v6h16v-6"/></symbol>
            <symbol id="ui-icon-download" viewBox="0 0 24 24"><path d="M12 3v13M7 11l5 5 5-5M4 15v6h16v-6"/></symbol>
            <symbol id="ui-icon-power" viewBox="0 0 24 24"><path d="M12 2v10M7 5a8 8 0 1 0 10 0"/></symbol>
            <symbol id="ui-icon-repeat" viewBox="0 0 24 24"><path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/></symbol>
            <symbol id="ui-icon-home" viewBox="0 0 24 24"><path d="M3 11l9-8 9 8M5 10v11h14V10M9 21v-7h6v7"/></symbol>
        </svg>

        <nav id="toolbar" @click.stop>
            <button class="emergency-btn"
                    :class="{ pressed: emergencyPressed }"
                    :aria-pressed="emergencyPressed"
                    :disabled="emergencyPending"
                    @click="toggleEmergency">
                <svg class="emergency-icon" aria-hidden="true"><use href="#ui-icon-stop"></use></svg>
                {{ emergencyPressed ? '急停按下' : '急停' }}
            </button>

            <template v-for="m in visibleMenus" :key="m.id">
                <!-- 无子菜单：直接按钮 -->
                <button v-if="!m.children"
                        class="menu-btn"
                        :class="{ active: currentMenu === m.id }"
                        @click="selectMenu(m.id)">
                    <ui-icon :name="m.icon"></ui-icon>{{ m.label }}
                </button>

                <!-- 有子菜单：下拉 -->
                <div v-else class="menu-dropdown">
                    <button class="menu-btn"
                            :class="{ active: openDropdown === m.id || isChildActive(m) }"
                            @click="toggleDropdown(m.id)">
                        <ui-icon :name="m.icon"></ui-icon>{{ m.label }}
                        <span class="dropdown-arrow">▾</span>
                    </button>
                    <div v-show="openDropdown === m.id" class="dropdown-panel">
                        <button v-for="c in m.children" :key="c.id"
                                class="dropdown-item"
                                :class="{ active: currentMenu === c.id }"
                                @click="selectMenu(c.id)">
                            <ui-icon :name="c.icon"></ui-icon>
                            {{ c.label }}
                        </button>
                    </div>
                </div>
            </template>

            <button class="menu-btn login-btn"
                    :class="{ 'login-btn-out': isLoggedIn }"
                    @click="toggleLogin">
                <ui-icon :name="isLoggedIn ? 'lock' : 'unlock'"></ui-icon>{{ isLoggedIn ? '退出' : '登录' }}
            </button>

            <div class="toolbar-right">
                <span class="brand-logo"><img src="minth-logo.png" alt="Minth Group" /></span>
                <div class="nav-breadcrumb">
                    <span class="brand" @click="toggleHome">轮式人形机器人</span>
                    <template v-for="item in navBreadcrumb" :key="item">
                        <span class="breadcrumb-separator">/</span>
                        <span class="nav-page-title">{{ item }}</span>
                    </template>
                </div>
            </div>
        </nav>

        <!-- 登录弹窗 -->
        <div v-if="loginDialog.visible" class="save-overlay login-overlay" @click.self="closeLoginDialog">
            <div class="save-dialog login-dialog">
                <h6 class="login-title">🔐 管理模式登录</h6>
                <div class="login-form">
                    <div class="login-form-row">
                        <label>帐号</label>
                        <input type="text" v-model="loginDialog.username" class="login-input"
                               placeholder="请输入帐号" @keyup.enter="doLogin" ref="loginUserInput" />
                    </div>
                    <div class="login-form-row">
                        <label>密码</label>
                        <input type="password" v-model="loginDialog.password" class="login-input"
                               placeholder="请输入密码" @keyup.enter="doLogin" />
                    </div>
                    <div v-if="loginDialog.error" class="login-error">{{ loginDialog.error }}</div>
                    <div class="login-form-actions">
                        <button class="cv-btn cv-btn-save" @click="doLogin"><ui-icon name="unlock"></ui-icon>登录</button>
                        <button class="cv-btn" @click="closeLoginDialog"><ui-icon name="x"></ui-icon>取消</button>
                    </div>
                </div>
            </div>
        </div>

        <main id="content" :class="{ 'content-hidden': !currentMenu, 'content-fullscreen': currentMenu === 'map_chassis' || currentMenu === 'cam_capture' || currentMenu === 'data_joints' || currentMenu === 'data_coords' || currentMenu === 'data_map_points' || currentMenu === 'data_modbus' || currentMenu === 'program' || currentMenu === 'teach_joints' || currentMenu === 'teach_coords' }">
            <teach-joints     v-if="currentMenu === 'teach_joints'"></teach-joints>
            <teach-coords     v-if="currentMenu === 'teach_coords'"></teach-coords>
            <program-view     ref="programView" v-if="currentMenu === 'program'"></program-view>
            <map-view         v-if="currentMenu === 'map_scan'"></map-view>

            <!-- 地图 > 底盘控制 -->
            <chassis-control  v-if="currentMenu === 'map_chassis'"></chassis-control>

            <!-- 相机 > 采集 -->
            <camera-view      v-if="currentMenu === 'cam_capture'"></camera-view>

            <!-- 数据 > 关节 -->
            <data-joints      v-if="currentMenu === 'data_joints'"></data-joints>

            <!-- 数据 > 坐标 -->
            <data-coords      v-if="currentMenu === 'data_coords'"></data-coords>

            <!-- 数据 > 地图点位（只操作 robot_data.db） -->
            <data-map-points  v-if="currentMenu === 'data_map_points'"></data-map-points>

            <!-- 数据 > 同步 -->
            <synchro-view      v-if="currentMenu === 'data_modbus'"></synchro-view>
        </main>
    </div>
    `,
    methods: {
        toggleEmergency() {
            if (this.emergencyPending) return;
            this.emergencyPending = true;
            mqttClient.publishEmergency(this.emergencyPressed ? 'release' : 'press');
            // 状态以服务端回传为准；超时后恢复可操作，允许重试。
            setTimeout(() => {
                this.emergencyPending = false;
            }, 3000);
        },
        onEmergencyStatus(data) {
            if (!data || typeof data.pressed !== 'boolean') return;
            this.emergencyPressed = data.pressed;
            this.emergencyPending = false;
            if (data.error) {
                console.error('[急停] 部分停止信号下发失败:', data.error);
            } else {
                console.log(`[急停] 状态：${data.pressed ? '按下' : '松开'}`);
            }
        },
        selectMenu(id) {
            this.currentMenu = id;
            this.openDropdown = '';
        },
        toggleLogin() {
            if (this.isLoggedIn) {
                // 退出登录
                this.isLoggedIn = false;
                // 如果当前处于隐藏菜单页面，回到首页
                if (this.currentMenu === 'map_scan' || this.currentMenu === 'map_chassis'
                    || this.currentMenu === 'cam_capture') {
                    this.currentMenu = '';
                }
                console.log('[登录] 已退出管理模式');
            } else {
                // 打开登录弹窗
                this.loginDialog.visible = true;
                this.loginDialog.username = '';
                this.loginDialog.password = '';
                this.loginDialog.error = '';
                this.$nextTick(() => {
                    if (this.$refs.loginUserInput) this.$refs.loginUserInput.focus();
                });
            }
        },
        closeLoginDialog() {
            this.loginDialog.visible = false;
        },
        doLogin() {
            const u = (this.loginDialog.username || '').trim();
            const p = (this.loginDialog.password || '').trim();
            if (!u || !p) {
                this.loginDialog.error = '请输入帐号和密码';
                return;
            }
            if (u === 'admin' && p === 'admin') {
                this.isLoggedIn = true;
                this.loginDialog.visible = false;
                console.log('[登录] 登录成功，进入管理模式');
            } else {
                this.loginDialog.error = '帐号或密码错误';
            }
        },
        toggleHome() {
            // 点击「人形底盘机器人」logo，收起所有功能页，显示 3D 模型
            this.currentMenu = '';
            this.openDropdown = '';
        },
        toggleDropdown(id) {
            this.openDropdown = this.openDropdown === id ? '' : id;
        },
        closeDropdown() {
            this.openDropdown = '';
        },
        isChildActive(menu) {
            if (!menu.children) return false;
            return menu.children.some(c => c.id === this.currentMenu);
        },
        toggleMenu(id) {
            this.currentMenu = this.currentMenu === id ? '' : id;
        },
        onStatus(data) {
            // serivces2 由关节、末端位姿、底盘和夹爪控制器分别发布状态片段。
            // 合并片段，避免后到的模块覆盖其他模块已经收到的状态。
            this.robotStatus = {
                ...(this.robotStatus || {}),
                ...(data || {}),
            };
            // 同步关节到 3D 模型
            if (data && data.joints && this.urdfViewer) {
                this.urdfViewer.setJointsFromStatus(data.joints);
            }
        }
    },
    mounted() {
        // 初始化背景 3D 模型
        this.urdfViewer = new UrdfViewer(this.$refs.bgCanvas);
        this.urdfViewer.loadUrdf('meshes/model.urdf');

        // 连接 MQTT，订阅机器人状态
        mqttClient.onStatus((data) => this.onStatus(data));
        mqttClient.addEmergencyStatusCallback((data) => this.onEmergencyStatus(data));
        mqttClient.connect();
    }
};

createApp(App).component('UiIcon', UiIcon).mount('#app');

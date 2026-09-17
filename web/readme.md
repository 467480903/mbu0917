# 机器人 Web 控制台

`web/` 是 agiBot-G2 人形底盘机器人的浏览器控制界面。它是一个**无构建步骤的静态 ES Module 应用**：浏览器直接加载本目录的 `index.html`、本地 Vue/Three.js 库与业务模块；控制和实时数据全部经 MQTT-over-WebSocket 与 `services/main.py` 通信，不依赖 REST API、前端路由或后端模板渲染。

## 总体架构

```text
浏览器（web/，HTTP :8002）
  ├─ Vue Options API：菜单、业务面板与共享状态
  ├─ Paho MQTT（WebSocket :9001）：命令发布、数据订阅与回调分发
  └─ Three.js + URDF：常驻机器人三维模型
             │ MQTT JSON
             ▼
MQTT Broker
             │
             ▼
services/main.py（GDK 硬件控制服务）
  ├─ 机器人 / 相机 / 雷达 / SLAM
  ├─ 示教数据与地图点位数据库
  └─ Modbus TCP / Siemens S7 设备
```

`services/run.sh` 会在启动机器人服务的同时，以 `web/` 为工作目录运行 `python3 -m http.server 8002`。页面加载后连接 `location.hostname:9001` 的 MQTT WebSocket；地址为空时会回退为 `10.2.236.6:9001`。因此部署时 MQTT Broker 必须同时提供 WebSocket 监听端口 `9001`。

## 入口与依赖

- `index.html`：唯一页面入口，挂载 `#app`，加载 Paho MQTT，并通过 import map 将 Vue、Three.js、URDF Loader 映射到 `libs/` 本地文件。
- `js/index.js`：Vue 根组件；创建菜单、管理当前面板与前端登录状态，初始化 MQTT 和 3D 查看器，并把机器人状态提供给子组件。
- `css/vue_app.css`：全屏控制台布局、工具栏、弹窗、示教/数据表格、地图、相机和 YOLO 面板样式。
- `libs/`：本地分发的 Vue ESM、Three.js、URDF Loader、OrbitControls、STL Loader 等，不需要 CDN。
- `paho-mqtt.min.js`：浏览器端 MQTT 客户端。
- `bootstrap.min.css`：入口页面引用的基础样式；目录中的 jQuery、Alpine 与 Bootstrap JS 当前未由 `index.html` 引用。

## 页面组成

根组件使用条件渲染（`v-if`）在一个内容区域中装载功能面板。未选择业务页时，内容区不接收鼠标事件，用户可直接操作背景中的 3D 机器人。

| 菜单 | 模块 | 功能 |
| --- | --- | --- |
| 示教 / 角度轴 | `teach-joints.js` | 显示并微调头部、腰部、躯干与双臂关节；发送 WBC/关节控制指令；保存示教关节数据。 |
| 示教 / 末端坐标 | `teach-coords.js` | 显示左右末端状态；进行相对偏移、夹爪控制与末端位姿保存。 |
| 数据 / 关节 | `data-joints.js` | 查询、执行、更新和删除已保存的关节示教数据。 |
| 数据 / 坐标 | `data-coords.js` | 管理已保存的左右臂/双臂末端位姿，支持到位和用当前姿态更新。 |
| 数据 / 地图点位 | `data-map-points.js` | 管理 `robot_data.db` 中的本地点位；该功能与机器人内部地图点位分开。 |
| 数据 / 同步 | `synchro.js` | 展示 Modbus/S7 读写变量，将可写项写入工业设备同步区。 |
| 程序 | `program-view.js` | 列出、读取、上传、删除、复制、运行、单步调试 `runtime/programs/` 中的 Python 程序。 |
| 地图 / 扫图建图 | `map-view.js` | 显示激光点云并控制开始、停止、保存 SLAM 建图。 |
| 地图 / 底盘控制 | `chassis-control.js` | 在栅格地图上显示机器人和点位；执行相对移动、点位导航、地图切换及点位保存。 |
| 相机 / 采集 | `camera-view.js` | 显示头部 RGB/深度与左右腕部图像；控制流、拍照及连续采集。 |
| 相机 / YOLO 计算 | `yolo-inference.js` | 显示 `yolo/rgb.jpg` 与 `yolo/server_result_rgb.jpg`，并触发拍照/推理流程。 |

## MQTT 通信层

`js/mqtt-client.js` 是所有业务模块的共享通信封装。它在连接成功后订阅服务端数据主题，将 JSON 消息分发给按领域注册的回调；掉线或连接失败后每 5 秒重试。命令统一以 QoS 0 发布；未连接时命令会被丢弃并在控制台提示。

| 领域 | 控制主题 | 前端订阅主题 |
| --- | --- | --- |
| 相机 | `/humanoid/camera/control` | `/humanoid/camera/data` |
| 关节与示教数据 | `/humanoid/joints/control`、`/humanoid/joints/save` | `/humanoid/joints/data` |
| 机器人状态/点云 | `/humanoid/status/control` | `/humanoid/status/data`、`/humanoid/status/cloud` |
| 高层动作 | `/humanoid/commands/data` | `/humanoid/commands/done` |
| 地图与本地点位 | `/humanoid/map/control`、`/humanoid/map/db_control` | `/humanoid/map/points`、`/humanoid/map/info`、`/humanoid/map/grid`、`/humanoid/map/db_data` |
| 末端位姿 | `/humanoid/positions/control` | `/humanoid/positions/data` |
| 程序调试 | `/humanoid/programs/control` | `/humanoid/programs/step`、`codes`、`files`、`file_content`、上传/删除结果主题 |
| Modbus / S7 | `/humanoid/modbus/control` | `/humanoid/modbus/data` |

根组件持续接收 `/humanoid/status/data`，保存为共享 `robotStatus`，并将其中的 `joints` 角度实时同步给三维模型。面板在挂载时注册自己需要的回调、发送初始读取命令；需要高频数据的页面会在离开时取消回调或关闭对应数据流。

## 三维机器人视图

`js/urdf-viewer.js` 通过 Three.js、OrbitControls 和 `urdf-loader` 渲染始终可见的背景模型：

- 加载 `meshes/model.urdf`，STL 网格来自 `meshes/G2/T2/` 和 `meshes/arm/`。
- 将 URDF 的 Z-up 坐标转换为 Three.js 的 Y-up 坐标，并根据模型包围盒自动调整相机。
- 使用 `robot.joints[关节名].setJointValue(弧度)` 应用实时状态，未找到的关节安全忽略。
- 提供环境光、方向光、网格地面和轨道旋转缩放控制；模型生命周期与整个页面一致。

## 资源目录

| 路径 | 内容 |
| --- | --- |
| `js/` | Vue 根组件、MQTT 封装和所有业务页面模块。 |
| `css/vue_app.css` | 控制台主题与所有页面布局。 |
| `libs/` | Vue、Three.js、URDF Loader 及 Three.js 附加加载器。 |
| `meshes/model.urdf` | 机器人运动学与视觉模型定义。 |
| `meshes/G2/T2/`、`meshes/arm/` | 底盘、躯干、头部和机械臂 STL/FBX 网格。 |
| `yolo/` | YOLO 输入图和服务端结果图的静态展示文件。 |
| `minth-logo.png` | 顶部品牌图标。 |

## 注意事项

- 页面中的“登录”是前端 UI 显隐：账号密码写死为 `admin` / `admin`，不会发送认证信息，不能替代 MQTT Broker 或后端的权限控制。
- 所有实际硬件操作最终由 MQTT 消费端执行；浏览器侧确认弹窗、超时和按钮禁用仅是交互保护，不是安全联锁。
- `yolo-inference.js` 会发布 `yolo_infer`，而当前 `services/camera.py` 公开的检测命令为 `detect`。若没有其他 MQTT 消费者处理 `yolo_infer`，应在联调时统一此命令协议。
- 开发时使用静态 HTTP 服务访问页面，不要直接以 `file://` 打开，否则 ES Module 和资源路径可能受浏览器安全策略限制。

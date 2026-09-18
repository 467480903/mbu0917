# agiBot-G2 人形机器人控制系统

面向 **agiBot-G2** 人形机器人的本地控制工程。系统将浏览器控制台、MQTT 消息总线和 Python 硬件控制服务连接起来，支持机器人运动、相机、SLAM/地图、点云、示教数据、运行时程序，以及 Modbus TCP / Siemens S7 工业设备交互。

> 该项目直接控制真实机器人与外部工业设备。请仅在具备场地安全措施、急停可用并确认设备连接正确后执行运动、导航或写入操作。

## 架构

```text
浏览器（web/，HTTP :8002）
  │  MQTT JSON（WebSocket :9001）
  ▼
MQTT Broker
  │  MQTT（localhost:1883）
  ▼
services/main.py
  ├─ agibot_gdk：机器人、相机、SLAM、雷达、末端执行器与底盘
  ├─ SQLite：示教数据、坐标点与本地点位
  ├─ Modbus TCP / Siemens S7：工业数据同步
  └─ runtime/：可在控制台查看、上传和调试的 Python 程序
```

- 后端是单一 Python 服务入口 `services/main.py`；它初始化 GDK、连接 MQTT、订阅控制主题，并启动相机、状态、Modbus 和 S7 后台发布/轮询任务。
- 前端是无构建步骤的静态 ES Module 应用，使用本地 Vue、Three.js、URDF Loader 和 Paho MQTT 库，不依赖 REST API。
- MQTT Broker 需要同时提供 TCP `1883` 与 WebSocket `9001` 监听端口。

## 功能

- **机器人控制**：关节、WBC、双臂/头部控制，末端位姿移动、夹爪和底盘导航。
- **示教与数据管理**：保存、查询、更新和删除关节、末端坐标与地图点位；数据存于 `datas/robot_data.db`。
- **感知与地图**：相机图像流、拍照、检测、机器人状态、激光点云、SLAM 建图和栅格地图。
- **运行时程序**：在 Web 控制台列出、读取、上传、删除、复制、运行和单步调试 `runtime/programs/` 的 Python 文件。
- **工业设备集成**：按 `datas/modbus.json` 周期读取/写入 Modbus TCP 寄存器，并支持 S7 数据交互。

## 目录结构

```text
.
├── datas/                 # Modbus/S7 配置、SQLite 数据库和数据转换说明
│   ├── modbus.json        # Modbus TCP 设备、寄存器、变量名与轮询周期
│   ├── robot_data.db      # 本地示教、坐标和地图点位数据库
│   └── s7.json_           # S7 配置样例（实际运行读取 s7.json）
├── runtime/               # 运行时 Python 程序及其入口/辅助接口
│   └── programs/          # 可通过 Web 控制台管理和调试的程序
├── services/              # Python 机器人控制服务
│   ├── main.py            # 唯一服务入口与 MQTT 消息路由
│   ├── common.py          # GDK/MQTT 初始化、主题和路径常量
│   ├── camera.py          # 相机数据流与控制
│   ├── joints.py          # 关节运动与示教数据
│   ├── positions.py       # 末端坐标点位控制
│   ├── status.py          # 状态与点云发布
│   ├── commands.py        # TTS、抓取、导航等高层命令
│   ├── map.py             # 地图与本地点位管理
│   ├── programs.py        # runtime 程序管理与调试
│   ├── modbus.py / s7.py  # 工业协议读写与轮询
│   └── run.sh             # 服务与 Web 静态站点启动脚本
├── test/                  # 服务相关测试
└── web/                   # 静态 Web 控制台
    ├── index.html         # 页面入口
    ├── js/                # Vue 组件、MQTT 客户端和 3D 查看器
    ├── meshes/            # URDF 与机器人网格资源
    └── readme.md          # Web 控制台的详细说明
```

## 前置条件

运行机器人服务前，请准备以下环境：

1. **Linux 与 Python 3**。
2. **agiBot GDK**：需要已安装 `agibot_gdk`，并可加载 GDK 环境脚本。默认启动脚本使用 `/home/agi/app/env.sh`。
3. **Python MQTT 客户端**：服务依赖 `paho-mqtt`（使用 Paho MQTT v2 回调 API）。GDK 及其他底层依赖的具体版本由机器人运行环境提供；本仓库未锁定 Python 依赖版本。
4. **MQTT Broker**：
   - TCP：`localhost:1883`，供 Python 服务连接；
   - WebSocket：`<Web 页面主机>:9001`，供浏览器连接。
5. **硬件与网络**：机器人 GDK/DDS 通信正常；如启用 Modbus/S7，请确保工业设备地址、端口和寄存器配置正确。

## 配置

### MQTT

服务端配置位于 `services/common.py`：

```python
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "humanoid_server"
```

Web 控制台会连接 `location.hostname:9001`。因此远程访问控制台时，Broker 必须允许该主机通过 WebSocket `9001` 接入，且需要按实际网络环境配置访问控制与认证。

### Modbus 与 S7

- Modbus TCP 配置：`datas/modbus.json`。该文件定义设备 IP、端口、读写 holding register、变量名和轮询周期（`rate`）。修改前请确认设备映射，特别是 `write` 区域。
- S7：服务运行时读取 `datas/s7.json`；仓库当前提供 `datas/s7.json_` 作为样例。首次启用时，请根据现场 PLC 参数复制并调整：

```bash
cp datas/s7.json_ datas/s7.json
```

请勿将生产环境 PLC 地址、凭据或敏感工艺数据提交到版本库。

## 启动与停止

`services/run.sh` 会加载 GDK 环境、启动机器人服务，并在 `web/` 目录启动静态服务器。

```bash
cd services
chmod +x run.sh
./run.sh             # 启动机器人服务和 Web 控制台
./run.sh status      # 查看服务状态
./run.sh stop        # 停止服务
./run.sh restart     # 重启服务
```

启动成功后：

- Web 控制台：`http://<机器人主机地址>:8002/`
- 服务日志：`services/logs/humanoid_server.log`
- Web 日志：`services/logs/web_server.log`

> `run.sh` 会尝试加载 `/home/agi/app/env.sh`。若 GDK 安装在其他位置，请先调整脚本中的 `ENV_FILE` 与传入目录，或在启动前加载等效的 GDK 环境。

## MQTT 接口概览

所有消息均为 JSON。控制台与服务端使用以下核心主题：

| 领域 | 控制主题 | 服务端发布主题 |
| --- | --- | --- |
| 相机 | `/humanoid/camera/control` | `/humanoid/camera/data` |
| 关节与示教 | `/humanoid/joints/control`、`/humanoid/joints/save` | `/humanoid/joints/data` |
| 状态与点云 | `/humanoid/status/control` | `/humanoid/status/data`、`/humanoid/status/cloud` |
| 高层动作 | `/humanoid/commands/data` | `/humanoid/commands/done` |
| 地图与点位 | `/humanoid/map/control`、`/humanoid/map/db_control` | `/humanoid/map/points`、`/humanoid/map/info`、`/humanoid/map/grid`、`/humanoid/map/db_data` |
| 末端坐标 | `/humanoid/positions/control` | `/humanoid/positions/data` |
| 程序调试 | `/humanoid/programs/control` | `/humanoid/programs/step`、`/humanoid/programs/codes`、`/humanoid/programs/files` |
| Modbus / S7 | `/humanoid/modbus/control` | `/humanoid/modbus/data` |
| 同步变量 | `/humanoid/data/read`、`/humanoid/data/write` | `/humanoid/data/response` |

完整的消息分发与命令处理逻辑见 `services/main.py`，Web 控制台的具体交互及 MQTT 回调说明见 [`web/readme.md`](web/readme.md)。

## Web 控制台

控制台包含以下主要页面：

- **示教**：角度轴、末端坐标；
- **数据**：关节、坐标、地图点位、工业同步变量；
- **程序**：运行时 Python 文件的编辑、运行和调试；
- **地图**：扫图建图、点云与底盘控制；
- **相机**：RGB/深度/腕部相机采集与 YOLO 流程；
- **3D 视图**：通过 `web/meshes/model.urdf` 展示机器人模型，并实时同步关节状态。

控制台的登录仅是前端界面控制，不构成身份认证或操作授权。生产部署时，应在 MQTT Broker、网络边界和机器人安全系统中配置真实的认证、授权与安全联锁。

## 开发说明

- 前端直接由 Python 静态服务器提供，开发时请通过 `http://` 访问，不要使用 `file://` 打开 `web/index.html`，以避免浏览器阻止 ES Module 和资源加载。
- `services/main.py` 为唯一服务入口；不要并行启动旧的拆分服务，以免重复连接硬件或竞争 MQTT 客户端 ID。
- 长耗时的关节和高层动作通过单线程执行器排队执行，避免阻塞 MQTT 消息循环。
- 项目未提供 `requirements.txt`、`pyproject.toml`、容器定义或前端构建配置；依赖版本与 GDK 安装由目标机器人环境管理。

## 故障排查

| 现象 | 排查建议 |
| --- | --- |
| 服务无法连接 MQTT | 确认 Broker 已启动且 `localhost:1883` 可访问；检查端口、ACL 和客户端 ID 冲突。 |
| 页面无法连接 MQTT | 确认 Broker 已启用 WebSocket `9001`，并检查浏览器开发者工具中的网络错误和跨主机访问策略。 |
| 服务启动时 GDK 初始化失败 | 检查 `/home/agi/app/env.sh`、GDK 安装与机器人/DDS 连接状态。 |
| Modbus/S7 无数据或写入失败 | 核对 `datas/modbus.json` / `datas/s7.json` 的设备地址、端口、寄存器/DB 映射与现场网络连通性。 |
| 页面资源或模块加载失败 | 使用 `./run.sh` 启动的 HTTP 站点访问 `:8002`，不要直接打开本地 HTML 文件。 |

## 相关文档

- [`services/readme.md`](services/readme.md)：服务侧补充说明。
- [`web/readme.md`](web/readme.md)：Web 控制台架构、页面模块、资源与 MQTT 通信细节。
- [`services/SKILL.md`](services/SKILL.md)：服务开发约定。
- [`datas/convert_map_points_skill.md`](datas/convert_map_points_skill.md)：地图点位数据转换说明。

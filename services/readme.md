# Humanoid 机器人控制服务

`services/` 是 agiBot-G2 人形机器人的控制服务目录。它以 `main.py` 为唯一进程入口：初始化 GDK 硬件对象与 MQTT 客户端，将 Web/运行时客户端发来的 MQTT JSON 指令分发给各功能组件，并持续发布机器人遥测数据。

## 架构与依赖

- **硬件 SDK**：`agibot_gdk`，用于机器人本体、相机、SLAM、地图、雷达等设备访问。
- **消息总线**：本机 MQTT Broker（`localhost:1883`），客户端 ID 为 `humanoid_server`。
- **数据存储**：`datas/robot_data.db`；关节姿态、末端位姿与本地点位由 `data.py` 管理。
- **工业协议**：`datas/modbus.json` 提供 Modbus TCP 设备配置；`s7.py` 读取 `datas/s7.json` 并轮询 S7 设备（仓库当前的 `datas/s7.json_` 可作为配置样例，启用前需提供实际的 `s7.json`）。
- **运行时程序**：`runtime/programs/` 中的 Python 程序可通过程序调试组件管理和执行。

服务启动时会先初始化 GDK 和内存 SQLite 数据库、连接 MQTT，再启动相机、状态、Modbus 与 S7 的后台发布/轮询线程。耗时的运动和导航命令会进入单线程执行器，以避免阻塞 MQTT 消息循环。

## 入口与启动

- `main.py`：服务唯一入口，订阅 MQTT 控制主题并路由消息。
- `run.sh`：启动/停止脚本；会加载 `/home/agi/app/env.sh`（如果存在），启动 `main.py`，并在项目的 `web/` 目录启动端口 `8002` 的静态 HTTP 服务。

在本目录执行：

```bash
chmod +x run.sh
./run.sh          # 启动服务与 Web 静态服务器
./run.sh status   # 查看状态
./run.sh stop     # 停止服务
./run.sh restart  # 重启
```

日志位于 `services/logs/humanoid_server.log` 和 `services/logs/web_server.log`。运行前应确认 GDK 环境、MQTT Broker、机器人 DDS 通信及相关设备网络均已就绪。

## MQTT 主题

所有消息使用 JSON。`main.py` 订阅下列控制主题，并通过相应数据主题返回结果或持续发布状态。

| 功能 | 控制主题（客户端 → 服务） | 数据/结果主题（服务 → 客户端） | 说明 |
| --- | --- | --- | --- |
| 相机 | `/humanoid/camera/control` | `/humanoid/camera/data` | 视频流开关、拍照、检测。 |
| 关节 | `/humanoid/joints/control`、`/humanoid/joints/save` | `/humanoid/joints/data` | 头部、腰部、双臂/单臂与单关节运动；保存、读取、更新、删除示教数据。 |
| 状态与点云 | `/humanoid/status/control` | `/humanoid/status/data`、`/humanoid/status/cloud` | 持续发布关节、末端和底盘状态；按需发布前后雷达点云。 |
| 动作命令 | `/humanoid/commands/data` | `/humanoid/commands/done` | 语音、抓取、导航、相对移动、相机头部控制等。 |
| 地图 | `/humanoid/map/control`、`/humanoid/map/db_control` | `/humanoid/map/points`、`/humanoid/map/info`、`/humanoid/map/grid`、`/humanoid/map/db_data` | SLAM 建图、地图切换、栅格发布及本地点位管理/导航。 |
| 末端位姿 | `/humanoid/positions/control` | `/humanoid/positions/data` | 末端到位、以当前机器人姿态更新已保存的位姿。 |
| 程序调试 | `/humanoid/programs/control` | `/humanoid/programs/step`、`/humanoid/programs/codes`、`/humanoid/programs/files` 等 | 运行、单步、停止、上传、读取、删除 `runtime/programs/` 下程序。 |
| Modbus / S7 | `/humanoid/modbus/control` | `/humanoid/modbus/data` | 配置读取/写入及设备数据发布。 |
| 同步变量 | `/humanoid/data/read`、`/humanoid/data/write` | `/humanoid/data/response` | 按名称读取或写入 `synch` 中的工业设备变量。 |

## 主要模块

| 文件 | 职责 |
| --- | --- |
| `common.py` | 公共路径与 MQTT 主题常量；初始化/释放 GDK；持有 Robot、Camera、Slam、Lidar、地图、导航和末端执行器等共享对象；封装 MQTT 发布。 |
| `main.py` | 唯一入口与 MQTT 分发器；负责组件、数据库和后台线程的生命周期。 |
| `camera.py` | 采集并编码相机帧，控制视频流与拍照；支持将检测请求转发至 TCP 检测服务并保存结果。 |
| `joints.py` | 控制头、腰、左右臂及单关节运动；管理关节示教数据。 |
| `status.py` | 以固定周期发布关节角、左右末端位姿和底盘地图坐标；可启停雷达点云发布。 |
| `commands.py` | 处理 TTS、夹爪抓取、底盘导航/相对移动、相机头部等高层动作命令。 |
| `chassis_controller.py` | `RobotController`：地图导航点加载、绝对/相对导航、路径序列、蟹行、前进与旋转。 |
| `EndEffectorController.py` | 双臂末端轨迹规划、姿态插值、绝对到位和相对偏移运动。 |
| `positions.py` | 保存/更新左右臂或双臂末端位姿，并执行已保存位姿的到位动作。 |
| `map.py` | 管理 GDK 地图、SLAM 状态和栅格地图；合并并管理数据库本地点位。 |
| `data.py` | 初始化和持久化 SQLite 数据；提供关节、末端位姿、地图点位的 CRUD，以及线程安全的 `synch` 变量表。 |
| `modbus.py` | 按 `datas/modbus.json` 配置轮询 Modbus TCP 保持寄存器；将读值写入 `synch`，并将待写变量同步至设备。 |
| `s7.py` | 轮询并同步西门子 S7 数据块变量，逻辑与 Modbus 同步机制一致。 |
| `programs.py` | 管理 `runtime/programs/`：运行、调试单步、终止、复制、上传、读取与删除程序文件。 |

## `synch` 工业设备变量同步

`data.py` 在内存中维护线程安全的 `synch` 列表。每一项包含协议类型、操作类型（`read` / `write`）、设备地址、变量名、值与同步状态。

- `modbus.py`、`s7.py` 初始化配置后注册同步项并周期读取设备，将读值更新到对应 `read` 项。
- 客户端向 `/humanoid/data/read` 发送 `{"name": "变量名"}`，可读取最新值。
- 客户端向 `/humanoid/data/write` 发送 `{"name": "变量名", "value": 值}`，会将对应 `write` 项标记为待同步。
- 后台协议轮询线程发现待同步写项后写入设备，成功后更新同步状态。

## 开发注意事项

- 服务设计为**单一入口进程**；新功能应新增组件模块，并由 `main.py` 统一初始化和路由，不应再启动额外的独立服务进程。
- MQTT 控制消息应保持 JSON 格式，并在 `common.py` 定义主题常量后由 `main.py` 显式订阅与分发。
- 硬件控制依赖真实机器人及 GDK 环境。不要在未连接设备的机器上直接执行会驱动关节、底盘或夹爪的命令。

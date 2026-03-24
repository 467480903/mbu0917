# Services2 — 机器人控制系统重构

基于 `agents.md` 规格文档，对 `services/` 目录代码的重构版本。
目标机器人为**智元 G2 人形机器人**，通过 **MQTT 报文**进行交互：Python 侧使用 G2 GDK 激活设备驱动层，收到 MQTT 请求报文后执行设备动作，动作完成后再回传反馈/完成报文。

## 旧 web 状态兼容

`serivces2` 不创建单独的集中式 `status.py`。状态读取和发布由拥有相应
GDK 对象的控制器负责，并兼容旧 `web/` 使用的主题：

- `JointController`：5 Hz 发布 `/humanoid/status/data` 的 `joints` 片段。
- `PoseController`：5 Hz 发布 `left_ee`、`right_ee`、`waist_pose` 片段。
- `ChassisController`：5 Hz 发布 `chassis`，按需向
  `/humanoid/status/cloud` 发布前后激光点云。
- `EndEffectorController`：5 Hz 发布 `grippers` 片段。
- `CameraController`：3 Hz 更新四路相机内存缓存；旧网页发出 `start` 后，
  才向 `/humanoid/camera/data` 发布画面。

旧 `web/js/index.js` 合并这些状态片段，因此关节、末端和底盘状态不会互相覆盖。
`web/` 是正式网页入口；`web2/` 不再作为主界面。

`g2.py` 还提供旧网页兼容主题：

- 关节/位姿数据：`/humanoid/joints/save` → `/humanoid/joints/data`
- 坐标点位：`/humanoid/positions/control` → `/humanoid/positions/data`
- 地图与地图点位：`/humanoid/map/control`、`/humanoid/map/db_control`
- Modbus/S7：`/humanoid/modbus/control` → `/humanoid/modbus/data`
- 相机、关节、底盘、夹爪、TTS 保持旧 web 的原主题协议。

程序列表、执行和单步调试由 `runtime2/run.py` 独立服务提供，
不在 `service2/g2.py` 中复制调试器。

### 启动旧 web 整套服务

```bash
cd /data/wxf/mbu0917
source /home/agi/app/env.sh /home/agi/app
python3 service2/g2.py

# 独立 Apriltag 服务（不加载 GDK）
PYTHONPATH=/home/agi/.local/lib/python3.10/site-packages \
  .venv-apriltag/bin/python service2/apriltag.py

# 另一终端：程序调试服务
python3 runtime2/run.py

# 另一终端：旧 web 静态页面
python3 -m http.server 8004 -d web
```

访问 `http://<机器人IP>:8004/index.html`。

## 目录文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `agents.md` | 文档 | 重构规格说明书（目标、交互方式、测试要求、代码风格、功能划分） |
| `config.json` | 配置 | MQTT broker 地址、各模块 topic、数据/图片/识别输出路径 |
| `database_controller.py` | 控制器 | SQLite 数据库读写（关节角、位姿、地图点位） |
| `chassis_controller.py` | 控制器 | 底盘运动，以及当前地图、激光点云、地图点位、地图坐标、电池状态读取 |
| `joint_controller.py` | 控制器 | 全身关节控制（头/腰/左右臂/全身） |
| `pose_controller.py` | 控制器 | 左右手末端位姿控制（含腰部上下前后） |
| `end_effector_controller.py` | 控制器 | 末端爪子张合 |
| `interaction_controller.py` | 控制器 | TTS 语音输出 |
| `camera_controller.py` | 控制器 | 头部彩色/深度、左右手腕相机单帧读取与双文件拍照保存 |
| `apriltag_controller.py` | 控制器 | Apriltag 图片识别解析 |
| `g2.py` | 服务入口 | GDK 控制、状态、相机和数据库 MQTT 服务；不加载 Apriltag |
| `apriltag.py` | 服务入口 | 使用 `.venv-apriltag` 的独立 Apriltag MQTT 服务 |
| `run.sh` | 自启动管理 | 启动 g2、Apriltag、runtime 和 web 四个进程 |
| `README.md` | 文档 | 本说明 |

## 整体架构

- 每个功能模块都是一个**独立的类**，所有变量与函数都包裹在类中，**没有 `main` 函数、没有 `get_controller`、没有 `handle_request`**。
- 构造函数**通过参数传入** GDK 对象与 MQTT 客户端对象，避免在模块内自行创建/获取全局依赖。
- 涉及 GDK 调用的函数**不嵌套其他子函数**，直接调用功能，防止过度嵌套。
- 报文约定：请求 topic `.../request/`，反馈 topic `.../response/`，动作完成统一发到 `/humanoid/done/`（带 `type` 字段区分来源模块）。

## 各控制器详解

### 1. 数据库控制器 `database_controller.py`

- **不涉及运动**，使用默认系统 Python；引用 关节/位姿/底盘 三个控制器（可选注入）用于「运动到位置」。
- 构造函数：`DatabaseController(db_path, joint_controller=None, pose_controller=None, chassis_controller=None)`
- 核心方法 `init()`：从文件加载到内存 SQLite（`:memory:`），写操作后 `_sync_to_file()` 同步回文件。
- 数据表：`joints`、`positions`、`map_points`；每类数据实现 增(add)/删(delete)/改(update)/读取所有(get_all)/运动到位置(move)，无查询功能，数据一律按名称字符排序。
- 姿态变量 `positions` 统一分为四类：`left`（左手）、`right`（右手）、`both`（左右手）、`waist`（腰部）。腰部数据统一保存为 `x/y/z/rx/ry/rz`。
- `joints` 表字段为 `id/type/name/joint_name/value`。类型限定为 `whole_body`（全身22关节）、`left_arm`（左手7关节）、`right_arm`（右手7关节）和 `single_joint`（单轴）；仅单轴变量填写 `joint_name`。
- 主要方法（以关节为例，位姿/地图点位同构）：
  - `add_joints(type, name, value, joint_name=None)` / `update_joints(type, name, value, joint_name=None)` / `delete_joints(type, name)`
  - `get_joints()` — 读取所有（按名称排序）
  - `move_joints(name)` — 运动到位置（委托关节控制器，禁止自动化测试）

### 2. 底盘控制器 `chassis_controller.py`

- 构造函数：`ChassisController(agibot_gdk, mqtt_client, topic_response, topic_done)`（不引用数据库控制器，内部创建 Pnc/Slam/Map/Lidar/Robot）
- 既支持**蟹行斜走**，也支持 **Ackermann 方式转弯**，以及前后直行。
- 单位约定：x/y 为毫米，rotate 为角度，vel_line 为米/秒，vel_rotate 为度/秒。
- 主要方法：
  - `relative_move(x_mm, y_mm, rotate_deg, timeout)` — 基于 GDK `relative_move`，内部 `while` 判断到位。
  - `point_move(point, timeout)` — 接收点位字典 `{position, orientation, name}`，使用 GDK `normal_navi`（支持到点重定位），非阻塞下发后循环判断到达。
  - `points_move(points, vel_line, vel_rotate_deg, timeout)` — points 为点位字典列表，多点依次导航；**最后一个点用 `normal_navi` 走精度，其余点用 `relative2_move` 走**。
  - `relative2_move(...)` — 带速度参数的相对运动：先转角（`vel_rotate`）→ 蟹行直线（分 12 段：前 4 段加速、中 4 段匀速、后 4 段减速，队列式执行）→ 到位后最终转角。
  - `stop()` — 立即停止底盘。
  - `get_map_data()` — 读取当前地图 `OccupancyGrid`，返回宽高、分辨率、原点和 gzip+base64 栅格数据，网页解压后绘制。
  - `get_laser_points()` — 读取前后激光雷达真实点云，过滤 30 米外点并按 4 倍降采样。
  - `get_current_map_pose()` — 通过 `slam.get_curr_pose()` 读取底盘地图坐标与朝向，同时返回定位状态和置信度。
  - `get_map_points()` — 读取当前地图内部保存的全部引导点。
  - `get_battery()` — 读取两组底盘电池的 SOC/SOH、电压、电流和温度。
  - `get_map_snapshot()` — 一次返回网页显示需要的全部真实地图数据。
- 内部辅助：`_task_state`、`_cancel_navi`、`_request_chassis`、`_make_twist`、`_stop_chassis`、`_wait_stop`、`_wait_navi_done`、`_rotate_to`、`_move_line`、`_get_current_pose` 等。

### 3. 关节控制器 `joint_controller.py`

- 构造函数：`JointController(robot, mqtt_client, topic_response, topic_done)`
- **不在内部加载数据库控制器**。
- 关节分组：头部 3、腰部（body）5、左手 7、右手 7、全身 22。
- 由于 `move_head_joint` / `move_waist_joint` / `move_arm_joint` 均为**阻塞式**运动，每个运动函数执行前发送“运动命令下发告知”，执行后发送“运动到位完成”信号。
- 主要方法：
  - `move_head(joints, speed=None)` / `move_waist(joints, speed=None)`
  - `move_left_arm(joints, speed=None)` / `move_right_arm(joints, speed=None)`
  - `move_arms(joints_dict, speed=None)` — 双臂 14 关节
  - `move_wbc(agibot_gdk, joints_dict, speed=None)` — 全身 22 关节（`joint_control_request` 批量下发）
  - `move_single_joint(name, value=None, offset=None, speed=None)` — 单关节绝对/增量控制

### 4. 位姿控制器 `pose_controller.py`

- 构造函数：`PoseController(robot, mqtt_client, topic_response, topic_done)`（不引用数据库控制器）
- 控制左右手末端位姿，以及腰腿在 `base_link` 坐标系内的 X 前后、Z 上下运动。
- 腰部姿态变量支持绝对定位：读取当前五个腰腿关节角，按 URDF 链对保存的 `x/z/rx/ry/rz` 做解析逆解，校验工作空间和关节限位后执行腰部关节运动。
- 数学工具：`slerp`（四元数球面插值）、`euler_to_quaternion`、`quaternion_multiply`、`distance`。
- 腰腿几何来自 `web/meshes/model.urdf` 的 `base_link -> body_link5` 串联链。等价改进 DH/URDF 参数如下：

  | 关节 | 关节轴 | URDF 原点 xyz (m) | 限位 (rad) |
  |---|---|---|---|
  | `idx01_body_joint1` | Y | `[0.102, 0, 0.144]` | `[-1.0821, 0]` |
  | `idx02_body_joint2` | Y | `[0, 0, 0.360]` | `[0, 2.6529]` |
  | `idx03_body_joint3` | Y | `[0, 0, 0.380]` | `[-1.919, 1.117]` |
  | `idx04_body_joint4` | X | `[0, 0, 0]` | `[-0.4363, 0.4363]` |
  | `idx05_body_joint5` | Z | `[0, 0, 0.149]` | `[-3.0456, 3.0456]` |

  前三轴构成 X/Z 平面 3R 链。控制器从 GDK 读取五轴当前角度，按 URDF 原点变换做正解；逆解时联动前三轴并约束
  `q1 + q2 + q3` 保持不变，因此上身俯仰不随平移改变，关节 4/5 保持当前角度。目标还会经过可达域、URDF 限位、
  单次笛卡尔步长（最大 0.03 m）、单次关节变化（最大 0.20 rad）和速度（0.02~0.50 rad/s）检查。
- 主要方法：
  - `move_left_arm(position, orientation)` / `move_right_arm(...)`
  - `move_both_arms(left_target, right_target)`
  - `move_relative(side, offset, rotation)`
  - `move_waist(offset, speed=None)` — `offset=[X前后, Y侧向, Z上下]`（米），当前要求 Y 必须为 0
  - `get_current_pose(side)`
- 腰腿 MQTT：新版 `/humanoid/pose/request/` 使用
  `{"cmd":"waist","offset":[0.01,0,0],"speed":0.2}`；旧网页通过
  `/humanoid/commands/data` 使用 `{"command":"waist_move","data":{"forward":0.01,"up":0}}`。
- 内部辅助：`_waist_forward_kinematics`、`_waist_inverse_kinematics`、`_get_current_waist_angles`、
  `_find_pose`、`_n_steps`、`_plan`、`_send_trajectory`、`_send_dual_trajectory`、`_hold_at_pose`、`_recover_quat`。

### 5. 末端控制器 `end_effector_controller.py`

- 构造函数：`EndEffectorController(robot, mqtt_client, topic_response, topic_done)`
- 控制末端爪子的张合（0.0=完全闭合，1.0=完全张开）。
- 主要方法：
  - `left_gripper(position)` / `right_gripper(position)`
  - `left_gripper_action(action)` / `right_gripper_action(action)`（`open`/`close`）
  - `both_grippers(left_position, right_position)`

### 6. 交互控制器 `interaction_controller.py`

- 构造函数：`InteractionController(interaction, mqtt_client, topic_response)`
- 控制 TTS 输出，不涉及运动。
- 主要方法：`speak(text)`、`set_volume(volume)`（0~100）、`get_volume()`。

### 7. 摄像头控制器 `camera_controller.py`

- 构造函数：`CameraController(camera, mqtt_client, topic_response, image_save_dir)`
- 控制头部彩色相机、头部深度相机、左右手腕相机的单帧读取和拍照保存。
- 支持相机：`kHeadColor`、`kHeadDepth`、`kHandLeftColor`、`kHandRightColor`。
- 主要方法：
  - `capture(camera_name)` — 拍照并同时保存 `{相机}-{时间戳}.jpg` 和 `{相机}-latest.jpg`
  - `capture_all()` — 拍摄全部相机
  - `get_image_base64(camera_name)` — 返回可供网页显示的 JPEG Base64

### 8. Apriltag 图片解析控制器 `apriltag_controller.py`

- 构造函数：`ApriltagController(mqtt_client, topic_response, image_save_dir)`
- 对摄像头控制器保存的图片做识别解析；`apriltag.py` 使用独立虚拟环境 `.venv-apriltag` 自启动，不加载 GDK。
- MQTT：订阅 `/humanoid/apriltag/request/`，响应 `/humanoid/apriltag/response/`。`detect_head` 默认识别 `images/kHeadColor-latest.jpg`。
- 主要方法：
  - `init()` — 初始化 `pyapriltags` 检测器（tag36h11）
  - `detect_image(image)` / `detect_file(filepath)` / `detect_saved_image(filename)`
  - 静态辅助：`_rotmat_to_quat(R)`

## 配置文件 `config.json`

```json
{
  "mqtt":   { "broker": "localhost", "port": 1883 },
  "topics": {
    "base":     { "request": "/humanoid/base/request/",     "response": "/humanoid/base/response/" },
    "joint":    { "request": "/humanoid/joint/request/",    "response": "/humanoid/joint/response/" },
    "pose":     { "request": "/humanoid/pose/request/",     "response": "/humanoid/pose/response/" },
    "ee":       { "request": "/humanoid/ee/request/",       "response": "/humanoid/ee/response/" },
    "tts":      { "request": "/humanoid/tts/request/",      "response": "/humanoid/tts/response/" },
    "camera":   { "request": "/humanoid/camera/request/",   "response": "/humanoid/camera/response/" },
    "apriltag": { "request": "/humanoid/apriltag/request/", "response": "/humanoid/apriltag/response/" },
    "db":       { "request": "/humanoid/db/request/",       "response": "/humanoid/db/response/" },
    "maptest":  { "request": "/humanoid/maptest/request/",  "response": "/humanoid/maptest/response/" },
    "done": "/humanoid/done/"
  },
  "paths": { "datas": "datas", "images": "images", "detect": "detect" }
}
```

## 代码风格约定

1. **防止过度嵌套**：涉及 GDK 调用的函数不嵌套其他子函数，直接调用功能。
2. **类封装**：所有变量、函数都包裹在类里面。
3. **构造函数传参**：把 GDK 对象、MQTT 对象作为参数传入构造函数。
4. **无入口函数**：不要 `main` 函数，也不要 `get_controller` / `handle_request`。
5. **测试覆盖**：每个关键功能函数都要在 `test/services2/` 下有对应测试文件。

## 测试

测试目录：`test/services2/`

| 测试文件 | 覆盖模块 | 是否可直接运行 |
|----------|----------|----------------|
| `test_database_controller.py` | 数据库 | 是（系统 Python） |
| `test_chassis_controller_relative.py` | 底盘相对运动 | 否（需人工确认） |
| `test_chassis_controller_stop.py` | 底盘停止 | 否（需人工确认） |
| `test_chassis_controller_map_data.py` | 当前真实栅格地图读取 | 是（需 GDK 环境） |
| `test_chassis_controller_laser.py` | 前后真实激光点云读取 | 是（需 GDK 环境） |
| `test_chassis_controller_map_pose.py` | 底盘当前地图坐标读取 | 是（需 GDK 环境） |
| `test_chassis_controller_battery.py` | 底盘电池状态读取 | 是（需 GDK 环境） |
| `maptest.html` / `maptest.js` | 真实 MQTT 地图综合测试页面 | 是（运动按钮人工操作） |
| `test_maptest_web.sh` | Playwright 真实数据读取测试 | 是（不自动执行运动） |
| `test_joint_controller_head.py` | 头部关节 | 否（需人工确认） |
| `test_joint_controller_waist.py` | 腰部关节 | 否（需人工确认） |
| `test_waist_position_variable.py` | 已保存腰部姿态变量定位 | 否（需人工确认） |
| `test_joint_controller_left_arm.py` | 左臂关节 | 否（需人工确认） |
| `test_end_effector_controller.py` | 末端爪子 | 否（需人工确认） |
| `test_camera_controller.py` | 摄像头 | 是（需 GDK 环境） |
| `camera.html` / `camera.js` | 四路真实摄像头集成测试页面 | 是（需服务层和真实相机） |
| `test_camera_web.sh` | Playwright 四路摄像头按钮测试 | 是（不涉及机器人运动） |
| `test_interaction_controller.py` | TTS | 是（需 GDK 环境） |
| `test_head_rgb_apriltag.py` | 拍摄当前头部 RGB 并通过 MQTT 识别 Apriltag | 是（不涉及运动） |

### 测试要求（来自 `agents.md`）

- 每个功能模块尽量独立测试，每个子函数都有对应测试文件，测试脚本尽量简单（20 行以内）。
- 涉及机器人本体运动的测试，执行前要提示用户输入回车确认。
- 功能测试尽量以 `mosquitto_pub` 命令行（MQTT pub）为主。
- **凡涉及机器人运动的测试文件，AI agent 不能直接执行**；不涉及运动的（文件操作、数据库操作）可直接测试。

### 运行测试

```bash
# 数据库测试（默认系统 Python，可直接运行）
python3 test/services2/test_database_controller.py

# 需要 GDK 的测试（先激活环境）
source ~/app/env.bash
python3 test/services2/test_chassis_controller_stop.py

# 地图测试页面位于 test/services2/maptest.html
# 页面可分别显示/隐藏地图与激光点图层，并可通过按钮放大、缩小地图画面

# Playwright 只读取真实数据，不点击运动和数据库写入按钮
bash test/services2/test_maptest_web.sh

# Apriltag 测试（先拍摄当前头部 RGB，再请求独立服务识别）
PYTHONPATH=/home/agi/.local/lib/python3.10/site-packages \
  .venv-apriltag/bin/python test/services2/test_head_rgb_apriltag.py
```

## MQTT 命令示例

```bash
# 底盘相对运动
mosquitto_pub -t /humanoid/base/request/ -m '{"cmd":"relative","x":100,"y":0,"rotate":0,"time":"20260920120000000"}'

# 关节运动
mosquitto_pub -t /humanoid/joint/request/ -m '{"cmd":"head","joints":[0,0,0],"time":"..."}'

# 末端爪子
mosquitto_pub -t /humanoid/ee/request/ -m '{"cmd":"left_gripper","action":"open","time":"..."}'

# 摄像头拍照
mosquitto_pub -t /humanoid/camera/request/ -m '{"cmd":"capture","camera":"kHeadColor","time":"..."}'
```

## 运行环境

| 模块 | 环境 |
|------|------|
| 底盘/关节/位姿/末端/摄像头/交互控制器 | `source /home/agi/app/env.sh /home/agi/app`（GDK 环境） |
| 数据库控制器 | 默认系统 Python |
| Apriltag 控制器 | `source .venv-apriltag/bin/activate` |

## 注意事项

1. **安全第一**：涉及机器人运动的测试，执行前务必确认周围环境安全。
2. **环境激活**：GDK 服务需先执行 `source /home/agi/app/env.sh /home/agi/app`。
3. **Apriltag 环境**：Apriltag 服务由 `.venv-apriltag/bin/python` 启动，依赖通过专用 `PYTHONPATH` 提供，不加载 GDK。
4. **MQTT Broker**：确保 MQTT Broker（如 mosquitto）已启动。

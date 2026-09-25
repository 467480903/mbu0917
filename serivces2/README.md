# Services2 — 机器人控制系统重构

基于 `agents.md` 规格文档，对 `services/` 目录代码的重构版本。
目标机器人为**智元 G2 人形机器人**，通过 **MQTT 报文**进行交互：Python 侧使用 G2 GDK 激活设备驱动层，收到 MQTT 请求报文后执行设备动作，动作完成后再回传反馈/完成报文。

## 目录文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `agents.md` | 文档 | 重构规格说明书（目标、交互方式、测试要求、代码风格、功能划分） |
| `config.json` | 配置 | MQTT broker 地址、各模块 topic、数据/图片/识别输出路径 |
| `database_controller.py` | 控制器 | SQLite 数据库读写（关节角、位姿、地图点位） |
| `chassis_controller.py` | 控制器 | 底盘运动（相对/到点/多点/停止/带速度相对运动） |
| `joint_controller.py` | 控制器 | 全身关节控制（头/腰/左右臂/全身） |
| `pose_controller.py` | 控制器 | 左右手末端位姿控制（含腰部上下前后） |
| `end_effector_controller.py` | 控制器 | 末端爪子张合 |
| `interaction_controller.py` | 控制器 | TTS 语音输出 |
| `camera_controller.py` | 控制器 | 头部彩色/深度、左右手腕相机拍照与图像流 |
| `apriltag_controller.py` | 控制器 | Apriltag 图片识别解析 |
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
- 主要方法（以关节为例，位姿/地图点位同构）：
  - `add_joints(type, name, value)` / `update_joints(type, name, value)` / `delete_joints(type, name)`
  - `get_joints()` — 读取所有（按名称排序）
  - `move_joints(name)` — 运动到位置（委托关节控制器，禁止自动化测试）

### 2. 底盘控制器 `chassis_controller.py`

- 构造函数：`ChassisController(pnc, slam, mqtt_client, topic_response, topic_done)`（不引用数据库控制器）
- 既支持**蟹行斜走**，也支持 **Ackermann 方式转弯**，以及前后直行。
- 单位约定：x/y 为毫米，rotate 为角度，vel_line 为米/秒，vel_rotate 为度/秒。
- 主要方法：
  - `relative_move(agibot_gdk, x_mm, y_mm, rotate_deg, timeout)` — 基于 GDK `relative_move`，内部 `while` 判断到位。
  - `point_move(agibot_gdk, point, timeout)` — 接收点位字典 `{position, orientation, name}`，使用 GDK `normal_navi`（支持到点重定位），非阻塞下发后循环判断到达。
  - `points_move(agibot_gdk, points, vel_line, vel_rotate_deg, timeout)` — points 为点位字典列表，多点依次导航；**最后一个点用 `normal_navi` 走精度，其余点用 `relative2_move` 走**。
  - `relative2_move(...)` — 带速度参数的相对运动：先转角（`vel_rotate`）→ 蟹行直线（分 12 段：前 4 段加速、中 4 段匀速、后 4 段减速，队列式执行）→ 到位后最终转角。
  - `stop(agibot_gdk)` — 立即停止底盘。
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
- 控制左右手末端在世界坐标系的绝对位姿；支持左右手/左手/右手/腰部（上下前后）4 种运动方式。
- 数学工具：`slerp`（四元数球面插值）、`euler_to_quaternion`、`quaternion_multiply`、`distance`。
- 主要方法：
  - `move_left_arm(agibot_gdk, position, orientation)` / `move_right_arm(...)`
  - `move_both_arms(agibot_gdk, left_target, right_target)`
  - `move_relative(agibot_gdk, side, offset, rotation)`
  - `move_waist(agibot_gdk, offset)` — 通过双臂联动实现腰部上下前后
  - `get_current_pose(side)`
- 内部辅助：`_find_pose`、`_n_steps`、`_plan`、`_send_trajectory`、`_send_dual_trajectory`、`_hold_at_pose`、`_recover_quat`。

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
- 控制头部彩色相机、头部深度相机、左右手腕相机的**视频流输出和拍照保存**。
- 支持相机：`kHeadColor`、`kHeadDepth`、`kHandLeftColor`、`kHandRightColor`。
- 主要方法：
  - `capture(agibot_gdk, camera_name)` — 拍照保存（JPEG/OpenCV 编码/原始数据三种兜底）
  - `capture_all(agibot_gdk)` — 拍摄全部相机
  - `get_image_base64(agibot_gdk, camera_name)` — 返回图像 base64

### 8. Apriltag 图片解析控制器 `apriltag_controller.py`

- 构造函数：`ApriltagController(mqtt_client, topic_response, image_save_dir)`
- 对摄像头控制器保存的图片做识别解析；**使用独立虚拟环境 `.venv-apriltag`（不依赖 GDK）**。
- 主要方法：
  - `init()` — 初始化 `dt_apriltags` 检测器（tag36h11）
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
| `test_joint_controller_head.py` | 头部关节 | 否（需人工确认） |
| `test_joint_controller_waist.py` | 腰部关节 | 否（需人工确认） |
| `test_joint_controller_left_arm.py` | 左臂关节 | 否（需人工确认） |
| `test_end_effector_controller.py` | 末端爪子 | 否（需人工确认） |
| `test_camera_controller.py` | 摄像头 | 是（需 GDK 环境） |
| `test_interaction_controller.py` | TTS | 是（需 GDK 环境） |
| `test_apriltag_controller.py` | Apriltag | 是（.venv-apriltag 环境） |

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

# Apriltag 测试（使用独立虚拟环境）
source .venv-apriltag/bin/activate
python3 test/services2/test_apriltag_controller.py
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
| 底盘/关节/位姿/末端/摄像头/交互控制器 | `source ~/app/env.bash`（GDK 环境） |
| 数据库控制器 | 默认系统 Python |
| Apriltag 控制器 | `source .venv-apriltag/bin/activate` |

## 注意事项

1. **安全第一**：涉及机器人运动的测试，执行前务必确认周围环境安全。
2. **环境激活**：GDK 控制器需先激活环境 `source ~/app/env.bash`。
3. **Apriltag 环境**：Apriltag 控制器需独立环境 `source .venv-apriltag/bin/activate`，且不依赖 GDK。
4. **MQTT Broker**：确保 MQTT Broker（如 mosquitto）已启动。

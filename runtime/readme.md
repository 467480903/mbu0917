# Runtime 程序运行时

`runtime/` 是 agiBot-G2 控制系统的**任务脚本运行模块**。它让用户将机器人动作编排为 Python 程序，并通过 Web 控制台或 MQTT 完成程序文件管理、运行和逐行单步调试。

> 脚本会直接控制真实机器人及其末端、底盘、相机等设备。执行前请确认场地清空、急停可用、GDK 已就绪且 MQTT Broker 已连接。不要在不了解动作时序的情况下运行或覆盖程序。

## 工作方式

Runtime 不是独立的机器人后端。正式运行链路如下：

```text
Web 控制台 / MQTT 客户端
  │  /humanoid/programs/control
  ▼
services/main.py
  ▼
services/programs.py
  ├─ 管理 runtime/programs/*.py
  ├─ 将选中的程序复制为 runtime/main.py
  └─ 用 runpy 执行 runtime/main.py
       │
       ▼
runtime/minth.py（Minth.G2 SDK）
       │  MQTT :1883
       ▼
机器人控制服务（关节、底盘、相机、末端等）
```

`services/programs.py` 执行的始终是 `runtime/main.py`，而不是直接执行 `runtime/programs/` 内的文件。标准流程是：先将程序保存到 `programs/`，再用 `copy` 复制为 `main.py`，最后运行或调试。

## 目录结构

```text
runtime/
├── main.py        # 当前工作副本；服务端实际执行的脚本
├── minth.py       # 脚本侧 SDK，提供 Minth.G2 控制接口
├── programs/      # 可由控制台管理、复制和执行的 Python 程序库
├── run.py         # 旧版独立调试服务（使用 /runtime_* 主题）
└── readme.md      # 本文档
```

- `main.py`：由 `copy` 操作从 `programs/` 覆盖，运行和调试时均以它为目标。
- `minth.py`：封装 MQTT 通信和 G2 常用动作接口，供程序通过 `from minth import Minth` 导入。
- `programs/`：保存可复用的 `.py` 程序文件。文件可读取、上传、删除、复制到 `main.py`。
- `run.py`：遗留的独立调试服务，使用 `/runtime_debug` 等旧主题；当前 Web 控制台和统一服务使用 `/humanoid/programs/*`，不要将两套机制同时作为正式入口运行。

## 编写程序

程序放在 `runtime/programs/`，使用 `Minth.G2` 创建机器人客户端：

```python
from minth import Minth
import time

G2 = Minth.G2()
try:
    # 移动到地图导航点，并等待服务端完成通知
    G2.GO(9)

    # 执行已保存的全身姿态
    G2.WBC("hold")

    # 相对移动：x 前/后、y 左/右，单位为米；yaw_rad 单位为弧度
    G2.REL({"x": 0.3, "y": 0.0, "yaw_rad": 0.0})
finally:
    G2.close()
```

创建 `G2` 时，SDK 会连接本机 MQTT Broker（`localhost:1883`），订阅命令完成和末端位姿结果主题；约 5 秒内无法连接会抛出 `ConnectionError`。建议用 `try/finally` 保证脚本结束时调用 `G2.close()`，以停止 MQTT 网络循环并断开连接。

## Minth.G2 接口

### 导航与底盘

| 方法 | 用途 | 返回语义 |
| --- | --- | --- |
| `GO(num)` | 导航至整型地图点位编号 | 等待匹配的完成通知，最长默认 15 秒。 |
| `GO_NOWAIT(num)` | 下发地图点位导航 | 仅确认本地 MQTT publish 调用成功；不等待机器人启动、到点或完成。 |
| `REL({"x", "y", "z"?, "yaw_rad"})` | 使用 GDK 相对导航移动，x 前+/后-，y 左+/右-，单位米 | 等待完成通知。 |
| `REL_ODOM(data, speed=0.25)` | 使用里程计闭环相对移动；`speed` 是线速度上限（m/s），不支持 z 位移 | 等待完成通知。 |
| `REL_NOWAIT(data)` | 下发 GDK 相对导航移动 | 仅确认本地 MQTT publish 调用成功；不等待执行结果。 |

`GO_NOWAIT` 和 `REL_NOWAIT` 会直接下发底盘命令。它们不会等待，并且底盘控制器也不会预先查询或取消已有导航任务；调用方必须自行保证动作时序与安全。

### 关节、末端与夹爪

| 方法 | 用途 |
| --- | --- |
| `WBC(name, speed=None)` | 通过单个 GDK 全身关节请求执行动作；`speed` 可选。 |
| `ARMS(name, speed=None)`、`LEFT(name, speed=None)`、`RIGHT(name, speed=None)` | 执行双臂、左臂或右臂动作；`speed` 可选。 |
| `HEAD(name)`、`WAIST(name)` | 执行头部或腰部动作。 |
| `JOINT(name, offset=rad)` | 按弧度增量调整单关节。 |
| `JOINT(name, value=rad)` | 将单关节运动至目标弧度；同时传 `offset` 时优先使用 `value`。 |
| `OFFSET(data)` | 末端相对移动。平移 `lx/ly/lz`、`rx/ry/rz` 单位为 mm；旋转使用 `lrx/lry/lrz`、`rrx/rry/rrz`，单位为度。 |
| `MoveL(position, offset=None)` | 移动至数据库中已保存的右臂坐标点；等待 `/humanoid/positions/data`，最长 30 秒。 |
| `GRIPPER({"left": value, "right": value})` | 操作指定侧夹爪；负值张开，正值闭合。 |

动作名称必须与机器人数据库中已保存的对应动作类型和名称一致。`MoveL` 当前固定使用右臂点位；其 `offset` 后端仅支持 `x/y/z` 平移偏移（mm）。

### 感知与辅助动作

| 方法 | 用途 |
| --- | --- |
| `YOLO(model="wxf.pt", ip=None)` | 触发头部相机采集与 YOLO 检测，最长等待 120 秒。结果写入 `detect/detect.json`。 |
| `CHASSIS_CORRECT(...)` | 根据检测结果中的 `horizontal_offset_px` 换算并执行底盘横向纠偏。 |
| `WAIST_CORRECT(...)` | 根据检测结果中的 `angle_rad` 对腰部关节做增量纠偏。 |
| `TTS(text)` | 语音播报。 |
| `DONE(message=None)` | 向完成主题发布通知，仅表示 MQTT 发布成功。 |
| `close()` | 停止 MQTT 网络循环并断开连接。 |

## 同步与异步语义

除 `GO_NOWAIT`、`REL_NOWAIT` 和 `DONE` 外，大部分 `G2` 方法会通过 MQTT 发布命令，并等待 `/humanoid/commands/done` 上同名命令的完成通知，默认超时为 15 秒。

收到完成通知不等同于底层 GDK 已明确报告动作成功：服务端会在命令处理结束时发布通知，且部分底层异常会被处理器记录后返回。多个脚本或客户端不要并发发送同名的同步命令，因为完成消息按命令名匹配，缺少请求 ID 的严格关联。

## 程序管理与调试

正式控制主题为 `/humanoid/programs/control`，消息格式为：

```json
{"command": "<操作>", "data": "<可选数据>"}
```

| `command` | `data` | 行为 |
| --- | --- | --- |
| `read_files` | 无 | 发布 `programs/` 中的 Python 文件列表。 |
| `read_file` | `"demo.py"` | 读取程序内容。 |
| `upload` | `{"filename":"demo.py","content":"..."}` | 新建或覆盖 `programs/` 下的 `.py` 文件。 |
| `delete` | `"demo.py"` | 删除程序文件。 |
| `copy` | `"demo.py"` | 将程序原样覆盖到 `runtime/main.py`。 |
| `codes` | 无 | 读取当前 `main.py` 内容。 |
| `run` | 无 | 在后台线程中正常运行 `main.py`。 |
| `debug` | 无 | 以单步模式运行 `main.py`。 |
| `next` | 无 | 放行单步调试中的下一行。 |
| `stop` | 无 | 请求停止当前程序。 |

推荐顺序：

1. 将程序放入 `runtime/programs/`，或通过 `upload` 保存；
2. 使用 `read_file` 检查内容；
3. 发送 `copy`，将目标程序复制为 `main.py`；
4. 使用 `codes` 复核当前工作副本；
5. 在确保安全后发送 `run` 或 `debug`。

### 单步调试限制

`debug` 会在 `main.py` 每行执行前向 `/humanoid/programs/step` 发布行号和代码，然后等待 `next`。调试器只跟踪 `main.py`，不会逐行进入 `minth.py` 等导入模块。

`stop` 会设置停止标志，并释放等待 `next` 的调试线程；真正中断发生在下一次 Python 行跟踪事件。因此，正在等待 MQTT/GDK、`sleep` 或其他阻塞 I/O 的调用不会被立即终止，已下发到硬件的机器人动作也不会因停止脚本而自动停止。

## 程序管理主题

| 主题 | 服务端发布内容 |
| --- | --- |
| `/humanoid/programs/step` | `{"filename":"main.py","lineno":1,"code":"..."}` |
| `/humanoid/programs/codes` | `{"code":"..."}` |
| `/humanoid/programs/files` | `{"files":["a.py","b.py"]}` |
| `/humanoid/programs/file_content` | 文件名、代码、`success` 与可选 `error`。 |
| `/humanoid/programs/upload_result` | 上传结果、文件名或错误。 |
| `/humanoid/programs/delete_result` | 删除结果、文件名或错误。 |

## 文件管理约束

- `programs/` 列表只包含 `.py` 文件，并排除 `__init__.py`。
- `upload` 和 `read_file` 只允许 `.py` 文件名，且拒绝 `/`、`\` 和 `..`，避免路径穿越。
- `delete` 禁止删除名为 `main.py` 的文件。
- `copy` 会直接覆盖 `runtime/main.py`，没有自动备份或版本管理；应始终把源程序保留在 `programs/` 中。

## 已知兼容性说明

- `runtime/programs/c.py` 中调用的 `G2.VLA(...)` 不在当前 `minth.py` 的 `G2` API 中，直接运行会发生 `AttributeError`。请删除、替换该调用或先实现相应接口。
- `YOLO(ip=...)` 会在 MQTT 消息中携带 `yolo_ip`，但当前服务端检测逻辑未使用该字段；检测端地址仍由服务端配置决定。
- `runtime/run.py` 是旧版独立调试服务，主题为 `/runtime_debug`、`/runtime_step` 等；当前程序控制台与统一服务不使用这些主题。

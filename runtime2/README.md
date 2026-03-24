# runtime2 中文用户层

`runtime2` 是面向用户自定义程序的 G2 MQTT 客户端。它不直接加载 GDK，所有操作通过 `serivces2` 约定的 MQTT request/response/done 主题完成。

## 安全机制

用户层本身不弹出运动确认，便于自定义程序自动执行。运动命令发布后，方法会等待带相同 `time`、`cmd` 和模块 `type` 的 `/humanoid/done/` 完成报文；数据库中保存的关节/位姿运动等待阻塞执行后的 `/humanoid/db/response/`。

`test/runtime2/` 中的脚本不会弹出确认提示，启动后会直接执行对应接口。运行涉及本体运动的脚本前，操作者应自行确认机器人周围安全、急停可用。

## 使用

从项目根目录运行：

```bash
python3 runtime2/demo.py
```

示例：

```python
from runtime2 import G2

with G2() as 机器人:
    机器人.底盘相对运动(前后=100, 左右=0, 转角=0)
    机器人.夹爪(左夹爪=1.0, 右夹爪=1.0)
    机器人.语音输出("动作完成")
```

底盘到点运动与上肢动作并行执行：

```python
from runtime2 import G2

with G2() as 机器人:
    机器人.底盘到点运动不等待("P1")
    try:
        机器人.全身关节运动("A1", 角速度=0.1)
        机器人.左手关节运动("JL1", 角速度=0.1)
        机器人.末端偏移量(
            右偏移量={
                "position": [0.0, 0.0, 0.05],
                "rotation": [0.0, 0.0, 0.0],
            }
        )
    finally:
        机器人.等待底盘运动结束()
```

`底盘到点运动不等待()` 只等待服务确认导航任务已经成功下发，不等待底盘到达；
随后上肢动作可以在底盘导航期间执行。`等待底盘运动结束()` 用于最后等待底盘
真正到达目标点。一个 `G2` 实例同时只允许保留一个未等待完成的底盘任务。

单位遵循 `serivces2`：底盘位移为毫米、转角为度、线速度为米/秒、角速度为度/秒；关节目标角度遵循 GDK，使用弧度；末端偏移位置使用米、旋转使用度。

## 中文 API

- `底盘相对运动(前后=0, 左右=0, 转角=0)`，未传入的分量不运动
- `底盘地图点运动(点位序号)`
- `底盘到点运动不等待(点位序号)`，导航命令成功下发后立即返回
- `等待底盘运动结束(timeout=None)`，等待上一次不等待到点运动真正结束
- `底盘相对运动带速度(前后, 左右, 转角, 线速度, 角速度)`
- `夹爪(左夹爪=None, 右夹爪=None)`，位置范围 `0.0~1.0`
- `末端偏移量(左偏移量=None, 右偏移量=None)`
- `全身关节运动(关节变量, 角速度=None)`
- `左手关节运动(左手关节变量, 角速度=None)`
- `右手关节运动(右手关节变量, 角速度=None)`
- `单关节变量运动(单关节变量, 角速度=None)`
- `左手坐标姿态运动(变量, 末端线速度=None, 末端角速度=None)`
- `右手坐标姿态运动(变量, 末端线速度=None, 末端角速度=None)`
- `单关节运动(关节名称, 目标角度, 角速度=None)`
- `单关节相对运动(关节名称, 递增量, 角速度=None)`
- `读取当前全身所有关节角()`，返回 `{关节名称: 角度弧度值}`
- `读取当前左手末端坐标姿态()`，返回 `position` 和 `orientation`
- `读取当前右手末端坐标姿态()`，返回 `position` 和 `orientation`
- `头部全局相机拍照()`，保存到 `images/` 并返回绝对路径
- `语音输出(文本内容)`
- `同步数据读取(变量名称)`
- `同步数据写入(变量名称, 值)`

## 服务与人工测试

先在 GDK 环境中启动统一服务：

```bash
source /home/agi/app/gdk/scripts/env.sh /home/agi/app
python3 serivces2/main.py
```

然后从项目根目录单独运行需要验证的脚本，例如：

```bash
python3 test/runtime2/test_12_tts.py
```

这些脚本也支持从任意工作目录以绝对路径运行。runtime2 MQTT 测试请使用安装了
`paho-mqtt` 的系统 `python3`；不要使用仅供 Apriltag 功能使用的
`.venv-apriltag/bin/python`。

每个测试文件直接创建 `G2` 并调用一个中文接口，不再使用模拟 MQTT，也不包含交互式确认；不要用 `unittest discover` 批量执行这些脚本。

## 用户程序目录

用户程序与运行框架统一放在 `runtime2/` 目录中，不再使用
`runtime2/programs/` 子目录。程序文件管理页面会遍历 `runtime2/` 下的
`.py` 文件，并自动隐藏以下框架文件：

- `__init__.py`：Python 包入口。
- `main.py`：当前待运行程序。
- `minth.py`：G2 中文用户 API。
- `run.py`：程序管理与单步调试服务。

因此默认可选择的用户程序为：

- `debug_demo.py`
- `demo.py`
- `long_action_test.py`
- `database_variable_motion_demo.py`

`database_variable_motion_demo.py` 演示按名称读取数据库变量并依次执行全身、
左臂、右臂、单关节和地图点位运动。运行前需要先把文件顶部的变量名改成
数据库中实际存在、且类型匹配的名称。

新增用户程序时，直接把 `.py` 文件放入 `/data/wxf/mbu0917/runtime2/`。

## 用户程序管理与单步调试

启动独立的程序管理服务：

```bash
cd /data/wxf/mbu0917
python3 runtime2/run.py
```

服务订阅 `/humanoid/programs/control`，支持以下命令：

- `read_files`：读取用户程序列表。
- `copy`：将选中程序复制到 `main.py`。
- `read_file`：读取指定用户程序，供网页修改或下载。
- `upload`：上传新程序或保存修改后的程序。
- `delete`：删除指定用户程序。
- `codes`：读取当前 `main.py`。
- `status`：读取程序管理服务当前的 `idle/running/paused/debugging` 状态。
- `run`、`pause`、`resume`、`stop`：运行、暂停、恢复和停止程序。
- `debug`、`next`：启动单步调试和执行下一行。

服务通过以下主题返回结果：

- `/humanoid/programs/files`：`runtime2/` 下过滤框架文件后的用户 `.py` 文件列表
- `/humanoid/programs/codes`：当前 `main.py` 源码
- `/humanoid/programs/file_content`：`read_file` 返回的文件名和源码
- `/humanoid/programs/upload_result`：上传或保存结果
- `/humanoid/programs/delete_result`：删除结果
- `/humanoid/programs/step`：trace 当前行号和源码
- `/humanoid/programs/status`：复制、运行、完成、停止或错误状态

`copy` 只接受 `runtime2/` 根目录中的用户 `.py` 文件名，不允许绝对路径、
目录穿越或选择框架文件。网页选中文件并点击“打开”后，服务以原子替换方式
覆盖 `runtime2/main.py`，并在 `main.py` 第一行写入来源注释，例如：

```python
# 本文件内容复制自用户程序：demo.py
```

该注释用于标明 `main.py` 当前内容最初复制自哪个用户程序。`debug` 只跟踪
`main.py`，每遇到一行便等待 `next`；`stop` 可结束等待中的调试。

网页点击“修改”时先通过 `read_file` 读取源程序；保存后通过 `upload` 原子替换
源程序。如果修改的是当前已打开的程序，网页会重新执行 `copy`，使
`main.py` 与保存后的源程序保持一致。上传和删除完成后，服务会自动重新发布
文件列表。所有文件操作都使用相同的文件名校验规则，不能操作框架文件、绝对
路径或父目录中的文件。

程序文件弹窗提供“新建”功能。网页通过 `create` 命令在 `runtime2/` 根目录
排他创建新的 `.py` 用户程序；如果同名文件已经存在，服务端返回错误并保留原
文件，不允许覆盖。创建成功后页面会自动打开代码编辑窗口。`main.py`、
`minth.py`、`run.py` 和 `__init__.py` 等框架文件不能通过新建功能创建或覆盖。

### 暂停与恢复

网页在普通运行模式下提供“暂停”和“恢复”按钮。`pause` 发出后，解释器会在
下一条 `main.py` 的 Python 语句执行前进入 `paused` 状态；`resume` 会从该行
继续运行。服务通过 `/humanoid/programs/status` 发布
`pause_requested`、`paused` 和 `running` 状态，网页据此更新按钮。

网页进入程序模块时会主动发送 `status`，因此刷新页面后仍能恢复服务端的真实
运行状态。运行或调试期间禁止替换 `main.py`；文件打开失败时，网页会保留文件
弹窗并显示服务端返回的原因，不再静默关闭。

暂停属于 Python 行级的协作式暂停，不是机器人运动急停。如果程序正在等待
一个 GDK/MQTT 调用返回，或某个机器人动作已经下发，暂停要等当前调用返回、
程序到达下一条 Python 语句时才会生效，也不会中断已经开始的单个动作。需要
立即停止机器人运动时，必须使用网页急停或机器人实体急停，而不是“暂停”。

安全的调试示例位于 `runtime2/debug_demo.py`。网页独立测试页为：

```text
http://10.42.1.101:8003/tests/runtime-debug.html
```

页面默认使用模拟 MQTT，不会执行程序；添加 `?live=1` 才会连接真实 MQTT。

> 网页中的“程序”模块依赖 `runtime2/run.py` 持续运行。若该进程未启动，
> 文件弹窗会保持空列表，因为 `/humanoid/programs/control` 请求没有服务端响应。

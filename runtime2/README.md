# runtime2 中文用户层

`runtime2` 是面向用户自定义程序的 G2 MQTT 客户端。它不直接加载 GDK，所有操作通过 `serivces2` 约定的 MQTT request/response/done 主题完成。

## 安全机制

用户层本身不弹出运动确认，便于自定义程序自动执行。运动命令发布后，方法会等待带相同 `time`、`cmd` 和模块 `type` 的 `/humanoid/done/` 完成报文；数据库中保存的关节/位姿运动等待阻塞执行后的 `/humanoid/db/response/`。

`test/runtime2/` 中的脚本不会弹出确认提示，启动后会直接执行对应接口。运行涉及本体运动的脚本前，操作者应自行确认机器人周围安全、急停可用。

## 使用

从项目根目录运行：

```bash
python3 runtime2/programs/demo.py
```

示例：

```python
from runtime2 import G2

with G2() as 机器人:
    机器人.底盘相对运动(前后=100, 左右=0, 转角=0)
    机器人.夹爪(左夹爪=1.0, 右夹爪=1.0)
    机器人.语音输出("动作完成")
```

单位遵循 `serivces2`：底盘位移为毫米、转角为度、线速度为米/秒、角速度为度/秒；关节目标角度遵循 GDK，使用弧度；末端偏移位置使用米、旋转使用度。

## 中文 API

- `底盘相对运动(前后=0, 左右=0, 转角=0)`，未传入的分量不运动
- `底盘地图点运动(点位序号)`
- `底盘相对运动带速度(前后, 左右, 转角, 线速度, 角速度)`
- `夹爪(左夹爪=None, 右夹爪=None)`，位置范围 `0.0~1.0`
- `末端偏移量(左偏移量=None, 右偏移量=None)`
- `全身关节运动(关节变量, 角速度=None)`
- `左手关节运动(左手关节变量, 角速度=None)`
- `右手关节运动(右手关节变量, 角速度=None)`
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

## 用户程序管理与单步调试

启动独立的程序管理服务：

```bash
cd /data/wxf/mbu0917
python3 runtime2/run.py
```

服务订阅 `/humanoid/programs/control`，支持 `read_files`、`copy`、`codes`、`run`、`debug`、`next` 和 `stop` 命令。它通过以下主题返回结果：

- `/humanoid/programs/files`：`programs/` 下的 `.py` 文件列表
- `/humanoid/programs/codes`：当前 `main.py` 源码
- `/humanoid/programs/step`：trace 当前行号和源码
- `/humanoid/programs/status`：复制、运行、完成、停止或错误状态

`copy` 只接受 `programs/` 目录中的单个 `.py` 文件名，并以原子替换方式覆盖 `runtime2/main.py`。`debug` 只跟踪该 `main.py`，每遇到一行便等待 `next`；`stop` 可结束等待中的调试。

安全的调试示例位于 `runtime2/programs/debug_demo.py`。网页独立测试页为：

```text
http://10.42.1.101:8003/tests/runtime-debug.html
```

页面默认使用模拟 MQTT，不会执行程序；添加 `?live=1` 才会连接真实 MQTT。

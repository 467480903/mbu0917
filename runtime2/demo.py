#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime2 import G2


with G2() as 机器人:
    机器人.语音输出("runtime2 已启动")
    # 真实运动前必须由现场人员确认环境安全，再取消下一行注释。
    # 机器人.底盘相对运动(前后=100, 左右=0, 转角=0)
    print(1234)
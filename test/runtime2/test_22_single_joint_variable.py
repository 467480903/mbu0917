#!/usr/bin/env python3
"""使用数据库中的单关节变量执行运动。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2


with G2() as 机器人:
    机器人.单关节变量运动("S1", 角速度=0.10)

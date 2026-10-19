#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2

with G2() as 机器人:
    机器人.底盘相对运动(前后=100, 左右=0, 转角=0)
    机器人.底盘相对运动(前后=100, 左右=0, 转角=0)
    机器人.底盘相对运动(前后=100, 左右=0, 转角=0)

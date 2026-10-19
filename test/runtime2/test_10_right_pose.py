#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2

with G2() as 机器人:
    机器人.右手坐标姿态运动(右手坐标姿态变量="right_pose_name", 末端线速度=0.1, 末端角速度=5)

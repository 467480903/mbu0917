#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2

with G2() as 机器人:
    机器人.单关节运动(关节名称="idx11_head_joint1", 目标角度=0.1, 角速度=0.2)

#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2


with G2() as 机器人:
    机器人.单关节相对运动(
        关节名称="idx11_head_joint1",
        递增量=0.05,
        角速度=0.1,
    )

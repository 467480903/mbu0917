#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2

with G2() as 机器人:
    机器人.末端偏移量(左偏移量={"position": [0.01, 0, 0], "rotation": [0, 0, 0]})
    print(1111111)

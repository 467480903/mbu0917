#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2


with G2() as 机器人:
    关节角 = 机器人.读取当前全身所有关节角()
    if not isinstance(关节角, dict) or not 关节角:
        raise RuntimeError("未读取到关节角")
    print(json.dumps(关节角, ensure_ascii=False, indent=2))

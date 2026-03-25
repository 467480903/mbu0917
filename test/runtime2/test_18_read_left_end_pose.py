#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2


with G2() as 机器人:
    左手姿态 = 机器人.读取当前左手末端坐标姿态()
    if len(左手姿态.get("position", [])) != 3 or len(左手姿态.get("orientation", [])) != 4:
        raise RuntimeError(f"左手末端坐标姿态格式错误: {左手姿态}")
    print(json.dumps(左手姿态, ensure_ascii=False, indent=2))

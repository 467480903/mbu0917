#!/usr/bin/env python3
"""独立测试附图围栏横线识别，输出图片到项目 image/llm；不控制机器人。"""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "service2"))
from llm_controller import LlmController

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=str(ROOT / "image/CAMERA1/1793869745755.png"))
    args = parser.parse_args()
    result = LlmController(ROOT).detect_file(args.image, "fence")
    print(json.dumps({k: v for k, v in result.items() if k != "image"}, ensure_ascii=False, indent=2))

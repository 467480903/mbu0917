#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime2 import G2


with G2() as 机器人:
    图片路径 = 机器人.头部全局相机拍照()
    if not 图片路径 or not Path(图片路径).is_file():
        raise RuntimeError(f"照片文件不存在: {图片路径}")
    print(f"照片已保存: {图片路径}")

"""通过 Minth.G2 保存头部彩色与深度相机图片。

服务端会保存 ``kHeadColor`` 和 ``kHeadDepth`` 的当前图像至项目
``images/`` 目录。本脚本会访问真实相机，仅应在现场允许拍照时执行。
"""

from pathlib import Path
import sys

# 允许从任意工作目录直接运行本测试文件。
RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from minth import Minth


G2 = Minth.G2()
try:
    # 向相机服务发送：
    # {"command": "save_photo", "cameras": ["kHeadColor", "kHeadDepth"]}
    completed = G2.SAVE_PHOTO(["kHeadColor", "kHeadDepth"])
    if not completed:
        raise RuntimeError("相机拍照保存未在超时时间内完成")
finally:
    G2.close()

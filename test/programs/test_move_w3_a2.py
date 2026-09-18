"""Minth.G2 运动与全身动作组合测试。

执行顺序：
1. 同步前进 1 米；
2. 同步执行全身动作 W3；
3. 下发后退 1 米（不等待完成），同时开始全身动作 A2。

仅在现场已确认急停可用、前后 1 米范围无人无障碍物，且底盘与
全身动作并行执行安全时运行。
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
    # 1. 前进 1 米，等待到位处理完成。
    # G2.REL_NOWAIT({"x": 1.0, "y": 0.0, "yaw_rad": 0.0})

    # 2. 通过一条全身关节命令以速度 0.5 运动到 W3。
    G2.WBC("W3", speed=0.5)

    # 3. 直接下发后退 1 米；不等待底盘完成，立即以速度 0.5 下发全身姿态 A3。
    # G2.REL_NOWAIT({"x": -1.0, "y": 0.0, "yaw_rad": 0.0})
    G2.WBC("A3", speed=0.5)
finally:
    G2.close()

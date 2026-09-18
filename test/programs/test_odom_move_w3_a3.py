"""里程计底盘运动与 WBC 姿态序列现场测试。

执行顺序：
1. 基于里程计前进 1 米；
2. WBC 到 W3；
3. WBC 到 A3；
4. 基于里程计后退 1 米；
5. WBC 到 W3；
6. WBC 到 A3。

运行前确认急停可用、前后各 1 米范围无人无障碍物，且 W3/A3
姿态动作安全。本脚本会驱动真实机器人，只能在现场安全条件满足时执行。
"""

from pathlib import Path
import sys

# 允许从任意工作目录直接运行本测试文件。
RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from minth import Minth


ODOM_SPEED = 0.25  # m/s
WBC_SPEED = 0.5

G2 = Minth.G2()
try:
    # 1. 基于里程计前进 1 米。
    G2.REL_ODOM({"x": 1.0, "y": 0.0, "yaw_rad": 0.0}, speed=ODOM_SPEED)

    # 2-3. 全身姿态：W3 → A3。
    G2.WBC("W3", speed=WBC_SPEED)
    G2.WBC("A3", speed=WBC_SPEED)

    # 4. 基于里程计后退 1 米。
    G2.REL_ODOM({"x": -1.0, "y": 0.0, "yaw_rad": 0.0}, speed=ODOM_SPEED)

    # 5-6. 再次执行全身姿态：W3 → A3。
    G2.WBC("W3", speed=WBC_SPEED)
    G2.WBC("A3", speed=WBC_SPEED)
finally:
    G2.close()

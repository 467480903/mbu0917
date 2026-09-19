from pathlib import Path
import sys
import time

# 允许从任意工作目录直接运行本测试文件。
RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from minth import Minth


G2 = Minth.G2()

G2.REL({"rotate": -175/3.1415926})
time.sleep(2)
G2.REL({"x":-0.1})
G2.GO(1)
G2.WBC("PP_STANDBY")
G2.WBC("PP_PRE_PLACE1")
G2.WBC("PP_PRE_PLACE_LIFT")
G2.WBC("PP_PLACE")
G2.GRIPPER({"right":-0.76})
G2.OFFSET({"rz":-30})
time.sleep(2)
G2.OFFSET({"rx":-100})
G2.WBC("PP_STANDBY")
G2.REL({"x":-0.7})


G2.setData("is_place_done",1)
time.sleep(2)
G2.setData("is_place_done",0)
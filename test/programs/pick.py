from pathlib import Path
import sys
import time

# 允许从任意工作目录直接运行本测试文件。
RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from minth import Minth


G2 = Minth.G2()


G2.GO(3)
G2.REL({"x":-0.1})
G2.GO(3)
G2.GRIPPER({"right":-0.76})
G2.WBC("PP_STANDBY")
G2.WBC("PP_PRE_PICK")
G2.WBC("PP_PICK")
G2.OFFSET({"rz":5})
time.sleep(0.1)
G2.OFFSET({"rz":5})
time.sleep(0.1)
G2.OFFSET({"rz":5})
time.sleep(0.1)
G2.OFFSET({"rz":5})
G2.GRIPPER({"right":-0.0})
time.sleep(0.1)
G2.OFFSET({"rz":5})
time.sleep(0.1)
G2.OFFSET({"rz":5})
time.sleep(0.1)



G2.WBC("PP_LIFT")
G2.REL({"x":-0.3})
G2.WBC("PP_STANDBY")


G2.setData("is_pick_done",1)
time.sleep(2)
G2.setData("is_pick_done",0)
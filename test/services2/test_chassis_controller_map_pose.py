#!/usr/bin/env python3
import sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
import agibot_gdk
from chassis_controller import ChassisController

assert agibot_gdk.gdk_init() == agibot_gdk.GDKRes.kSuccess
try:
    pose = ChassisController(agibot_gdk, None, "", "").get_current_map_pose()
    assert len(pose["position"]) == 3 and len(pose["orientation"]) == 4
    print(pose)
finally:
    agibot_gdk.gdk_release()

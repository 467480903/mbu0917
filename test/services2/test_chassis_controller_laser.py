#!/usr/bin/env python3
import sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
import agibot_gdk
from chassis_controller import ChassisController

assert agibot_gdk.gdk_init() == agibot_gdk.GDKRes.kSuccess
try:
    data = ChassisController(agibot_gdk, None, "", "").get_laser_points()
    assert data["count"] == len(data["points"])
    print(data["count"], data["front"], data["back"])
finally:
    agibot_gdk.gdk_release()

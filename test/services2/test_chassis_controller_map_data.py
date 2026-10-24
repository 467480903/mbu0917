#!/usr/bin/env python3
import sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
import agibot_gdk
from chassis_controller import ChassisController

assert agibot_gdk.gdk_init() == agibot_gdk.GDKRes.kSuccess
try:
    data = ChassisController(agibot_gdk, None, "", "").get_map_data()
    assert data["width"] > 0 and data["height"] > 0 and data["data_b64"]
    print(data["id"], data["name"], data["width"], data["height"])
finally:
    agibot_gdk.gdk_release()

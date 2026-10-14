#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "serivces2")
import agibot_gdk
from chassis_controller import ChassisController

if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
    raise RuntimeError("GDK 初始化失败")
try:
    controller = ChassisController(agibot_gdk, None, "", "")
    points = controller.get_map_points()
    print(json.dumps(points, ensure_ascii=False, indent=2))
finally:
    agibot_gdk.gdk_release()

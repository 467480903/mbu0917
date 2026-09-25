#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置加载 + 数据表初始化测试（读取 datas/ 真实配置，不连接设备）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from sync_controller import SyncController

config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../datas'))
c = SyncController(None, "/humanoid/sync/response/", config_dir)
c.load_config()
assert len(c._devices) == 2          # modbus(nodered) + s7(s1200)
assert len(c._data) == 19            # 9 个 read + 10 个 write 点位

snap = {i["name"]: i for i in c.snapshot()}
assert snap["m1"]["type"] == "read" and snap["m1"]["isChanged"] == 0
assert snap["m5"]["type"] == "read"
assert snap["m1_"]["type"] == "write" and snap["m1_"]["value"] == 0 and snap["m1_"]["isChanged"] == 1
assert snap["m6_"]["type"] == "write"
assert snap["heart_beat_plc"]["type"] == "read" and snap["heart_beat_plc"]["isChanged"] == 0
assert snap["ES"]["type"] == "read"
assert snap["heart_beat_g2"]["type"] == "write" and snap["heart_beat_g2"]["isChanged"] == 1
assert snap["is_place_done"]["type"] == "write"
print("配置加载 + 数据表初始化测试通过")

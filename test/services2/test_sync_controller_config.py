#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置加载 + 数据表初始化测试（不涉及网络/设备，可直接运行）"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from sync_controller import SyncController

tmp = tempfile.mkdtemp()
with open(os.path.join(tmp, "modbus.json"), "w") as f:
    json.dump([{"name": "n", "ip": "127.0.0.1", "port": 10502, "rate": 50,
                "read": {"holdings": [0, 1], "names": ["m1", "m2"]},
                "write": {"holdings": [10], "names": ["m1_"], "values": [112]}}], f)
with open(os.path.join(tmp, "s7.json"), "w") as f:
    json.dump([{"name": "s", "ip": "10.0.0.1", "rate": 100,
                "read": [{"name": "hb", "addr": "DB300.DBX0.0", "type": "bool"}],
                "write": [{"name": "hb_g2", "addr": "DB300.DBX0.1", "type": "bool"}]}], f)

c = SyncController(None, "/humanoid/sync/response/", tmp)
c.load_config()
assert len(c._devices) == 2
assert len(c._data) == 5
snap = {i["name"]: i for i in c.snapshot()}
assert snap["m1"]["type"] == "read" and snap["m1"]["isChanged"] == 0
assert snap["m1_"]["type"] == "write" and snap["m1_"]["value"] == 112 and snap["m1_"]["isChanged"] == 1
assert snap["hb"]["type"] == "read"
assert snap["hb_g2"]["type"] == "write" and snap["hb_g2"]["isChanged"] == 1
print("配置加载 + 数据表初始化测试通过")

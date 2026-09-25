#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据表读写测试（不涉及网络/MQTT，可直接运行）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from sync_controller import SyncController

c = SyncController(None, "/humanoid/sync/response/", "/tmp")
c._data_add("m1", "read", 0)
c._data_add("m2", "write", 112)

assert c._update_read("m1", 111) is True
assert c.read_data("m1") == 111
assert c.set_data("m2", 5) is True
assert c.set_data("m1", 9) is False          # read 点位不可写
assert len(c._pending_writes()) == 1
assert c._mark_written("m2") is True
assert c._pending_writes() == []
assert {i["name"]: i for i in c.snapshot()}["m2"]["isChanged"] == 0
print("数据表读写测试通过")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S7 地址解析 + 地址分组测试（纯函数，可直接运行）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from sync_controller import SyncController

assert SyncController.parse_s7_addr("DB1.DBW0") == (1, 0, 2, None)
assert SyncController.parse_s7_addr("DB12.DBD4") == (12, 4, 4, None)
assert SyncController.parse_s7_addr("DB1.DBB10") == (1, 10, 1, None)
assert SyncController.parse_s7_addr("DB8.DBX2.1") == (8, 2, 1, 1)
assert SyncController._group_continuous([0, 1, 2, 5, 6]) == [(0, 3), (5, 2)]
assert SyncController._group_continuous([]) == []
print("S7 地址解析 + 地址分组测试通过")

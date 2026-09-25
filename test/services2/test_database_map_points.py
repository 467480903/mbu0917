#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地图点位 增/删/改/读取所有 自动化测试（不涉及运动，可直接运行）"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from database_controller import DatabaseController

db = DatabaseController(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init()

assert db.add_map_point("b_point", [1.0, 2.0, 0.0], [0, 0, 0, 1]) is True
assert db.add_map_point("a_point", [3.0, 4.0, 0.0], [0, 0, 0, 1]) is True
assert db.add_map_point("b_point", [0, 0, 0], [0, 0, 0, 1]) is False  # 重复增失败
assert [p["name"] for p in db.get_map_points()] == ["a_point", "b_point"]  # 按名排序

assert db.update_map_point("b_point", [9.0, 8.0, 0.0], [0, 0, 0, 1]) is True
assert db.update_map_point("none", [0, 0, 0], [0, 0, 0, 1]) is False  # 改不存在失败
assert db.get_map_points()[1]["position"][0] == 9.0

assert db.delete_map_point("a_point") is True
assert db.delete_map_point("none") is False                        # 删不存在失败
assert [p["name"] for p in db.get_map_points()] == ["b_point"]
print("地图点位 增删改读取 测试通过")

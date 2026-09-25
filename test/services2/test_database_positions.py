#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""坐标姿态 增/删/改/读取所有 自动化测试（不涉及运动，可直接运行）"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from database_controller import DatabaseController

db = DatabaseController(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init()

assert db.add_positions("left", "b_pose", {"x": 0.5, "y": 0.2, "z": 0.3}) is True
assert db.add_positions("left", "a_pose", {"x": 0.1, "y": 0.2, "z": 0.3}) is True
assert db.add_positions("left", "b_pose", {}) is False             # 重复增失败
assert [p["name"] for p in db.get_positions()] == ["a_pose", "b_pose"]  # 按名排序

assert db.update_positions("left", "b_pose", {"x": 0.9, "y": 0.2, "z": 0.3}) is True
assert db.update_positions("left", "none", {}) is False            # 改不存在失败
assert db.get_positions()[1]["value"]["x"] == 0.9

assert db.delete_positions("left", "a_pose") is True
assert db.delete_positions("left", "none") is False                # 删不存在失败
assert [p["name"] for p in db.get_positions()] == ["b_pose"]
print("坐标姿态 增删改读取 测试通过")

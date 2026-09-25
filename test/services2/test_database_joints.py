#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关节角 增/删/改/读取所有 自动化测试（不涉及运动，可直接运行）"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from database_controller import DatabaseController

db = DatabaseController(os.path.join(tempfile.mkdtemp(), "t.db"))
db.init()

assert db.add_joints("head", "b_joint", {"idx11_head_joint1": 0.1}) is True
assert db.add_joints("head", "a_joint", {"idx11_head_joint1": 0.2}) is True
assert db.add_joints("head", "b_joint", {}) is False              # 重复增失败
assert [j["name"] for j in db.get_joints()] == ["a_joint", "b_joint"]  # 按名排序

assert db.update_joints("head", "b_joint", {"idx11_head_joint1": 0.9}) is True
assert db.update_joints("head", "none", {}) is False               # 改不存在失败
assert db.get_joints()[1]["value"]["idx11_head_joint1"] == 0.9

assert db.delete_joints("head", "a_joint") is True
assert db.delete_joints("head", "none") is False                   # 删不存在失败
assert [j["name"] for j in db.get_joints()] == ["b_joint"]
print("关节角 增删改读取 测试通过")

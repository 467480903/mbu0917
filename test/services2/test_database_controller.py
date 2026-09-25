#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_database_controller.py - 数据库控制器测试

测试 DatabaseController 的 CRUD 操作

不涉及机器人运动，可直接运行
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '../../datas/robot_data.db')

from database_controller import DatabaseController

# 初始化数据库
db = DatabaseController(DB_PATH)
db.init()

# 测试关节保存
db.save_joints("head", "test_pose", {"idx11_head_joint1": 0.1, "idx12_head_joint2": 0.2, "idx13_head_joint3": 0.3})

# 测试关节查询
joints = db.get_joints("head")
print(f"关节数据: {joints}")

# 测试位姿保存
db.save_positions("left", "test_pos", {"x": 0.5, "y": 0.2, "z": 0.3})

# 测试位姿查询
positions = db.get_positions("left")
print(f"位姿数据: {positions}")

# 测试地图点位
db.save_map_point("test_point", [1.0, 2.0, 0.0], [0, 0, 0, 1])
point = db.get_map_point("test_point")
print(f"地图点位: {point}")

print("测试完成！")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四类关节变量的增删改查与旧表迁移测试；不执行机器人运动。"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../service2"))

from database_controller import DatabaseController


def values(keys, start=0.0):
    return {key: start + index * 0.01 for index, key in enumerate(keys)}


db_dir = tempfile.mkdtemp()
db_path = os.path.join(db_dir, "joint_types.db")

# 模拟旧版 joints 表，验证启动时自动增加 joint_name 字段。
conn = sqlite3.connect(db_path)
conn.execute(
    """CREATE TABLE joints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,
        name TEXT NOT NULL,
        value TEXT NOT NULL,
        UNIQUE(type, name)
    )"""
)
conn.commit()
conn.close()

db = DatabaseController(db_path)
db.init()

columns = {
    row[1] for row in sqlite3.connect(db_path).execute("PRAGMA table_info(joints)")
}
assert "joint_name" in columns

whole_body = values(DatabaseController.WHOLE_BODY_JOINT_KEYS)
left_arm = values(DatabaseController.LEFT_ARM_JOINT_KEYS, 0.1)
right_arm = values(DatabaseController.RIGHT_ARM_JOINT_KEYS, 0.2)
single_name = DatabaseController.HEAD_JOINT_KEYS[0]

assert db.add_joints("whole_body", "全身待机", whole_body) is True
assert db.add_joints("left_arm", "左手取料", left_arm) is True
assert db.add_joints("right_arm", "右手放料", right_arm) is True
assert db.add_joints(
    "single_joint", "头部单轴", {single_name: 0.3}, single_name
) is True
assert db.add_joints(
    "single_joint", "头部单轴", {single_name: 0.3}, single_name
) is False

items = {item["name"]: item for item in db.get_joints()}
assert set(items) == {"全身待机", "左手取料", "右手放料", "头部单轴"}
assert items["全身待机"]["type"] == "whole_body"
assert len(items["全身待机"]["value"]) == 22
assert len(items["左手取料"]["value"]) == 7
assert len(items["右手放料"]["value"]) == 7
assert items["头部单轴"]["joint_name"] == single_name
assert items["头部单轴"]["value"] == {single_name: 0.3}

assert db.update_joints(
    "single_joint", "头部单轴", {single_name: 0.6}, single_name
) is True
items = {item["name"]: item for item in db.get_joints()}
assert items["头部单轴"]["value"][single_name] == 0.6

try:
    db.add_joints("left_arm", "数据不完整", {single_name: 0.1})
except ValueError as error:
    assert "缺少关节" in str(error)
else:
    raise AssertionError("缺失关节的数据应被拒绝")

assert db.delete_joints("right_arm", "右手放料") is True
assert db.delete_joints("right_arm", "不存在") is False
assert [item["name"] for item in db.get_joints()] == ["全身待机", "头部单轴", "左手取料"]

print("四类关节变量与数据库迁移测试通过")

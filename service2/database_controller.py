#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database_controller.py — 数据库控制器

职责（参考 agents.md「数据库控制器」）：
  - 操作 sqlite 数据库，读写三类数据：关节角 / 坐标姿态 / 地图点位
  - 每类数据实现：增(add) 删(delete) 改(update) 读取所有(get_all) 运动到位置(move)
  - 不提供「查询」功能；数据一律按「名称」做字符排序
  - 引用 关节/位姿/底盘 三个控制器，用于「运动到位置」
  - 不涉及机器人本体运动（运动委托给上述三个控制器），使用默认系统 python

注意：
  - 关节/位姿/底盘 控制器不得反向引用本控制器。
  - 「运动到位置」涉及机器人运动，禁止编写自动化测试。
"""

import os
import json
import math
import sqlite3
import threading


class DatabaseController:
    """数据库控制器：关节角 / 坐标姿态 / 地图点位"""

    JOINT_TYPE_ALIASES = {
        "WBC": "whole_body",
        "wbc": "whole_body",
        "whole_body": "whole_body",
        "left": "left_arm",
        "left_arm": "left_arm",
        "right": "right_arm",
        "right_arm": "right_arm",
        "joint": "single_joint",
        "single_joint": "single_joint",
    }
    WAIST_JOINT_KEYS = [
        "idx01_body_joint1", "idx02_body_joint2", "idx03_body_joint3",
        "idx04_body_joint4", "idx05_body_joint5",
    ]
    HEAD_JOINT_KEYS = [
        "idx11_head_joint1", "idx12_head_joint2", "idx13_head_joint3",
    ]
    LEFT_ARM_JOINT_KEYS = [
        "idx21_arm_l_joint1", "idx22_arm_l_joint2", "idx23_arm_l_joint3",
        "idx24_arm_l_joint4", "idx25_arm_l_joint5", "idx26_arm_l_joint6",
        "idx27_arm_l_joint7",
    ]
    RIGHT_ARM_JOINT_KEYS = [
        "idx61_arm_r_joint1", "idx62_arm_r_joint2", "idx63_arm_r_joint3",
        "idx64_arm_r_joint4", "idx65_arm_r_joint5", "idx66_arm_r_joint6",
        "idx67_arm_r_joint7",
    ]
    WHOLE_BODY_JOINT_KEYS = (
        WAIST_JOINT_KEYS + HEAD_JOINT_KEYS
        + LEFT_ARM_JOINT_KEYS + RIGHT_ARM_JOINT_KEYS
    )

    def __init__(self, db_path, joint_controller=None,
                 pose_controller=None, chassis_controller=None):
        self.db_path = db_path
        self.joint_controller = joint_controller
        self.pose_controller = pose_controller
        self.chassis_controller = chassis_controller
        self._mem_conn = None
        self._file_conn = None
        self._lock = threading.Lock()

    # ── 初始化 ──────────────────────────────────────────────
    def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
        if os.path.exists(self.db_path):
            self._file_conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._file_conn.backup(self._mem_conn)
            print(f"[DB] 已从文件加载: {self.db_path}")
        else:
            self._create_tables()
            self._file_conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._mem_conn.backup(self._file_conn)
            print(f"[DB] 已创建新数据库: {self.db_path}")
        self._create_tables()
        self._migrate_joints_schema()
        self._normalize_existing_positions()
        print("[DB] 初始化完成")

    def _create_tables(self):
        cur = self._mem_conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS joints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, name TEXT NOT NULL,
            joint_name TEXT,
            value TEXT NOT NULL, UNIQUE(type, name))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, name TEXT NOT NULL,
            value TEXT NOT NULL, UNIQUE(type, name))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS map_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'local',
            position TEXT NOT NULL DEFAULT '[]',
            orientation TEXT NOT NULL DEFAULT '[0,0,0,1]')""")
        self._mem_conn.commit()

    def _migrate_joints_schema(self):
        """增加单轴字段，并统一仍在使用的历史关节类型名称。"""
        cur = self._mem_conn.cursor()
        columns = {row[1] for row in cur.execute("PRAGMA table_info(joints)")}
        changed = False
        if "joint_name" not in columns:
            cur.execute("ALTER TABLE joints ADD COLUMN joint_name TEXT")
            changed = True

        aliases = {
            "WBC": "whole_body", "wbc": "whole_body",
            "left": "left_arm", "right": "right_arm",
            "joint": "single_joint",
        }
        for old_type, new_type in aliases.items():
            cur.execute("UPDATE joints SET type=? WHERE type=?", (new_type, old_type))
            changed = changed or cur.rowcount > 0

        cur.execute("SELECT id,value FROM joints WHERE type='single_joint' AND joint_name IS NULL")
        for row_id, raw_value in cur.fetchall():
            try:
                value = json.loads(raw_value)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and len(value) == 1:
                cur.execute(
                    "UPDATE joints SET joint_name=? WHERE id=?",
                    (next(iter(value)), row_id),
                )
                changed = True

        if changed:
            self._mem_conn.commit()
            self._sync_to_file()
            print("[DB] 已迁移关节变量类型并增加 joint_name 字段")

    def _sync_to_file(self):
        self._mem_conn.backup(self._file_conn)

    @staticmethod
    def _normalize_position_value(value):
        """将末端姿态统一为 x/y/z/rx/ry/rz 六字段格式。"""
        if not isinstance(value, dict):
            raise ValueError("坐标姿态必须是 JSON 对象")

        if "left" in value or "right" in value:
            if not isinstance(value.get("left"), dict) or not isinstance(value.get("right"), dict):
                raise ValueError("双臂坐标姿态必须同时包含 left/right")
            return {
                "left": DatabaseController._normalize_position_value(value["left"]),
                "right": DatabaseController._normalize_position_value(value["right"]),
            }

        position = value.get("position")
        if position is not None:
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                raise ValueError("position 必须包含 3 个分量")
            x, y, z = position
        else:
            x, y, z = (value.get(key, 0.0) for key in ("x", "y", "z"))

        orientation = value.get("orientation")
        if orientation is not None:
            if not isinstance(orientation, (list, tuple)) or len(orientation) != 4:
                raise ValueError("orientation 必须包含 4 个四元数分量")
            qx, qy, qz, qw = (float(component) for component in orientation)
            norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
            if not math.isfinite(norm) or norm == 0.0:
                raise ValueError("orientation 四元数无效")
            qx, qy, qz, qw = (component / norm for component in (qx, qy, qz, qw))
            if qw < 0.0:
                qx, qy, qz = -qx, -qy, -qz
            rx, ry, rz = qx, qy, qz
        else:
            rx, ry, rz = (value.get(key, 0.0) for key in ("rx", "ry", "rz"))

        result = {
            "x": float(x), "y": float(y), "z": float(z),
            "rx": float(rx), "ry": float(ry), "rz": float(rz),
        }
        if not all(math.isfinite(component) for component in result.values()):
            raise ValueError("坐标姿态包含非有限数值")
        return result

    def _normalize_existing_positions(self):
        """迁移历史姿态记录，并同步到磁盘数据库。"""
        cur = self._mem_conn.cursor()
        cur.execute("SELECT id,name,value FROM positions")
        updated = 0
        for row_id, name, raw_value in cur.fetchall():
            try:
                normalized = self._normalize_position_value(json.loads(raw_value))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                print(f"[DB] 跳过无法规范化的位姿 {name}: {exc}")
                continue
            normalized_json = json.dumps(normalized, ensure_ascii=False)
            if json.loads(raw_value) != normalized:
                cur.execute("UPDATE positions SET value=? WHERE id=?", (normalized_json, row_id))
                updated += 1
        if updated:
            self._mem_conn.commit()
            self._sync_to_file()
            print(f"[DB] 已统一 {updated} 条位姿记录为 x/y/z/rx/ry/rz")

    # ── 内部查找（非公开查询）──────────────────────────────
    def _find_joints_by_name(self, name):
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute(
                "SELECT type,name,joint_name,value FROM joints WHERE name=? ORDER BY name LIMIT 1",
                (name,),
            )
            row = cur.fetchone()
        return ({"type": row[0], "name": row[1], "joint_name": row[2],
                 "value": json.loads(row[3])} if row else None)

    def _find_positions_by_name(self, name):
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT type,name,value FROM positions WHERE name=? ORDER BY name LIMIT 1", (name,))
            row = cur.fetchone()
        return {"type": row[0], "name": row[1], "value": json.loads(row[2])} if row else None

    def _find_map_point(self, name):
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT name,source,position,orientation FROM map_points WHERE name=?", (name,))
            row = cur.fetchone()
        if not row:
            return None
        return {"name": row[0], "source": row[1],
                "position": json.loads(row[2]), "orientation": json.loads(row[3])}

    @staticmethod
    def _joint_list(value, keys):
        return [value.get(k, 0.0) for k in keys]

    @staticmethod
    def _recover_quat(data):
        qx = data.get("rx", 0)
        qy = data.get("ry", 0)
        qz = data.get("rz", 0)
        qw = math.sqrt(max(0.0, 1.0 - qx * qx - qy * qy - qz * qz))
        return [qx, qy, qz, qw]

    # ═══════════════════════════════════════════════════════
    #  关节角
    # ═══════════════════════════════════════════════════════
    @classmethod
    def _canonical_joint_type(cls, jtype):
        canonical = cls.JOINT_TYPE_ALIASES.get(str(jtype))
        if canonical is None:
            raise ValueError(f"不支持的关节变量类型: {jtype}")
        return canonical

    @classmethod
    def _joint_keys_for_type(cls, jtype):
        return {
            "whole_body": cls.WHOLE_BODY_JOINT_KEYS,
            "left_arm": cls.LEFT_ARM_JOINT_KEYS,
            "right_arm": cls.RIGHT_ARM_JOINT_KEYS,
        }.get(jtype)

    @classmethod
    def _normalize_joint_value(cls, jtype, value, joint_name=None):
        canonical_type = cls._canonical_joint_type(jtype)
        if not isinstance(value, dict):
            raise ValueError("关节变量值必须是关节名到弧度值的对象")

        if canonical_type == "single_joint":
            selected = joint_name
            if not selected and len(value) == 1:
                selected = next(iter(value))
            if selected not in cls.WHOLE_BODY_JOINT_KEYS:
                raise ValueError(f"单轴变量缺少有效的 joint_name: {selected}")
            if selected not in value:
                raise ValueError(f"单轴变量值中缺少关节: {selected}")
            return canonical_type, selected, {selected: float(value[selected])}

        keys = cls._joint_keys_for_type(canonical_type)
        missing = [key for key in keys if key not in value]
        if missing:
            raise ValueError(f"{canonical_type} 变量缺少关节: {missing}")
        return canonical_type, None, {key: float(value[key]) for key in keys}

    def add_joints(self, jtype, name, value, joint_name=None):
        """新增关节角（同类型同名已存在则失败）"""
        jtype, joint_name, value = self._normalize_joint_value(
            jtype, value, joint_name)
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT 1 FROM joints WHERE type=? AND name=?", (jtype, name))
            if cur.fetchone():
                return False
            cur.execute(
                "INSERT INTO joints(type,name,joint_name,value) VALUES(?,?,?,?)",
                (jtype, name, joint_name, json.dumps(value, ensure_ascii=False)),
            )
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 新增关节: {jtype}/{name}, joint_name={joint_name}")
        return True

    def update_joints(self, jtype, name, value, joint_name=None):
        """修改关节角（不存在则失败）"""
        jtype, joint_name, value = self._normalize_joint_value(
            jtype, value, joint_name)
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute(
                "UPDATE joints SET joint_name=?,value=? WHERE type=? AND name=?",
                (joint_name, json.dumps(value, ensure_ascii=False), jtype, name),
            )
            if cur.rowcount == 0:
                return False
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 修改关节: {jtype}/{name}")
        return True

    def delete_joints(self, jtype, name):
        """删除关节角"""
        jtype = self._canonical_joint_type(jtype)
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("DELETE FROM joints WHERE type=? AND name=?", (jtype, name))
            if cur.rowcount == 0:
                return False
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 删除关节: {jtype}/{name}")
        return True

    def get_joints(self):
        """读取所有关节角（按名称字符排序）"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT type,name,joint_name,value FROM joints ORDER BY name")
            rows = cur.fetchall()
        return [
            {"type": row[0], "name": row[1], "joint_name": row[2],
             "value": json.loads(row[3])}
            for row in rows
        ]

    def move_joints(self, name, agibot_gdk=None):
        """运动到存储的关节角（委托关节控制器）——禁止自动化测试"""
        item = self._find_joints_by_name(name)
        if item is None:
            print(f"[DB] 找不到关节: {name}")
            return False
        jc = self.joint_controller
        if jc is None:
            print("[DB] 未注入关节控制器")
            return False
        jtype, value = item["type"], item["value"]
        if jtype == "single_joint":
            joint_name = item.get("joint_name")
            return jc.move_single_joint(joint_name, value=value.get(joint_name))
        if jtype == "left_arm":
            return jc.move_left_arm(self._joint_list(value, jc.left_arm_joint_keys))
        if jtype == "right_arm":
            return jc.move_right_arm(self._joint_list(value, jc.right_arm_joint_keys))
        if jtype == "whole_body":
            return jc.move_wbc(value)
        print(f"[DB] 未知关节变量类型: {jtype}")
        return False

    # ═══════════════════════════════════════════════════════
    #  坐标姿态
    # ═══════════════════════════════════════════════════════
    def add_positions(self, ptype, name, value):
        """新增坐标姿态（同类型同名已存在则失败）"""
        normalized = self._normalize_position_value(value)
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT 1 FROM positions WHERE type=? AND name=?", (ptype, name))
            if cur.fetchone():
                return False
            cur.execute("INSERT INTO positions(type,name,value) VALUES(?,?,?)",
                        (ptype, name, json.dumps(normalized, ensure_ascii=False)))
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 新增位姿: {ptype}/{name}")
        return True

    def update_positions(self, ptype, name, value):
        """修改坐标姿态（不存在则失败）"""
        normalized = self._normalize_position_value(value)
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("UPDATE positions SET value=? WHERE type=? AND name=?",
                        (json.dumps(normalized, ensure_ascii=False), ptype, name))
            if cur.rowcount == 0:
                return False
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 修改位姿: {ptype}/{name}")
        return True

    def delete_positions(self, ptype, name):
        """删除坐标姿态"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("DELETE FROM positions WHERE type=? AND name=?", (ptype, name))
            if cur.rowcount == 0:
                return False
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 删除位姿: {ptype}/{name}")
        return True

    def get_positions(self):
        """读取所有坐标姿态（按名称字符排序）"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT type,name,value FROM positions ORDER BY name")
            rows = cur.fetchall()
        return [{"type": r[0], "name": r[1], "value": json.loads(r[2])} for r in rows]

    def move_position(self, name, agibot_gdk=None):
        """运动到存储的位姿（委托位姿控制器）——禁止自动化测试"""
        item = self._find_positions_by_name(name)
        if item is None:
            print(f"[DB] 找不到位姿: {name}")
            return False
        pc = self.pose_controller
        if pc is None:
            print("[DB] 未注入位姿控制器")
            return False
        ptype, value = item["type"], item["value"]
        if ptype == "left":
            pos = [value.get("x", 0), value.get("y", 0), value.get("z", 0)]
            return pc.move_left_arm(agibot_gdk, pos, self._recover_quat(value))
        if ptype == "right":
            pos = [value.get("x", 0), value.get("y", 0), value.get("z", 0)]
            return pc.move_right_arm(agibot_gdk, pos, self._recover_quat(value))
        if ptype == "both":
            left = value.get("left", {})
            right = value.get("right", {})
            left_target = {"position": [left.get("x", 0), left.get("y", 0), left.get("z", 0)],
                           "orientation": self._recover_quat(left)}
            right_target = {"position": [right.get("x", 0), right.get("y", 0), right.get("z", 0)],
                            "orientation": self._recover_quat(right)}
            return pc.move_both_arms(agibot_gdk, left_target, right_target)
        if ptype == "waist":
            return pc.move_waist(agibot_gdk, value)
        print(f"[DB] 未知位姿类型: {ptype}")
        return False

    # ═══════════════════════════════════════════════════════
    #  地图点位
    # ═══════════════════════════════════════════════════════
    def add_map_point(self, name, position, orientation, source="local"):
        """新增地图点位（同名已存在则失败）"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT 1 FROM map_points WHERE name=?", (name,))
            if cur.fetchone():
                return False
            cur.execute("INSERT INTO map_points(name,source,position,orientation) VALUES(?,?,?,?)",
                        (name, source,
                         json.dumps(position, ensure_ascii=False),
                         json.dumps(orientation, ensure_ascii=False)))
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 新增地图点位: {name}")
        return True

    def update_map_point(self, name, position, orientation, source=None):
        """修改地图点位（不存在则失败）"""
        with self._lock:
            cur = self._mem_conn.cursor()
            if source is None:
                cur.execute("UPDATE map_points SET position=?, orientation=? WHERE name=?",
                            (json.dumps(position, ensure_ascii=False),
                             json.dumps(orientation, ensure_ascii=False), name))
            else:
                cur.execute("UPDATE map_points SET position=?, orientation=?, source=? WHERE name=?",
                            (json.dumps(position, ensure_ascii=False),
                             json.dumps(orientation, ensure_ascii=False), source, name))
            if cur.rowcount == 0:
                return False
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 修改地图点位: {name}")
        return True

    def delete_map_point(self, name):
        """删除地图点位"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("DELETE FROM map_points WHERE name=?", (name,))
            if cur.rowcount == 0:
                return False
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 删除地图点位: {name}")
        return True

    def get_map_points(self):
        """读取所有地图点位（按名称字符排序）"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT name,source,position,orientation FROM map_points ORDER BY name")
            rows = cur.fetchall()
        return [{"name": r[0], "source": r[1],
                 "position": json.loads(r[2]), "orientation": json.loads(r[3])} for r in rows]

    def move_map_point(self, name, agibot_gdk=None):
        """运动到存储的地图点位（委托底盘控制器）——禁止自动化测试"""
        point = self._find_map_point(name)
        if point is None:
            print(f"[DB] 找不到地图点位: {name}")
            return False
        cc = self.chassis_controller
        if cc is None:
            print("[DB] 未注入底盘控制器")
            return False
        return cc.point_move(agibot_gdk, point)

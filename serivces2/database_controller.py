#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database_controller.py — 数据库控制器

职责：
  - 操作 sqlite 数据库
  - 读写关节角、坐标姿态、地图点位
  - 不涉及机器人运动，使用默认系统 python
"""

import os
import json
import sqlite3
import threading


class DatabaseController:
    """数据库控制器 - 操作 sqlite 数据库"""
    
    def __init__(self, db_path):
        """构造函数
        
        Parameters
        ----------
        db_path : str
            数据库文件路径
        """
        self.db_path = db_path
        self._mem_conn = None
        self._file_conn = None
        self._lock = threading.Lock()
    
    def init(self):
        """初始化数据库（从文件加载到内存）"""
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
        print("[DB] 初始化完成")
    
    def _create_tables(self):
        """创建表"""
        cur = self._mem_conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS joints (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                type  TEXT NOT NULL,
                name  TEXT NOT NULL,
                value TEXT NOT NULL,
                UNIQUE(type, name)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                type  TEXT NOT NULL,
                name  TEXT NOT NULL,
                value TEXT NOT NULL,
                UNIQUE(type, name)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS map_points (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                source       TEXT NOT NULL DEFAULT 'local',
                position     TEXT NOT NULL DEFAULT '[]',
                orientation  TEXT NOT NULL DEFAULT '[0,0,0,1]',
                UNIQUE(name, source)
            )
        """)
        self._mem_conn.commit()
    
    def _sync_to_file(self):
        """同步到文件"""
        self._mem_conn.backup(self._file_conn)
    
    # ═══════════════════════════════════════════════════════════
    #  关节数据 CRUD
    # ═══════════════════════════════════════════════════════════
    
    def get_joints(self, jtype=None):
        """查询关节数据"""
        with self._lock:
            cur = self._mem_conn.cursor()
            if jtype:
                cur.execute("SELECT type, name, value FROM joints WHERE type=? ORDER BY name", (jtype,))
            else:
                cur.execute("SELECT type, name, value FROM joints ORDER BY type, name")
            rows = cur.fetchall()
        return [{"type": r[0], "name": r[1], "value": json.loads(r[2])} for r in rows]
    
    def save_joints(self, jtype, name, value):
        """保存关节数据"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT 1 FROM joints WHERE type=? AND name=?", (jtype, name))
            exists = cur.fetchone() is not None
            if exists:
                cur.execute(
                    "UPDATE joints SET value=? WHERE type=? AND name=?",
                    (json.dumps(value, ensure_ascii=False), jtype, name)
                )
            else:
                cur.execute(
                    "INSERT INTO joints (type, name, value) VALUES (?, ?, ?)",
                    (jtype, name, json.dumps(value, ensure_ascii=False))
                )
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] {'更新' if exists else '新增'}关节: {jtype}/{name}")
    
    def delete_joints(self, jtype, name):
        """删除关节数据"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("DELETE FROM joints WHERE type=? AND name=?", (jtype, name))
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 删除关节: {jtype}/{name}")
    
    # ═══════════════════════════════════════════════════════════
    #  位姿数据 CRUD
    # ═══════════════════════════════════════════════════════════
    
    def get_positions(self, ptype=None):
        """查询位姿数据"""
        with self._lock:
            cur = self._mem_conn.cursor()
            if ptype:
                cur.execute("SELECT type, name, value FROM positions WHERE type=? ORDER BY name", (ptype,))
            else:
                cur.execute("SELECT type, name, value FROM positions ORDER BY type, name")
            rows = cur.fetchall()
        return [{"type": r[0], "name": r[1], "value": json.loads(r[2])} for r in rows]
    
    def save_positions(self, ptype, name, value):
        """保存位姿数据"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute(
                "INSERT INTO positions (type, name, value) VALUES (?, ?, ?) "
                "ON CONFLICT(type, name) DO UPDATE SET value=excluded.value",
                (ptype, name, json.dumps(value, ensure_ascii=False))
            )
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 保存位姿: {ptype}/{name}")
    
    def delete_positions(self, ptype, name):
        """删除位姿数据"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("DELETE FROM positions WHERE type=? AND name=?", (ptype, name))
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 删除位姿: {ptype}/{name}")
    
    # ═══════════════════════════════════════════════════════════
    #  地图点位 CRUD
    # ═══════════════════════════════════════════════════════════
    
    def get_map_points(self):
        """查询所有地图点位"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT name, source, position, orientation FROM map_points ORDER BY name")
            rows = cur.fetchall()
        return [{
            "name": r[0],
            "source": r[1],
            "position": json.loads(r[2]),
            "orientation": json.loads(r[3]),
        } for r in rows]
    
    def get_map_point(self, name):
        """查询单个地图点位"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT name, source, position, orientation FROM map_points WHERE name=?", (name,))
            row = cur.fetchone()
        if row:
            return {
                "name": row[0],
                "source": row[1],
                "position": json.loads(row[2]),
                "orientation": json.loads(row[3]),
            }
        return None
    
    def save_map_point(self, name, position, orientation, source="local"):
        """保存地图点位"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("SELECT 1 FROM map_points WHERE name=?", (name,))
            exists = cur.fetchone() is not None
            if exists:
                cur.execute(
                    "UPDATE map_points SET position=?, orientation=? WHERE name=?",
                    (json.dumps(position, ensure_ascii=False),
                     json.dumps(orientation, ensure_ascii=False), name)
                )
            else:
                cur.execute(
                    "INSERT INTO map_points (name, source, position, orientation) VALUES (?, ?, ?, ?)",
                    (name, source,
                     json.dumps(position, ensure_ascii=False),
                     json.dumps(orientation, ensure_ascii=False))
                )
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] {'更新' if exists else '新增'}地图点位: {name}")
    
    def delete_map_point(self, name):
        """删除地图点位"""
        with self._lock:
            cur = self._mem_conn.cursor()
            cur.execute("DELETE FROM map_points WHERE name=?", (name,))
            self._mem_conn.commit()
            self._sync_to_file()
        print(f"[DB] 删除地图点位: {name}")

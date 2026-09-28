#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status_publisher.py — 状态发布器

职责：
  - 纯粹的 publisher，往 MQTT 上持续发布机器人实时状态（默认 10Hz）：
      - 全身所有关节的当前转角
      - 左右手末端位姿（position + orientation）
      - 左右手夹爪当前开合程度
      - 底盘地图坐标（前提是底盘已初始化/重定位成功，否则为 null）

参考 services/status.py，但归整为一个类：所有变量、函数都包裹在类中，
没有 main / get_controller / handle_request，构造函数通过参数注入 GDK 对象与 MQTT 客户端。

报文格式（发布主题 /humanoid/status/data/）：
{
  "timestamp": "2026-09-28 12:00:00",
  "joints":   {"idx01_body_joint1": 0.123, ...},
  "left_ee":  {"position": [x, y, z], "orientation": [x, y, z, w]},
  "right_ee": {"position": [x, y, z], "orientation": [x, y, z, w]},
  "left_gripper":  0.5,
  "right_gripper": 0.5,
  "chassis": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0,
              "loc_state": 2, "loc_confidence": 0.95}
}
"""

import json
import math
import threading
import time


class StatusPublisher:
    """状态发布器 —— 纯粹的 publisher，往 MQTT 上发布实时状态"""

    def __init__(self, robot, slam, mqtt_client, topic_status, rate_hz=10.0):
        """构造函数

        Parameters
        ----------
        robot : agibot_gdk.Robot
            GDK Robot 对象（读取关节、末端位姿、夹爪）
        slam : agibot_gdk.Slam
            GDK Slam 对象（读取底盘地图坐标）
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_status : str
            状态发布主题
        rate_hz : float
            发布频率（Hz），默认 10Hz
        """
        self.robot = robot
        self.slam = slam
        self.mqtt_client = mqtt_client
        self.topic_status = topic_status
        self.rate_hz = rate_hz

        # 末端 link 名
        self.left_name = "arm_l_end_link"
        self.right_name = "arm_r_end_link"

        # 后台发布线程控制
        self._stop_event = threading.Event()
        self._thread = None

    # ── 状态读取（不嵌套，直接调用 GDK）────────────────────

    def read_joints(self):
        """读取全身所有关节的当前转角，返回 {关节名: 角度} 字典"""
        try:
            joint_states = self.robot.get_joint_states()
            joints = {}
            for state in joint_states["states"]:
                joints[state["name"]] = round(state["motor_position"], 6)
            return joints
        except Exception as e:
            print(f"[状态] 读取关节失败: {e}")
            return {}

    def _find_pose(self, status, name):
        """从 motion_control_status 中按名称查找末端位姿"""
        for i, frame_name in enumerate(status.frame_names):
            if frame_name == name:
                pose = status.frame_poses[i]
                return {
                    "position": [
                        round(pose.position.x, 6),
                        round(pose.position.y, 6),
                        round(pose.position.z, 6),
                    ],
                    "orientation": [
                        round(pose.orientation.x, 6),
                        round(pose.orientation.y, 6),
                        round(pose.orientation.z, 6),
                        round(pose.orientation.w, 6),
                    ],
                }
        return None

    def read_end_effector_poses(self):
        """读取左右手末端位姿，返回 (left, right)"""
        try:
            status = self.robot.get_motion_control_status()
            left = self._find_pose(status, self.left_name)
            right = self._find_pose(status, self.right_name)
            return left, right
        except Exception as e:
            print(f"[状态] 读取末端位姿失败: {e}")
            return None, None

    def read_gripper(self, side):
        """读取单侧夹爪当前开合程度，失败返回 None

        Parameters
        ----------
        side : str
            "left" 或 "right"
        """
        try:
            end_state = self.robot.get_end_state()
            states = (end_state.get(f"{side}_end_state") or {}).get("end_states") or []
            if not states:
                return None
            return round(float(states[0].get("position", 0.0)), 6)
        except Exception as e:
            print(f"[状态] 读取{side}夹爪失败: {e}")
            return None

    def read_grippers(self):
        """读取左右手夹爪开合程度，返回 (left, right)"""
        return self.read_gripper("left"), self.read_gripper("right")

    def read_chassis(self):
        """读取底盘地图坐标，未初始化/重定位失败时返回 None"""
        try:
            pose = self.slam.get_curr_pose()
            pos = pose.position
            ori = pose.orientation
            w, x, y, z = ori.w, ori.x, ori.y, ori.z
            yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

            loc_state = -1
            loc_confidence = 0.0
            try:
                odom = self.slam.get_odom_info()
                loc_state = odom.loc_state
                loc_confidence = round(odom.loc_confidence, 4)
            except Exception:
                pass

            return {
                "x": round(pos.x, 6),
                "y": round(pos.y, 6),
                "z": round(pos.z, 6),
                "yaw": round(yaw, 6),
                "loc_state": loc_state,
                "loc_confidence": loc_confidence,
            }
        except Exception as e:
            print(f"[状态] 读取底盘位姿失败: {e}")
            return None

    # ── 报文构建与发布 ─────────────────────────────────────

    def build_message(self):
        """构建一次状态报文"""
        left_ee, right_ee = self.read_end_effector_poses()
        left_gripper, right_gripper = self.read_grippers()
        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "joints": self.read_joints(),
            "left_ee": left_ee,
            "right_ee": right_ee,
            "left_gripper": left_gripper,
            "right_gripper": right_gripper,
            "chassis": self.read_chassis(),
        }

    def publish_once(self):
        """发布一次状态，返回本次报文"""
        msg = self.build_message()
        self.mqtt_client.publish(
            self.topic_status, json.dumps(msg, ensure_ascii=False), qos=0
        )
        return msg

    # ── 发布循环 ───────────────────────────────────────────

    def _run(self):
        """发布循环（后台线程）"""
        interval = 1.0 / self.rate_hz
        while not self._stop_event.is_set():
            try:
                self.publish_once()
            except Exception as e:
                print(f"[状态] 发布失败: {e}")
            self._stop_event.wait(interval)

    def start(self):
        """启动发布线程"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[状态] 发布线程已启动（{self.rate_hz}Hz）")

    def stop(self):
        """停止发布线程"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        print("[状态] 发布线程已停止")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""serivces2 的统一 MQTT 服务入口。"""

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import agibot_gdk
import paho.mqtt.client as mqtt

from apriltag_controller import ApriltagController
from camera_controller import CameraController
from chassis_controller import ChassisController
from database_controller import DatabaseController
from end_effector_controller import EndEffectorController
from interaction_controller import InteractionController
from joint_controller import JointController
from pose_controller import PoseController
from sync_controller import SyncController


class ServiceApplication:
    """初始化并启动全部服务层控制器。"""

    def __init__(self):
        self.service_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_dir = os.path.dirname(self.service_dir)
        self.config = self._load_config()
        self.topics = self.config["topics"]
        self.done_topic = self.topics["done"]
        self.sync_request = "/humanoid/sync/request/"
        self.sync_response = "/humanoid/sync/response/"
        self.sync_data = "/humanoid/sync/data/"
        self.legacy_topics = {
            "status_control": "/humanoid/status/control",
            "camera_control": "/humanoid/camera/control",
            "joints_control": "/humanoid/joints/control",
            "commands": "/humanoid/commands/data",
            "commands_done": "/humanoid/commands/done",
            "map_control": "/humanoid/map/control",
            "map_points": "/humanoid/map/points",
            "map_info": "/humanoid/map/info",
            "map_grid": "/humanoid/map/grid",
            "joints_save": "/humanoid/joints/save",
            "joints_data": "/humanoid/joints/data",
            "positions_control": "/humanoid/positions/control",
            "positions_data": "/humanoid/positions/data",
            "map_db_control": "/humanoid/map/db_control",
            "map_db_data": "/humanoid/map/db_data",
            "modbus_control": "/humanoid/modbus/control",
            "modbus_data": "/humanoid/modbus/data",
            "emergency_control": "/humanoid/emergency/control",
            "emergency_status": "/humanoid/emergency/status",
        }
        self._emergency_pressed = threading.Event()
        self._status_publishers_started = False
        self.motion_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="motion")
        self.io_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="service")
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"serivces2_{os.getpid()}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.controllers = {}

    def _load_config(self):
        path = os.path.join(self.service_dir, "config.json")
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def _path(self, key):
        value = self.config.get("paths", {}).get(key, key)
        return value if os.path.isabs(value) else os.path.join(self.project_dir, value)

    def _publish(self, topic, payload):
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=2)

    def _response(self, group, payload, success=True, **extra):
        message = {"cmd": payload.get("cmd"), "time": payload.get("time"), "success": success}
        message.update(extra)
        self._publish(self.topics[group]["response"], message)

    def _done(self, kind, payload, success=True, error=None):
        message = {
            "cmd": payload.get("cmd"), "time": payload.get("time"),
            "type": kind, "success": success,
        }
        if error:
            message["error"] = str(error)
        self._publish(self.done_topic, message)

    @staticmethod
    def _require_success(result, description):
        if result is False or result is None:
            raise RuntimeError(f"{description}失败")
        return result

    @staticmethod
    def _find_named(items, name):
        target = str(name)
        return next((item for item in items if str(item.get("name")) == target), None)

    @staticmethod
    def _orientation(value):
        if "orientation" in value:
            return value["orientation"]
        qx = value.get("rx", 0.0)
        qy = value.get("ry", 0.0)
        qz = value.get("rz", 0.0)
        qw = value.get("rw", math.sqrt(max(0.0, 1.0 - qx * qx - qy * qy - qz * qz)))
        return [qx, qy, qz, qw]

    def _initialize_controllers(self):
        topics = self.topics
        chassis = ChassisController(
            agibot_gdk, self.client, topics["base"]["response"], self.done_topic)
        joint = JointController(
            agibot_gdk, self.client, topics["joint"]["response"], self.done_topic)
        pose = PoseController(
            agibot_gdk, self.client, topics["pose"]["response"], self.done_topic)
        end_effector = EndEffectorController(
            agibot_gdk, self.client, topics["ee"]["response"], self.done_topic)
        interaction = InteractionController(
            agibot_gdk, self.client, topics["tts"]["response"])
        camera = CameraController(
            agibot_gdk, self.client, topics["camera"]["response"], self._path("images"))
        apriltag = ApriltagController(
            self.client, topics["apriltag"]["response"], self._path("images"))
        database = DatabaseController(
            os.path.join(self._path("datas"), "robot_data.db"), joint, pose, chassis)
        sync = SyncController(
            self.client, self.sync_response, self._path("datas"), self.sync_data)
        database.init()
        apriltag.init()
        sync.load_config()
        self.controllers = {
            "chassis": chassis, "joint": joint, "pose": pose,
            "ee": end_effector, "tts": interaction, "camera": camera,
            "apriltag": apriltag, "db": database, "sync": sync,
        }

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        is_failure = (
            reason_code.is_failure
            if hasattr(reason_code, "is_failure")
            else reason_code != 0
        )
        if is_failure:
            print(f"[MQTT] 连接失败: {reason_code}")
            return
        request_topics = [
            value["request"] for value in self.topics.values()
            if isinstance(value, dict) and "request" in value
        ]
        request_topics.append(self.sync_request)
        request_topics.extend([
            self.legacy_topics["status_control"],
            self.legacy_topics["camera_control"],
            self.legacy_topics["joints_control"],
            self.legacy_topics["commands"],
            self.legacy_topics["map_control"],
            self.legacy_topics["joints_save"],
            self.legacy_topics["positions_control"],
            self.legacy_topics["map_db_control"],
            self.legacy_topics["modbus_control"],
            self.legacy_topics["emergency_control"],
        ])
        for topic in request_topics:
            client.subscribe(topic, qos=2)
            print(f"[MQTT] 已订阅 {topic}")
        self._publish_emergency_status()
        self.controllers["sync"].start_polling()
        self._start_status_publishers()

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("报文必须是 JSON 对象")
        except Exception as exc:
            print(f"[MQTT] 无法解析 {message.topic}: {exc}")
            return
        if message.topic == self.legacy_topics["emergency_control"]:
            action = payload.get("action", payload.get("command"))
            if action in {"press", "pressed"}:
                # 先同步置位状态，立即拦截后续运动命令。
                self._emergency_pressed.set()
            elif action in {"release", "released"}:
                self._emergency_pressed.clear()
            self.io_executor.submit(self._dispatch_safely, message.topic, payload)
            return
        motion_topics = {
            self.topics[name]["request"] for name in ("base", "joint", "pose", "ee")
        }
        motion_topics.update({
            self.legacy_topics["joints_control"],
            self.legacy_topics["commands"],
        })
        if message.topic == self.legacy_topics["positions_control"] and payload.get("command") == "goto":
            motion_topics.add(message.topic)
        if message.topic == self.legacy_topics["map_db_control"] and payload.get("command") == "goto":
            motion_topics.add(message.topic)
        if message.topic == self.topics["db"]["request"] and payload.get("cmd") in {
            "moveJoint", "movePosition", "moveMapPoint"
        }:
            motion_topics.add(message.topic)
        if message.topic in motion_topics and self._emergency_pressed.is_set():
            self.io_executor.submit(self._reject_motion_while_emergency, message.topic, payload)
            return
        is_emergency_stop = (
            message.topic == self.topics["base"]["request"]
            and payload.get("cmd") == "stop"
        )
        executor = (
            self.motion_executor
            if message.topic in motion_topics and not is_emergency_stop
            else self.io_executor
        )
        executor.submit(self._dispatch_safely, message.topic, payload)

    def _dispatch_safely(self, topic, payload):
        try:
            self._dispatch(topic, payload)
        except Exception as exc:
            print(f"[服务] {topic} {payload.get('cmd')} 执行失败: {exc}")
            self._publish_failure(topic, payload, exc)

    def _dispatch(self, topic, payload):
        routes = {
            self.topics["base"]["request"]: self._handle_base,
            self.topics["joint"]["request"]: self._handle_joint,
            self.topics["pose"]["request"]: self._handle_pose,
            self.topics["ee"]["request"]: self._handle_end_effector,
            self.topics["tts"]["request"]: self._handle_tts,
            self.topics["camera"]["request"]: self._handle_camera,
            self.topics["apriltag"]["request"]: self._handle_apriltag,
            self.topics["db"]["request"]: self._handle_database,
            self.topics["maptest"]["request"]: self._handle_maptest,
            self.sync_request: self._handle_sync,
            self.legacy_topics["status_control"]: self._handle_legacy_status_control,
            self.legacy_topics["camera_control"]: self._handle_legacy_camera,
            self.legacy_topics["joints_control"]: self._handle_legacy_joint,
            self.legacy_topics["commands"]: self._handle_legacy_command,
            self.legacy_topics["map_control"]: self._handle_legacy_map,
            self.legacy_topics["joints_save"]: self._handle_legacy_data,
            self.legacy_topics["positions_control"]: self._handle_legacy_position,
            self.legacy_topics["map_db_control"]: self._handle_legacy_map_database,
            self.legacy_topics["modbus_control"]: self._handle_legacy_sync,
            self.legacy_topics["emergency_control"]: self._handle_emergency,
        }
        handler = routes.get(topic)
        if handler is None:
            raise ValueError(f"未知主题: {topic}")
        handler(payload)

    def _publish_emergency_status(self, success=True, error=None):
        """发布可保留的急停状态，新打开的网页也能立即同步。"""
        message = {
            "state": "pressed" if self._emergency_pressed.is_set() else "released",
            "pressed": self._emergency_pressed.is_set(),
            "success": success,
            "time": int(time.time() * 1000),
        }
        if error:
            message["error"] = str(error)
        self.client.publish(
            self.legacy_topics["emergency_status"],
            json.dumps(message, ensure_ascii=False), qos=2, retain=True)

    def _reject_motion_while_emergency(self, topic, payload):
        error = RuntimeError("急停已按下，运动命令已拒绝")
        print(f"[急停] 拒绝运动命令: {topic} {payload}")
        self._publish_failure(topic, payload, error)

    def _handle_emergency(self, payload):
        action = payload.get("action", payload.get("command"))
        if action in {"press", "pressed"}:
            errors = []
            print("[急停] 已按下，立即停止底盘并保持上肢当前位置")
            try:
                self.controllers["chassis"].set_emergency_stop(True)
            except Exception as exc:
                errors.append(f"底盘: {exc}")
            try:
                self.controllers["joint"].emergency_stop()
            except Exception as exc:
                errors.append(f"上肢: {exc}")
            self._publish_emergency_status(not errors, "; ".join(errors) if errors else None)
            return
        if action in {"release", "released"}:
            self.controllers["chassis"].set_emergency_stop(False)
            print("[急停] 已松开，恢复接收运动命令")
            self._publish_emergency_status()
            return
        raise ValueError(f"未知急停命令: {action}")

    def _publish_failure(self, topic, payload, exc):
        motion_groups = {
            self.topics["base"]["request"]: "base",
            self.topics["joint"]["request"]: "joint",
            self.topics["pose"]["request"]: "pose",
            self.topics["ee"]["request"]: "ee",
        }
        if topic in motion_groups:
            self._done(motion_groups[topic], payload, False, exc)
        elif topic == self.sync_request:
            target = self.sync_data if payload.get("cmd") == "readData" else self.sync_response
            self._publish(target, {
                "cmd": payload.get("cmd"), "time": payload.get("time"),
                "name": payload.get("name"), "success": False, "error": str(exc),
            })
        else:
            for group, config in self.topics.items():
                if isinstance(config, dict) and config.get("request") == topic:
                    self._response(group, payload, False, error=str(exc))
                    break

    def _handle_base(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["chassis"]
        self._response("base", payload)
        if cmd == "relative":
            result = controller.relative_move(payload["x"], payload["y"], payload["rotate"])
        elif cmd == "relative2":
            result = controller.relative2_move(
                payload["x"], payload["y"], payload["rotate"],
                payload.get("vel_line", 0.25), payload.get("vel_rotate", 10.0))
        elif cmd in {"point", "point_no_wait"}:
            point = self._find_named(self.controllers["db"].get_map_points(), payload.get("name"))
            if point is None:
                point = self._find_named(
                    controller.get_map_points(), payload.get("name"))
            if point is None:
                raise KeyError(f"地图点位不存在: {payload.get('name')}")
            result = (
                controller.point_move2(point)
                if cmd == "point_no_wait"
                else controller.point_move(point)
            )
        elif cmd == "wait_motion":
            result = controller.wait_navigation_done(payload.get("timeout", 120.0))
        elif cmd == "points":
            points = [
                self._find_named(self.controllers["db"].get_map_points(), name)
                for name in payload.get("val", [])
            ]
            if not points or any(point is None for point in points):
                raise KeyError("多点路径包含不存在的地图点位")
            result = controller.points_move(
                points, payload.get("vel_line", 0.25), payload.get("vel_rotate", 10.0))
        elif cmd == "stop":
            result = controller.stop()
        else:
            raise ValueError(f"未知底盘命令: {cmd}")
        self._require_success(result, cmd)
        if cmd != "stop":
            self._done("base", payload)

    def _handle_joint(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["joint"]
        if cmd == "get_current_angles":
            result = controller.get_current_angles()
            self._response("joint", payload, True, result=result)
            return
        self._response("joint", payload)
        methods = {
            "head": lambda: controller.move_head(payload["joints"], payload.get("speed")),
            "waist": lambda: controller.move_waist(payload["joints"], payload.get("speed")),
            "left_arm": lambda: controller.move_left_arm(payload["joints"], payload.get("speed")),
            "right_arm": lambda: controller.move_right_arm(payload["joints"], payload.get("speed")),
            "arms": lambda: controller.move_arms(payload["joints"], payload.get("speed")),
            "wbc": lambda: controller.move_wbc(payload["joints"], payload.get("speed")),
            "single_joint": lambda: controller.move_single_joint(
                payload["name"], value=payload.get("value"),
                offset=payload.get("offset"), speed=payload.get("speed")),
        }
        if cmd not in methods:
            raise ValueError(f"未知关节命令: {cmd}")
        self._require_success(methods[cmd](), cmd)
        self._done("joint", payload)

    def _handle_pose(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["pose"]
        if cmd == "get_current_pose":
            result = controller.get_current_pose(payload["side"])
            self._response("pose", payload, True, side=payload["side"], result=result)
            return
        self._response("pose", payload)
        if cmd == "relative":
            result = controller.move_relative(
                payload["side"], payload["offset"], payload.get("rotation", [0, 0, 0]))
        elif cmd == "left":
            result = controller.move_left_arm(payload["position"], payload["orientation"])
        elif cmd == "right":
            result = controller.move_right_arm(payload["position"], payload["orientation"])
        elif cmd == "both":
            result = controller.move_both_arms(payload["left"], payload["right"])
        elif cmd == "waist":
            result = controller.move_waist(payload["offset"])
        else:
            raise ValueError(f"未知位姿命令: {cmd}")
        self._require_success(result, cmd)
        self._done("pose", payload)

    def _handle_end_effector(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["ee"]
        self._response("ee", payload)
        methods = {
            "left_gripper": lambda: controller.left_gripper(payload["position"]),
            "right_gripper": lambda: controller.right_gripper(payload["position"]),
            "both_grippers": lambda: controller.both_grippers(payload["left"], payload["right"]),
        }
        if cmd not in methods:
            raise ValueError(f"未知末端命令: {cmd}")
        self._require_success(methods[cmd](), cmd)
        self._done("ee", payload)

    def _handle_tts(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["tts"]
        if cmd == "speak":
            result = controller.speak(payload["text"])
        elif cmd == "set_volume":
            result = controller.set_volume(payload["volume"])
        elif cmd == "get_volume":
            result = controller.get_volume()
            self._response("tts", payload, True, volume=result)
            return
        else:
            raise ValueError(f"未知 TTS 命令: {cmd}")
        self._response("tts", payload, bool(result))

    def _handle_camera(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["camera"]
        if cmd == "capture":
            result = controller.capture(payload["camera"])
        elif cmd == "capture_all":
            result = controller.capture_all()
        elif cmd == "get_image":
            result = controller.get_image_base64(payload["camera"])
        else:
            raise ValueError(f"未知相机命令: {cmd}")
        extra = {"result": result}
        if cmd == "capture" and result is not None:
            extra["path"] = os.path.join(controller.image_save_dir, result)
        self._response("camera", payload, result is not None, **extra)

    def _handle_apriltag(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["apriltag"]
        if cmd == "detect_file":
            result = controller.detect_file(payload["file"])
        elif cmd == "detect_saved":
            result = controller.detect_saved_image(payload["file"])
        else:
            raise ValueError(f"未知 Apriltag 命令: {cmd}")
        self._response("apriltag", payload, True, result=result)

    def _move_stored_joint(self, payload):
        expected_type = payload.get("type")
        item = next((candidate for candidate in self.controllers["db"].get_joints()
                     if str(candidate.get("name")) == str(payload.get("name"))
                     and (not expected_type or candidate.get("type") == expected_type)), None)
        if item is None:
            raise KeyError(f"关节变量不存在: {payload.get('name')}")
        controller = self.controllers["joint"]
        value, speed, kind = item["value"], payload.get("speed"), item["type"]
        if kind == "single_joint":
            joint_name = item.get("joint_name")
            return controller.move_single_joint(
                joint_name, value=value.get(joint_name), speed=speed)
        if kind == "left_arm":
            joints = [value.get(key, 0.0) for key in controller.left_arm_joint_keys]
            return controller.move_left_arm(joints, speed)
        if kind == "right_arm":
            joints = [value.get(key, 0.0) for key in controller.right_arm_joint_keys]
            return controller.move_right_arm(joints, speed)
        if kind == "whole_body":
            return controller.move_wbc(value, speed)
        raise ValueError(f"未知关节变量类型: {kind}")

    def _move_stored_position(self, payload):
        expected_type = payload.get("type")
        item = next((candidate for candidate in self.controllers["db"].get_positions()
                     if str(candidate.get("name")) == str(payload.get("name"))
                     and (not expected_type or candidate.get("type") == expected_type)), None)
        if item is None:
            raise KeyError(f"坐标姿态变量不存在: {payload.get('name')}")
        controller, value, kind = self.controllers["pose"], item["value"], item["type"]
        if kind in ("left", "right"):
            position = [value.get("x", 0.0), value.get("y", 0.0), value.get("z", 0.0)]
            method = controller.move_left_arm if kind == "left" else controller.move_right_arm
            return method(position, self._orientation(value))
        if kind == "both":
            left, right = value.get("left", {}), value.get("right", {})
            left_target = {"position": [left.get(k, 0.0) for k in ("x", "y", "z")],
                           "orientation": self._orientation(left)}
            right_target = {"position": [right.get(k, 0.0) for k in ("x", "y", "z")],
                            "orientation": self._orientation(right)}
            return controller.move_both_arms(left_target, right_target)
        if kind == "waist":
            return controller.move_waist(value)
        raise ValueError(f"未知坐标姿态类型: {kind}")

    def _handle_database(self, payload):
        cmd = payload.get("cmd")
        db = self.controllers["db"]
        simple = {
            "addJoint": lambda: db.add_joints(
                payload["type"], payload["name"], payload["value"], payload.get("joint_name")),
            "updateJoint": lambda: db.update_joints(
                payload["type"], payload["name"], payload["value"], payload.get("joint_name")),
            "deleteJoint": lambda: db.delete_joints(payload["type"], payload["name"]),
            "getJoints": db.get_joints,
            "addPosition": lambda: db.add_positions(payload["type"], payload["name"], payload["value"]),
            "updatePosition": lambda: db.update_positions(payload["type"], payload["name"], payload["value"]),
            "deletePosition": lambda: db.delete_positions(payload["type"], payload["name"]),
            "getPositions": db.get_positions,
            "addMapPoint": lambda: db.add_map_point(
                payload["name"], payload["position"], payload["orientation"], payload.get("source", "local")),
            "updateMapPoint": lambda: db.update_map_point(
                payload["name"], payload["position"], payload["orientation"], payload.get("source")),
            "deleteMapPoint": lambda: db.delete_map_point(payload["name"]),
            "getMapPoints": db.get_map_points,
        }
        if cmd == "moveJoint":
            result = self._move_stored_joint(payload)
        elif cmd == "movePosition":
            result = self._move_stored_position(payload)
        elif cmd == "moveMapPoint":
            point = self._find_named(db.get_map_points(), payload.get("name"))
            if point is None:
                raise KeyError(f"地图点位不存在: {payload.get('name')}")
            result = self.controllers["chassis"].point_move(point)
        elif cmd in simple:
            result = simple[cmd]()
        else:
            raise ValueError(f"未知数据库命令: {cmd}")
        self._response("db", payload, result is not False, name=payload.get("name"), result=result)

    def _handle_maptest(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["chassis"]
        db = self.controllers["db"]
        readers = {
            "snapshot": controller.get_map_snapshot,
            "map": controller.get_map_data,
            "laser": controller.get_laser_points,
            "points": controller.get_map_points,
            "battery": controller.get_battery,
        }
        if cmd in readers:
            self._response("maptest", payload, True, result=readers[cmd]())
            return
        if cmd == "save_current":
            pose = controller.get_current_map_pose()
            result = db.add_map_point(
                payload["name"], pose["position"], pose["orientation"], "local")
            if not result:
                raise ValueError(f"地图点位已存在: {payload['name']}")
            self._response("maptest", payload, True, result=True)
            return
        if cmd == "sync_points":
            database_points = {item["name"] for item in db.get_map_points()}
            added = 0
            updated = 0
            for point in controller.get_map_points():
                if point["name"] in database_points:
                    db.update_map_point(
                        point["name"], point["position"], point["orientation"], "map")
                    updated += 1
                else:
                    db.add_map_point(
                        point["name"], point["position"], point["orientation"], "map")
                    added += 1
            self._response(
                "maptest", payload, True,
                result={"added": added, "updated": updated})
            return
        raise ValueError(f"未知地图测试命令: {cmd}")

    def _handle_sync(self, payload):
        cmd = payload.get("cmd")
        controller = self.controllers["sync"]
        if cmd == "readData":
            item = self._find_named(controller.snapshot(), payload["name"])
            value = item.get("value") if item else None
            self._publish(self.sync_data, {
                "cmd": cmd, "time": payload.get("time"), "name": payload["name"],
                "value": value, "success": item is not None,
            })
        elif cmd == "setData":
            success = controller.set_data(payload["name"], payload.get("value"))
            self._publish(self.sync_response, {
                "cmd": cmd, "time": payload.get("time"), "name": payload["name"],
                "success": success,
            })
        else:
            raise ValueError(f"未知同步命令: {cmd}")

    def _start_status_publishers(self):
        """启动各控制器自己的状态发布器，不创建集中式状态服务。"""
        if self._status_publishers_started:
            return
        self.controllers["joint"].start_status_publishing()
        self.controllers["pose"].start_status_publishing()
        self.controllers["chassis"].start_status_publishing()
        self.controllers["ee"].start_status_publishing()
        self.controllers["camera"].start_frame_cache()
        self._status_publishers_started = True

    def _stop_status_publishers(self):
        if not self._status_publishers_started:
            return
        self.controllers["joint"].stop_status_publishing()
        self.controllers["pose"].stop_status_publishing()
        self.controllers["chassis"].stop_status_publishing()
        self.controllers["ee"].stop_status_publishing()
        self.controllers["camera"].stop_frame_cache()
        self._status_publishers_started = False

    def _publish_legacy(self, topic_key, payload):
        self.client.publish(
            self.legacy_topics[topic_key],
            json.dumps(payload, ensure_ascii=False), qos=0)

    def _handle_legacy_status_control(self, payload):
        command = payload.get("command")
        if command == "start_cloud":
            self.controllers["chassis"].set_cloud_publishing(True)
        elif command == "stop_cloud":
            self.controllers["chassis"].set_cloud_publishing(False)
        else:
            raise ValueError(f"未知旧网页状态命令: {command}")

    def _handle_legacy_camera(self, payload):
        command = payload.get("command")
        camera = self.controllers["camera"]
        if command == "start":
            camera.set_streaming(True)
        elif command == "stop":
            camera.set_streaming(False)
        elif command == "start_continuous_capture":
            camera.set_continuous_capture(True)
        elif command == "stop_continuous_capture":
            camera.set_continuous_capture(False)
        elif command == "save_photo":
            names = payload.get("cameras") or ["kHeadColor", "kHeadDepth"]
            for name in names:
                camera.capture(name)
        else:
            raise ValueError(f"未知旧网页相机命令: {command}")

    def _handle_legacy_joint(self, payload):
        command = str(payload.get("command", ""))
        data = payload.get("data")
        speed = payload.get("speed")
        controller = self.controllers["joint"]
        if isinstance(data, str):
            self._require_success(
                self._move_stored_joint({"name": data, "type": command, "speed": speed}), command)
            self._publish_legacy(
                "commands_done", {"command": "done", "source": command})
            return
        methods = {
            "WBC": lambda: controller.move_wbc(data, speed),
            "arms": lambda: controller.move_arms(data, speed),
            "left": lambda: controller.move_left_arm(
                [data.get(key, 0.0) for key in controller.left_arm_joint_keys], speed),
            "right": lambda: controller.move_right_arm(
                [data.get(key, 0.0) for key in controller.right_arm_joint_keys], speed),
            "head": lambda: controller.move_head(
                [data.get(key, 0.0) for key in controller.head_joint_keys], speed),
            "waist": lambda: controller.move_waist(
                [data.get(key, 0.0) for key in controller.waist_joint_keys], speed),
        }
        if command not in methods:
            raise ValueError(f"旧网页关节命令暂不支持: {command}")
        self._require_success(methods[command](), command)
        self._publish_legacy("commands_done", {"command": "done", "source": command})

    def _handle_legacy_command(self, payload):
        command = payload.get("command")
        data = payload.get("data")
        if command == "go_rel":
            data = data or {}
            result = self.controllers["chassis"].relative_move(
                float(data.get("x", 0.0)) * 1000.0,
                float(data.get("y", 0.0)) * 1000.0,
                math.degrees(float(data.get("yaw_rad", 0.0))))
        elif command == "go":
            points = self.controllers["chassis"].get_map_points()
            point = self._find_named(points, data)
            if point is None and isinstance(data, int) and 0 <= data < len(points):
                point = points[data]
            if point is None:
                raise KeyError(f"地图点位不存在: {data}")
            result = self.controllers["chassis"].point_move(point)
        elif command == "offset_move":
            values = data or {}
            result = True
            if any(key.startswith("l") for key in values):
                result = self.controllers["pose"].move_relative(
                    "left",
                    [values.get("lx", 0.0) / 1000.0,
                     values.get("ly", 0.0) / 1000.0,
                     values.get("lz", 0.0) / 1000.0],
                    [values.get("lrx", 0.0), values.get("lry", 0.0), values.get("lrz", 0.0)])
            if any(key.startswith("r") for key in values):
                result = self.controllers["pose"].move_relative(
                    "right",
                    [values.get("rx", 0.0) / 1000.0,
                     values.get("ry", 0.0) / 1000.0,
                     values.get("rz", 0.0) / 1000.0],
                    [values.get("rrx", 0.0), values.get("rry", 0.0), values.get("rrz", 0.0)]) and result
        elif command == "grab":
            values = data or {}
            left = values.get("left")
            right = values.get("right")
            normalize = lambda value: max(0.0, min(1.0, float(value) / -0.7))
            if left is not None and right is not None:
                result = self.controllers["ee"].both_grippers(normalize(left), normalize(right))
            elif left is not None:
                result = self.controllers["ee"].left_gripper(normalize(left))
            elif right is not None:
                result = self.controllers["ee"].right_gripper(normalize(right))
            else:
                result = True
        elif command == "tts":
            result = self.controllers["tts"].speak(str(data))
        else:
            raise ValueError(f"旧网页动作命令暂不支持: {command}")
        self._require_success(result, command)
        self._publish_legacy("commands_done", {"command": "done", "source": command})

    def _handle_legacy_map(self, payload):
        command = payload.get("command")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        chassis = self.controllers["chassis"]
        if command in ("read_points", "read_map_points"):
            points = chassis.get_map_points() + self.controllers["db"].get_map_points()
            self._publish_legacy("map_points", {"command": "map_points", "data": points})
        elif command == "read_maps":
            self._publish_legacy("map_info", {"command": "maps", "data": chassis.get_maps()})
            self._publish_legacy("map_info", {
                "command": "slam_state", "data": {"is_mapping": chassis.is_mapping()}})
            self._publish_legacy("map_grid", {
                "command": "occupancy_grid", "data": chassis.get_legacy_map_grid()})
        elif command == "load_grid":
            self._publish_legacy("map_grid", {
                "command": "occupancy_grid",
                "data": chassis.get_legacy_map_grid(data.get("map_id"))})
        elif command == "switch_map":
            chassis.switch_map(data.get("map_id"))
            self._handle_legacy_map({"command": "read_maps"})
        elif command == "save_point":
            name = data.get("name", "unnamed")
            pose = chassis.get_current_map_pose()
            self.controllers["db"].add_map_point(
                name, pose["position"], pose["orientation"], "local")
            self._handle_legacy_map({"command": "read_points"})
        elif command == "start_mapping":
            chassis.start_mapping()
            self._publish_legacy("map_info", {
                "command": "slam_state", "data": {"is_mapping": True}})
        elif command in ("stop_mapping", "save_map"):
            chassis.stop_mapping()
            self._publish_legacy("map_info", {
                "command": "slam_state", "data": {"is_mapping": False}})
        else:
            raise ValueError(f"未知旧网页地图命令: {command}")

    def _publish_legacy_data(self):
        db = self.controllers["db"]
        items = [dict(item, category="joints") for item in db.get_joints()]
        items.extend(dict(item, category="positions") for item in db.get_positions())
        self._publish_legacy(
            "joints_data", {"command": "response", "data": items})

    def _handle_legacy_data(self, payload):
        """处理旧 web 的示教数据保存、读取、更新和删除。"""
        command = payload.get("command")
        db = self.controllers["db"]
        category = payload.get("category", "joints")
        kind = payload.get("type", "WBC")
        name = payload.get("name", "unnamed")
        joint_name = payload.get("joint_name")
        data = payload.get("data", {})
        if command == "save_joints":
            success = db.add_joints(kind, name, data, joint_name)
        elif command == "save_position":
            success = db.add_positions(kind, name, data)
        elif command == "read":
            self._publish_legacy_data()
            return
        elif command == "update" and category == "positions":
            success = db.update_positions(kind, name, data)
        elif command == "update":
            success = db.update_joints(kind, name, data, joint_name)
        elif command == "delete" and category == "positions":
            success = db.delete_positions(kind, name)
        elif command == "delete":
            success = db.delete_joints(kind, name)
        else:
            raise ValueError(f"未知旧网页数据命令: {command}")
        if not success:
            raise ValueError(f"数据操作失败或名称已存在: {kind}/{name}")
        self._publish_legacy_data()

    @staticmethod
    def _pose_for_database(pose):
        position = pose["position"]
        orientation = pose["orientation"]
        return {
            "x": position[0], "y": position[1], "z": position[2],
            "rx": orientation[0], "ry": orientation[1], "rz": orientation[2],
        }

    def _handle_legacy_position(self, payload):
        command = payload.get("command")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        kind, name = data.get("type"), data.get("name")
        db = self.controllers["db"]
        if kind not in ("left", "right", "both") or not name:
            raise ValueError("坐标点位缺少有效的 type/name")
        if command == "goto":
            success = self._move_stored_position({"name": name, "type": kind})
        elif command == "update":
            pose = self.controllers["pose"]
            if kind == "both":
                value = {
                    "left": self._pose_for_database(pose.get_current_pose("left")),
                    "right": self._pose_for_database(pose.get_current_pose("right")),
                }
            else:
                value = self._pose_for_database(pose.get_current_pose(kind))
            success = db.update_positions(kind, name, value)
        else:
            raise ValueError(f"未知旧网页坐标命令: {command}")
        self._publish_legacy("positions_data", {
            "command": f"{command}_result",
            "data": {"name": name, "success": bool(success),
                     "message": "操作成功" if success else "操作失败"},
        })
        if command == "update" and success:
            self._publish_legacy_data()

    def _publish_legacy_map_database(self):
        self._publish_legacy("map_db_data", {
            "command": "db_points",
            "data": self.controllers["db"].get_map_points(),
        })

    def _handle_legacy_map_database(self, payload):
        command = payload.get("command")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        db = self.controllers["db"]
        name = data.get("name")
        if command == "read":
            self._publish_legacy_map_database()
            return
        if command == "update":
            if not name:
                raise ValueError("地图点位缺少 name")
            current = self._find_named(db.get_map_points(), name)
            if current:
                success = db.update_map_point(
                    name, data.get("position", [0, 0, 0]),
                    data.get("orientation", [0, 0, 0, 1]), data.get("source"))
            else:
                success = db.add_map_point(
                    name, data.get("position", [0, 0, 0]),
                    data.get("orientation", [0, 0, 0, 1]), data.get("source", "local"))
            if success:
                self._publish_legacy_map_database()
            return
        if command == "delete":
            if not db.delete_map_point(name):
                raise KeyError(f"地图点位不存在: {name}")
            self._publish_legacy_map_database()
            return
        if command == "goto":
            point = self._find_named(db.get_map_points(), name)
            if point is None:
                success, message = False, "点位不存在"
            else:
                success = bool(self.controllers["chassis"].point_move(point))
                message = "已到达" if success else "导航失败"
            self._publish_legacy("map_db_data", {
                "command": "goto_result",
                "data": {"name": name, "success": success, "message": message},
            })
            return
        raise ValueError(f"未知旧网页地图数据库命令: {command}")

    def _handle_legacy_sync(self, payload):
        command = payload.get("command")
        sync = self.controllers["sync"]
        if command == "read":
            for item in sync.legacy_device_snapshots():
                self._publish_legacy("modbus_data", item)
            return
        if command == "write":
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            if not sync.set_legacy_value(data):
                raise KeyError("未找到可写同步点位")
            for item in sync.legacy_device_snapshots():
                self._publish_legacy("modbus_data", item)
            return
        raise ValueError(f"未知旧网页同步命令: {command}")

    def run(self):
        result = agibot_gdk.gdk_init()
        if result != agibot_gdk.GDKRes.kSuccess:
            raise RuntimeError(f"GDK 初始化失败: {result}")
        try:
            self._initialize_controllers()
            broker = self.config["mqtt"]["broker"]
            port = int(self.config["mqtt"]["port"])
            self.client.connect(broker, port, 60)
            print(f"[服务] serivces2 已启动，MQTT={broker}:{port}")
            self.client.loop_forever()
        finally:
            self._stop_status_publishers()
            if "sync" in self.controllers:
                self.controllers["sync"].stop_polling()
            self.motion_executor.shutdown(wait=False, cancel_futures=True)
            self.io_executor.shutdown(wait=False, cancel_futures=True)
            try:
                self.client.disconnect()
            finally:
                agibot_gdk.gdk_release()


if __name__ == "__main__":
    ServiceApplication().run()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""serivces2 的统一 MQTT 服务入口。"""

import json
import math
import os
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
        for topic in request_topics:
            client.subscribe(topic, qos=2)
            print(f"[MQTT] 已订阅 {topic}")
        self.controllers["sync"].start_polling()

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("报文必须是 JSON 对象")
        except Exception as exc:
            print(f"[MQTT] 无法解析 {message.topic}: {exc}")
            return
        motion_topics = {
            self.topics[name]["request"] for name in ("base", "joint", "pose", "ee")
        }
        if message.topic == self.topics["db"]["request"] and payload.get("cmd") in {
            "moveJoint", "movePosition", "moveMapPoint"
        }:
            motion_topics.add(message.topic)
        executor = self.motion_executor if message.topic in motion_topics else self.io_executor
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
            self.sync_request: self._handle_sync,
        }
        handler = routes.get(topic)
        if handler is None:
            raise ValueError(f"未知主题: {topic}")
        handler(payload)

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
        elif cmd == "point":
            point = self._find_named(self.controllers["db"].get_map_points(), payload.get("name"))
            if point is None:
                raise KeyError(f"地图点位不存在: {payload.get('name')}")
            result = controller.point_move(point)
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
        self._response("camera", payload, result is not None, result=result)

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
        item = self._find_named(self.controllers["db"].get_joints(), payload.get("name"))
        if item is None:
            raise KeyError(f"关节变量不存在: {payload.get('name')}")
        controller = self.controllers["joint"]
        value, speed, kind = item["value"], payload.get("speed"), item["type"]
        if kind == "head":
            joints = [value.get(key, 0.0) for key in controller.head_joint_keys]
            return controller.move_head(joints, speed)
        if kind == "waist":
            joints = [value.get(key, 0.0) for key in controller.waist_joint_keys]
            return controller.move_waist(joints, speed)
        if kind in ("left", "left_arm"):
            joints = [value.get(key, 0.0) for key in controller.left_arm_joint_keys]
            return controller.move_left_arm(joints, speed)
        if kind in ("right", "right_arm"):
            joints = [value.get(key, 0.0) for key in controller.right_arm_joint_keys]
            return controller.move_right_arm(joints, speed)
        if kind == "arms":
            return controller.move_arms(value, speed)
        return controller.move_wbc(value, speed)

    def _move_stored_position(self, payload):
        item = self._find_named(self.controllers["db"].get_positions(), payload.get("name"))
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
            "addJoint": lambda: db.add_joints(payload["type"], payload["name"], payload["value"]),
            "updateJoint": lambda: db.update_joints(payload["type"], payload["name"], payload["value"]),
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

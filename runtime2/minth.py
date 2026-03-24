#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 MQTT 调用 services2 的 G2 中文用户层 API。"""

import json
import threading
import time
import uuid

try:
    import paho.mqtt.client as mqtt
except ImportError:  # 纯模拟测试不要求安装 paho-mqtt
    mqtt = None


class G2Error(RuntimeError):
    """G2 用户层基础异常。"""


class MqttPublishError(G2Error):
    """MQTT 发布失败。"""


class ResponseTimeoutError(G2Error):
    """等待服务层反馈超时。"""


class G2:
    """G2 机器人中文控制接口。

    运动方法发布 MQTT 后阻塞等待与请求时间戳匹配的完成反馈。
    一个实例同一时刻只执行一个同步请求。
    """

    BASE_REQUEST = "/humanoid/base/request/"
    BASE_RESPONSE = "/humanoid/base/response/"
    JOINT_REQUEST = "/humanoid/joint/request/"
    JOINT_RESPONSE = "/humanoid/joint/response/"
    POSE_REQUEST = "/humanoid/pose/request/"
    POSE_RESPONSE = "/humanoid/pose/response/"
    EE_REQUEST = "/humanoid/ee/request/"
    EE_RESPONSE = "/humanoid/ee/response/"
    TTS_REQUEST = "/humanoid/tts/request/"
    TTS_RESPONSE = "/humanoid/tts/response/"
    CAMERA_REQUEST = "/humanoid/camera/request/"
    CAMERA_RESPONSE = "/humanoid/camera/response/"
    DB_REQUEST = "/humanoid/db/request/"
    DB_RESPONSE = "/humanoid/db/response/"
    SYNC_REQUEST = "/humanoid/sync/request/"
    SYNC_RESPONSE = "/humanoid/sync/response/"
    SYNC_DATA = "/humanoid/sync/data/"
    DONE = "/humanoid/done/"

    def __init__(
        self,
        broker="localhost",
        port=1883,
        timeout=120.0,
        client_id=None,
        mqtt_client=None,
    ):
        self.broker = broker
        self.port = int(port)
        self.timeout = float(timeout)
        self._connected = threading.Event()
        self._request_lock = threading.Lock()
        self._response_event = threading.Event()
        self._expected = None
        self._response = None
        self._last_timestamp = 0
        self._timestamp_lock = threading.Lock()
        self._pending_base_motion = None

        if mqtt_client is None:
            if mqtt is None:
                raise RuntimeError("真实 MQTT 连接需要安装 paho-mqtt")
            mqtt_client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id or f"runtime2_{uuid.uuid4().hex[:12]}",
            )
        self._client = mqtt_client
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self.broker, self.port, 60)
        self._client.loop_start()
        if not self._connected.wait(5.0):
            self.close()
            raise ConnectionError(f"无法连接 MQTT broker {self.broker}:{self.port}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        is_failure = (
            reason_code.is_failure
            if hasattr(reason_code, "is_failure")
            else reason_code != 0
        )
        if is_failure:
            return
        for topic in (
            self.BASE_RESPONSE, self.JOINT_RESPONSE, self.POSE_RESPONSE,
            self.EE_RESPONSE, self.TTS_RESPONSE, self.CAMERA_RESPONSE, self.DB_RESPONSE,
            self.SYNC_RESPONSE, self.SYNC_DATA, self.DONE,
        ):
            client.subscribe(topic, qos=2)
        self._connected.set()

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        expected = self._expected
        if expected is None or message.topic not in expected["topics"]:
            return
        if payload.get("cmd") != expected["cmd"]:
            return
        if payload.get("time") not in (None, expected["time"]):
            return
        if payload.get("type") not in (None, expected.get("type")):
            return
        if expected.get("name") and payload.get("name") not in (None, expected["name"]):
            return
        if message.topic == self.DONE:
            text = json.dumps(payload, ensure_ascii=False)
            print(f"[runtime2] MQTT {message.topic}: {text}")
        self._response = payload
        self._response_event.set()

    def _next_timestamp(self):
        with self._timestamp_lock:
            current = int(time.time() * 1000)
            self._last_timestamp = max(current, self._last_timestamp + 1)
            return time.strftime("%Y%m%d%H%M%S", time.localtime(self._last_timestamp / 1000)) + f"{self._last_timestamp % 1000:03d}"

    def _publish(self, topic, payload, qos=2):
        text = json.dumps(payload, ensure_ascii=False)
        print(f"[runtime2] MQTT {topic}: {text}")
        info = self._client.publish(topic, text, qos=qos)
        success_code = mqtt.MQTT_ERR_SUCCESS if mqtt is not None else 0
        if getattr(info, "rc", success_code) != success_code:
            raise MqttPublishError(f"MQTT 发布失败: {topic}")

    def _publish_and_wait(self, topic, payload, response_topics, cmd,
                          response_type=None, name=None, timeout=None):
        with self._request_lock:
            timestamp = payload.setdefault("time", self._next_timestamp())
            self._response = None
            self._response_event.clear()
            self._expected = {
                "topics": set(response_topics), "cmd": cmd, "time": timestamp,
                "type": response_type, "name": name,
            }
            try:
                self._publish(topic, payload)
                if not self._response_event.wait(self.timeout if timeout is None else timeout):
                    raise ResponseTimeoutError(f"等待 {cmd} 反馈超时")
                response = self._response or {}
                if response.get("success") is False or response.get("result") is False:
                    raise G2Error(f"服务层执行失败: {response}")
                return response
            finally:
                self._expected = None

    def _wait_motion_done(self, topic, payload, command_type, timeout=None):
        self._publish_and_wait(topic, payload, {self.DONE}, payload["cmd"],
                               command_type, timeout=timeout)
        return True

    @staticmethod
    def _validate_number(name, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"{name} 必须是数值")
        return float(value)

    @classmethod
    def _parse_offset(cls, value):
        if isinstance(value, dict):
            position = value.get("position", value.get("offset"))
            if position is None:
                position = [value.get("x", 0), value.get("y", 0), value.get("z", 0)]
            rotation = value.get("rotation", [value.get("rx", 0), value.get("ry", 0), value.get("rz", 0)])
        else:
            position, rotation = value, [0, 0, 0]
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            raise ValueError("偏移量必须包含 3 个位置分量")
        if not isinstance(rotation, (list, tuple)) or len(rotation) != 3:
            raise ValueError("旋转量必须包含 3 个角度分量")
        return [cls._validate_number("偏移量", item) for item in position], [cls._validate_number("旋转量", item) for item in rotation]

    def 底盘相对运动(self, 前后=0, 左右=0, 转角=0, timeout=None):
        """执行底盘相对运动；未传入的运动分量按 0 处理。"""
        payload = {"cmd": "relative", "x": self._validate_number("前后", 前后),
                   "y": self._validate_number("左右", 左右), "rotate": self._validate_number("转角", 转角)}
        return self._wait_motion_done(self.BASE_REQUEST, payload, "base", timeout)

    def 底盘地图点运动(self, 点位序号, timeout=None):
        payload = {"cmd": "point", "name": str(点位序号)}
        return self._wait_motion_done(self.BASE_REQUEST, payload, "base", timeout)

    def 底盘到点运动不等待(self, 点位序号, timeout=None):
        """启动地图点位导航，确认命令已下发后立即返回。"""
        if self._pending_base_motion is not None:
            raise G2Error("已有未等待完成的底盘到点运动，请先调用 等待底盘运动结束()")

        name = str(点位序号)
        payload = {"cmd": "point_no_wait", "name": name}
        self._publish_and_wait(
            self.BASE_REQUEST, payload, {self.DONE}, "point_no_wait",
            "base", timeout=timeout,
        )
        self._pending_base_motion = {"name": name, "time": payload["time"]}
        return True

    def 等待底盘运动结束(self, timeout=None):
        """等待此前由 ``底盘到点运动不等待`` 启动的导航任务结束。"""
        if self._pending_base_motion is None:
            raise G2Error("当前没有需要等待的底盘到点运动")

        wait_timeout = self.timeout if timeout is None else self._validate_number("等待超时", timeout)
        if wait_timeout <= 0:
            raise ValueError("等待超时必须大于 0")
        payload = {
            "cmd": "wait_motion",
            "name": self._pending_base_motion["name"],
            "source_time": self._pending_base_motion["time"],
            "timeout": wait_timeout,
        }
        try:
            self._publish_and_wait(
                self.BASE_REQUEST, payload, {self.DONE}, "wait_motion",
                "base", timeout=wait_timeout + 5.0,
            )
        except (MqttPublishError, ResponseTimeoutError):
            raise
        except G2Error:
            self._pending_base_motion = None
            raise
        self._pending_base_motion = None
        return True

    def 底盘相对运动带速度(self, 前后, 左右, 转角, 线速度, 角速度, timeout=None):
        payload = {"cmd": "relative2", "x": self._validate_number("前后", 前后),
                   "y": self._validate_number("左右", 左右), "rotate": self._validate_number("转角", 转角),
                   "vel_line": self._validate_number("线速度", 线速度),
                   "vel_rotate": self._validate_number("角速度", 角速度)}
        return self._wait_motion_done(self.BASE_REQUEST, payload, "base", timeout)

    def 夹爪(self, 左夹爪=None, 右夹爪=None, timeout=None):
        if 左夹爪 is None and 右夹爪 is None:
            raise ValueError("至少指定一个夹爪位置")

        positions = {}
        for side, value in (("left", 左夹爪), ("right", 右夹爪)):
            if value is None:
                continue
            position = self._validate_number(f"{side}夹爪", value)
            if not 0.0 <= position <= 1.0:
                raise ValueError("夹爪位置必须在 0.0 到 1.0 之间")
            positions[side] = position

        if len(positions) == 2:
            self._publish_and_wait(
                self.EE_REQUEST,
                {"cmd": "both_grippers", "left": positions["left"], "right": positions["right"]},
                {self.DONE}, "both_grippers", "ee", timeout=timeout,
            )
            return True

        side, position = next(iter(positions.items()))
        cmd = f"{side}_gripper"
        self._publish_and_wait(
            self.EE_REQUEST, {"cmd": cmd, "position": position},
            {self.DONE}, cmd, "ee", timeout=timeout,
        )
        return True

    def 末端偏移量(self, 左偏移量=None, 右偏移量=None, timeout=None):
        if 左偏移量 is None and 右偏移量 is None:
            raise ValueError("至少指定一侧末端偏移量")
        for side, value in (("left", 左偏移量), ("right", 右偏移量)):
            if value is None:
                continue
            offset, rotation = self._parse_offset(value)
            self._publish_and_wait(self.POSE_REQUEST,
                                   {"cmd": "relative", "side": side, "offset": offset, "rotation": rotation},
                                   {self.DONE}, "relative", "pose", timeout=timeout)
        return True

    def _database_motion(self, command, name, speed=None, linear_speed=None,
                         angular_speed=None, variable_type=None, timeout=None):
        payload = {"cmd": command, "name": str(name)}
        if variable_type is not None:
            payload["type"] = str(variable_type)
        if speed is not None:
            payload["speed"] = self._validate_number("角速度", speed)
        if linear_speed is not None:
            payload["linear_speed"] = self._validate_number("末端线速度", linear_speed)
        if angular_speed is not None:
            payload["angular_speed"] = self._validate_number("末端角速度", angular_speed)
        self._publish_and_wait(self.DB_REQUEST, payload, {self.DB_RESPONSE}, command,
                               name=str(name), timeout=timeout)
        return True

    def 全身关节运动(self, 关节变量, 角速度=None, timeout=None):
        return self._database_motion(
            "moveJoint", 关节变量, speed=角速度,
            variable_type="whole_body", timeout=timeout)

    def 左手关节运动(self, 左手关节变量, 角速度=None, timeout=None):
        return self._database_motion(
            "moveJoint", 左手关节变量, speed=角速度,
            variable_type="left_arm", timeout=timeout)

    def 右手关节运动(self, 右手关节变量, 角速度=None, timeout=None):
        return self._database_motion(
            "moveJoint", 右手关节变量, speed=角速度,
            variable_type="right_arm", timeout=timeout)

    def 单关节变量运动(self, 单关节变量, 角速度=None, timeout=None):
        """运动到数据库中保存的单关节变量。"""
        return self._database_motion(
            "moveJoint", 单关节变量, speed=角速度,
            variable_type="single_joint", timeout=timeout)

    def 左手坐标姿态运动(self, 左手坐标姿态变量, 末端线速度=None, 末端角速度=None, timeout=None):
        return self._database_motion("movePosition", 左手坐标姿态变量,
                                     linear_speed=末端线速度, angular_speed=末端角速度, timeout=timeout)

    def 右手坐标姿态运动(self, 右手坐标姿态变量, 末端线速度=None, 末端角速度=None, timeout=None):
        return self._database_motion("movePosition", 右手坐标姿态变量,
                                     linear_speed=末端线速度, angular_speed=末端角速度, timeout=timeout)

    def 单关节运动(self, 关节名称, 目标角度, 角速度=None, timeout=None):
        payload = {"cmd": "single_joint", "name": str(关节名称),
                   "value": self._validate_number("目标角度", 目标角度)}
        if 角速度 is not None:
            payload["speed"] = self._validate_number("角速度", 角速度)
        return self._wait_motion_done(self.JOINT_REQUEST, payload, "joint", timeout)

    def 单关节相对运动(self, 关节名称, 递增量, 角速度=None, timeout=None):
        """按当前关节角增加指定弧度，并等待关节运动完成反馈。"""
        payload = {"cmd": "single_joint", "name": str(关节名称),
                   "offset": self._validate_number("递增量", 递增量)}
        if 角速度 is not None:
            payload["speed"] = self._validate_number("角速度", 角速度)
        return self._wait_motion_done(self.JOINT_REQUEST, payload, "joint", timeout)

    def 读取当前全身所有关节角(self, timeout=None):
        """读取全部关节当前角度，返回 ``{关节名称: 角度(弧度)}``。"""
        response = self._publish_and_wait(
            self.JOINT_REQUEST, {"cmd": "get_current_angles"},
            {self.JOINT_RESPONSE}, "get_current_angles", timeout=timeout,
        )
        return response.get("result", {})

    def _read_current_end_pose(self, side, timeout=None):
        response = self._publish_and_wait(
            self.POSE_REQUEST, {"cmd": "get_current_pose", "side": side},
            {self.POSE_RESPONSE}, "get_current_pose", timeout=timeout,
        )
        return response.get("result")

    def 读取当前左手末端坐标姿态(self, timeout=None):
        """返回左手末端的位置和四元数姿态。"""
        return self._read_current_end_pose("left", timeout)

    def 读取当前右手末端坐标姿态(self, timeout=None):
        """返回右手末端的位置和四元数姿态。"""
        return self._read_current_end_pose("right", timeout)

    def 头部全局相机拍照(self, timeout=None):
        """驱动头部彩色全局相机拍照，返回图片的绝对保存路径。"""
        response = self._publish_and_wait(
            self.CAMERA_REQUEST, {"cmd": "capture", "camera": "kHeadColor"},
            {self.CAMERA_RESPONSE}, "capture", timeout=timeout,
        )
        return response.get("path") or response.get("result")

    def 语音输出(self, 文本内容):
        text = str(文本内容).strip()
        if not text:
            raise ValueError("语音内容不能为空")
        self._publish_and_wait(
            self.TTS_REQUEST, {"cmd": "speak", "text": text},
            {self.TTS_RESPONSE}, "speak",
        )
        return True

    def 同步数据读取(self, 变量名称, timeout=None):
        response = self._publish_and_wait(
            self.SYNC_REQUEST, {"cmd": "readData", "name": str(变量名称)},
            {self.SYNC_DATA}, "readData", name=str(变量名称), timeout=timeout,
        )
        return response.get("value")

    def 同步数据写入(self, 变量名称, 值, timeout=None):
        self._publish_and_wait(
            self.SYNC_REQUEST, {"cmd": "setData", "name": str(变量名称), "value": 值},
            {self.SYNC_RESPONSE}, "setData", name=str(变量名称), timeout=timeout,
        )
        return True

    def close(self):
        client, self._client = self._client, None
        if client is not None:
            client.loop_stop()
            client.disconnect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


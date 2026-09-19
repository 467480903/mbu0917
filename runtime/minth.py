#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minth G2 MQTT 控制客户端。

所有常规机器人运动命令直接发布 MQTT 并立刻返回本地发布状态。每个命令
方法都会打印实际下发的 JSON 报文，方便在运行程序时检查协议内容。

需要等待服务端数据响应的接口：readData、setData、MoveL、SAVE_PHOTO。
"""

import json
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt


MQTT_BROKER = "localhost"
MQTT_PORT = 1883

JOINTS_TOPIC = "/humanoid/joints/control"
COMMANDS_TOPIC = "/humanoid/commands/data"
DONE_TOPIC = "/humanoid/commands/done"
CAMERA_TOPIC = "/humanoid/camera/control"
POSITIONS_CTRL_TOPIC = "/humanoid/positions/control"
POSITIONS_DATA_TOPIC = "/humanoid/positions/data"
DATA_READ_TOPIC = "/humanoid/data/read"
DATA_WRITE_TOPIC = "/humanoid/data/write"
DATA_RESPONSE_TOPIC = "/humanoid/data/response"

DEFAULT_TIMEOUT = 15
_DETECT_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "detect", "detect.json",
)


class G2:
    """G2 机器人 MQTT 控制类。"""

    def __init__(
        self,
        broker=MQTT_BROKER,
        port=MQTT_PORT,
        timeout=DEFAULT_TIMEOUT,
        client_id=None,
    ):
        self.broker = broker
        self.port = port
        self.timeout = timeout
        self._connected = False
        self._done_event = threading.Event()
        self._done_cmd = None
        self._positions_event = threading.Event()
        self._positions_result = None
        self._data_lock = threading.Lock()
        self._data_ready = threading.Event()
        self._data_request_id = None
        self._data_response = None

        mqtt_client_id = client_id or f"minth_G2_{id(self)}"
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=mqtt_client_id,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(broker, port)
        self._client.loop_start()

        for _ in range(50):
            if self._connected:
                break
            threading.Event().wait(0.1)
        if not self._connected:
            self.close()
            raise ConnectionError(f"无法连接到 MQTT broker {broker}:{port}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"[Minth] MQTT 连接失败，返回码: {rc}")
            return
        client.subscribe(DONE_TOPIC, qos=2)
        client.subscribe(POSITIONS_DATA_TOPIC, qos=0)
        client.subscribe(DATA_RESPONSE_TOPIC, qos=0)
        self._connected = True
        print(f"[Minth] MQTT 已连接: {self.broker}:{self.port}")

    def _on_message(self, client, userdata, msg):
        if msg.topic == DONE_TOPIC:
            try:
                self._done_cmd = json.loads(msg.payload.decode()).get("cmd", "")
            except Exception:
                self._done_cmd = ""
            self._done_event.set()
            return

        if msg.topic == POSITIONS_DATA_TOPIC:
            try:
                self._positions_result = json.loads(msg.payload.decode())
                self._positions_event.set()
            except Exception:
                pass
            return

        if msg.topic == DATA_RESPONSE_TOPIC:
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except Exception:
                return
            if payload.get("request_id") == self._data_request_id:
                self._data_response = payload
                self._data_ready.set()

    def close(self):
        """停止 MQTT 网络循环并释放客户端连接。"""
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def DONE(self, message=None):
        """向 /humanoid/commands/done 发布外部程序完成通知。"""
        payload = {"command": "done"}
        if message is not None:
            payload["message"] = str(message)
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {DONE_TOPIC}: {message_json}")
        info = self._client.publish(DONE_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    # ── Modbus / Siemens S7 同步变量 ───────────────────────

    def readData(self, name):
        """读取 ``synch`` read 类型变量，等待服务端数据响应。"""
        with self._data_lock:
            request_id = uuid.uuid4().hex
            payload = {"command": "read", "name": name, "request_id": request_id}
            self._data_request_id = request_id
            self._data_response = None
            self._data_ready.clear()
            message_json = json.dumps(payload, ensure_ascii=False)
            print(f"[Minth] MQTT {DATA_READ_TOPIC}: {message_json}")
            info = self._client.publish(DATA_READ_TOPIC, message_json, qos=0)
            if getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
                return None
            if not self._data_ready.wait(timeout=self.timeout):
                print(f"[Minth] readData({name}) 超时")
                return None
            response = self._data_response or {}
            value = response.get("value") if response.get("command") == "read" else None
            print(f"[Minth] readData({name}) = {value}")
            return value

    def setData(self, name, value):
        """设置 ``synch`` write 类型变量，等待服务端接受确认。"""
        with self._data_lock:
            request_id = uuid.uuid4().hex
            payload = {
                "command": "write",
                "name": name,
                "value": value,
                "request_id": request_id,
            }
            self._data_request_id = request_id
            self._data_response = None
            self._data_ready.clear()
            message_json = json.dumps(payload, ensure_ascii=False)
            print(f"[Minth] MQTT {DATA_WRITE_TOPIC}: {message_json}")
            info = self._client.publish(DATA_WRITE_TOPIC, message_json, qos=0)
            if getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
                return False
            if not self._data_ready.wait(timeout=self.timeout):
                print(f"[Minth] setData({name}, {value}) 超时")
                return False
            response = self._data_response or {}
            accepted = response.get("command") == "write" and response.get("success") is True
            print(f"[Minth] setData({name}, {value}): {'已接收' if accepted else '被拒绝'}")
            return accepted

    # ── 机器人运动命令：直接发布，不等待 done ─────────────

    def GO(self, num):
        """导航到地图点位。报文：{"command":"go","data":<点位编号>}。"""
        payload = {"command": "go", "data": num}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def GO_NOWAIT(self, num):
        """异步导航。报文：{"command":"go_nowait","data":<点位编号>}。"""
        payload = {"command": "go_nowait", "data": num}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def WBC(self, name, speed=None):
        """全身姿态。报文：{"command":"WBC","data":"名称","speed":可选速度}。"""
        payload = {"command": "WBC", "data": name}
        if speed is not None:
            payload["speed"] = speed
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def ARMS(self, name, speed=None):
        """双臂姿态。报文：{"command":"arms","data":"名称","speed":可选速度}。"""
        payload = {"command": "arms", "data": name}
        if speed is not None:
            payload["speed"] = speed
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def LEFT(self, name, speed=None):
        """左臂姿态。报文：{"command":"left","data":"名称","speed":可选速度}。"""
        payload = {"command": "left", "data": name}
        if speed is not None:
            payload["speed"] = speed
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def RIGHT(self, name, speed=None):
        """右臂姿态。报文：{"command":"right","data":"名称","speed":可选速度}。"""
        payload = {"command": "right", "data": name}
        if speed is not None:
            payload["speed"] = speed
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def HEAD(self, name):
        """头部姿态。报文：{"command":"head","data":"名称"}。"""
        payload = {"command": "head", "data": name}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def WAIST(self, name):
        """腰部姿态。报文：{"command":"waist","data":"名称"}。"""
        payload = {"command": "waist", "data": name}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def JOINT(self, name, offset=None, value=None):
        """单关节命令。报文含 command=joint 和 name/value 或 name/offset。"""
        if value is None and offset is None:
            print("[Minth] JOINT 需要 offset 或 value")
            return False
        data = {"name": name}
        if value is not None:
            data["value"] = value
        else:
            data["offset"] = offset
        payload = {"command": "joint", "data": data}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {JOINTS_TOPIC}: {message_json}")
        info = self._client.publish(JOINTS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def OFFSET(self, data):
        """末端偏移。报文：{"command":"offset_move","data":{偏移字段}}。"""
        payload = {"command": "offset_move", "data": data}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def REL(self, data):
        """底盘相对移动。报文：{"command":"go_rel","data":{x,y,yaw_rad}}。"""
        payload = {"command": "go_rel", "data": data}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def REL_ODOM(self, data, speed=0.25):
        """里程计相对移动。报文：{"command":"go_rel_odom","data":...,"speed":...}。"""
        payload = {"command": "go_rel_odom", "data": data, "speed": speed}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def REL_NOWAIT(self, data):
        """异步底盘移动。报文：{"command":"go_rel_nowait","data":...}。"""
        payload = {"command": "go_rel_nowait", "data": data}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def TTS(self, text):
        """语音。报文：{"command":"tts","data":"文本"}。"""
        payload = {"command": "tts", "data": text}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    def GRIPPER(self, data):
        """夹爪。报文：{"command":"grab","data":{"left"/"right":位置}}。"""
        payload = {"command": "grab", "data": data}
        message_json = json.dumps(payload, ensure_ascii=False)
        print(f"[Minth] MQTT {COMMANDS_TOPIC}: {message_json}")
        info = self._client.publish(COMMANDS_TOPIC, message_json, qos=2)
        return getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) == mqtt.MQTT_ERR_SUCCESS

    # ── 坐标点位与相机 ─────────────────────────────────────

    def MoveL(self, position, offset=None):
        """运动到右臂保存位姿，等待 /humanoid/positions/data 结果。"""
        payload = {"command": "goto", "data": {"type": "right", "name": position}}
        if offset is not None:
            payload["data"]["offset"] = offset
        message_json = json.dumps(payload, ensure_ascii=False)
        self._positions_event.clear()
        self._positions_result = None
        print(f"[Minth] MQTT {POSITIONS_CTRL_TOPIC}: {message_json}")
        info = self._client.publish(POSITIONS_CTRL_TOPIC, message_json, qos=0)
        if getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
            return False
        if not self._positions_event.wait(timeout=30):
            print(f"[Minth] MoveL({position}) 超时")
            return False
        data = (self._positions_result or {}).get("data", {})
        print(f"[Minth] MoveL({position}): {data.get('message', '')}")
        return data.get("success", False)

    def SAVE_PHOTO(self, cameras=None, timeout=20):
        """保存指定相机图片，等待 save_photo 完成通知。"""
        if cameras is None:
            cameras = ["kHeadColor", "kHeadDepth"]
        if not isinstance(cameras, (list, tuple)) or not cameras:
            print("[Minth] SAVE_PHOTO 的 cameras 必须是非空列表")
            return False
        payload = {"command": "save_photo", "cameras": list(cameras)}
        message_json = json.dumps(payload, ensure_ascii=False)
        self._done_cmd = None
        self._done_event.clear()
        print(f"[Minth] MQTT {CAMERA_TOPIC}: {message_json}")
        info = self._client.publish(CAMERA_TOPIC, message_json, qos=2)
        if getattr(info, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._done_event.wait(timeout=deadline - time.time()):
                self._done_event.clear()
                if self._done_cmd == "save_photo":
                    return True
        return False

    def WAIST_CORRECT(self, detect_json=None, joint_name="idx05_body_joint5"):
        """读取检测角度并直接发布指定腰部关节的增量命令。"""
        path = detect_json or _DETECT_JSON
        if not os.path.isfile(path):
            print(f"[Minth] 检测结果文件不存在: {path}")
            return False
        try:
            with open(path, "r", encoding="utf-8") as source:
                angle = -float(json.load(source).get("angle_rad"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"[Minth] 读取 angle_rad 失败: {exc}")
            return False
        return self.JOINT(joint_name, offset=angle)


class Minth:
    """Minth 命名空间，仅提供 G2 控制类。"""

    G2 = G2

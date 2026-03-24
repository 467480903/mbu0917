#!/usr/bin/env python3
"""独立 Apriltag MQTT 服务；由 .venv-apriltag Python 启动。"""

import json
import os

import paho.mqtt.client as mqtt

from apriltag_controller import ApriltagController


class ApriltagApplication:
    """监听图片识别请求，不加载 GDK。"""

    def __init__(self):
        self.service_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_dir = os.path.dirname(self.service_dir)
        with open(os.path.join(self.service_dir, "config.json"), encoding="utf-8") as stream:
            self.config = json.load(stream)
        topic = self.config["topics"]["apriltag"]
        image_dir = self.config.get("paths", {}).get("images", "images")
        if not os.path.isabs(image_dir):
            image_dir = os.path.join(self.project_dir, image_dir)
        self.request_topic = topic["request"]
        self.response_topic = topic["response"]
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"apriltag_service_{os.getpid()}")
        self.controller = ApriltagController(
            self.client, self.response_topic, image_dir)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _publish(self, payload):
        self.client.publish(
            self.response_topic, json.dumps(payload, ensure_ascii=False), qos=2)

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties=None):
        if getattr(reason_code, "is_failure", reason_code != 0):
            print(f"[Apriltag] MQTT 连接失败: {reason_code}")
            return
        client.subscribe(self.request_topic, qos=2)
        print(f"[Apriltag] 已订阅 {self.request_topic}")

    def _on_message(self, _client, _userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            command = payload.get("cmd")
            if command == "detect_file":
                tags = self.controller.detect_file(payload["file"])
                filename = payload["file"]
            elif command in ("detect_saved", "detect_head"):
                filename = payload.get("file", "kHeadColor-latest.jpg")
                tags = self.controller.detect_saved_image(filename)
            else:
                raise ValueError(f"未知 Apriltag 命令: {command}")
            self._publish({"cmd": command, "time": payload.get("time"),
                           "success": True, "file": filename, "result": tags})
            print(f"[Apriltag] {filename}: 检测到 {len(tags)} 个标签")
        except Exception as error:
            self._publish({"cmd": payload.get("cmd") if 'payload' in locals() else None,
                           "time": payload.get("time") if 'payload' in locals() else None,
                           "success": False, "error": str(error)})
            print(f"[Apriltag] 请求失败: {error}")

    def run(self):
        if not self.controller.init():
            raise RuntimeError("Apriltag 检测器初始化失败")
        broker = self.config["mqtt"]["broker"]
        port = int(self.config["mqtt"]["port"])
        self.client.connect(broker, port, 60)
        print(f"[Apriltag] 独立服务已启动，MQTT={broker}:{port}")
        self.client.loop_forever()


if __name__ == "__main__":
    ApriltagApplication().run()

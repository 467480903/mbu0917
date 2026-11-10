#!/usr/bin/env python3
"""真实 MQTT 单路相机调用（不运动）；可选 capture / status / stop 等命令。"""
import argparse
import json
import threading
import uuid
import paho.mqtt.client as mqtt

parser = argparse.ArgumentParser()
parser.add_argument("--camera", default="kHeadColor")
parser.add_argument("--cmd", default="capture")
args = parser.parse_args()
done, request_id = threading.Event(), uuid.uuid4().hex
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
def connected(client, userdata, flags, reason, properties):
    client.subscribe(f"/humanoid/camera/{args.camera}/response", qos=1)
def subscribed(client, userdata, mid, reasons, properties):
    client.publish(f"/humanoid/camera/{args.camera}/request", json.dumps({"cmd": args.cmd, "time": request_id}), qos=1)
def received(client, userdata, message):
    result = json.loads(message.payload)
    if result.get("time") == request_id:
        image = result.pop("image", "")
        print(json.dumps(result, ensure_ascii=False), "image_bytes=", len(image), flush=True)
        done.set()
client.on_connect, client.on_subscribe, client.on_message = connected, subscribed, received
client.connect("localhost", 1883)
client.loop_start()
try:
    if not done.wait(20):
        raise TimeoutError("相机服务未回包")
finally:
    client.disconnect()
    client.loop_stop()

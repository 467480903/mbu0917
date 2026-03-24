#!/usr/bin/env python3
"""拍摄当前头部 RGB 图片，并请求独立 Apriltag 服务识别。"""
import json, threading, time
import paho.mqtt.client as mqtt
done = threading.Event()
def on_connect(client, _u, _f, _r, _p=None):
    client.subscribe("/humanoid/camera/response/"); client.subscribe("/humanoid/apriltag/response/")
    client.publish("/humanoid/camera/request/", json.dumps({"cmd":"capture","camera":"kHeadColor","time":str(time.time_ns())}))
def on_message(client, _u, message):
    data = json.loads(message.payload.decode())
    if message.topic.endswith("camera/response/") and data.get("success"):
        client.publish("/humanoid/apriltag/request/", json.dumps({"cmd":"detect_head","time":str(time.time_ns())}))
    elif message.topic.endswith("apriltag/response/"):
        print(json.dumps(data, ensure_ascii=False, indent=2)); done.set()
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="test_head_rgb_apriltag")
client.on_connect = on_connect; client.on_message = on_message
client.connect("localhost", 1883, 60); client.loop_start()
done.wait(15); client.loop_stop(); client.disconnect()
if not done.is_set(): raise TimeoutError("Apriltag 识别超时")

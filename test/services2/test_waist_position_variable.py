#!/usr/bin/env python3
"""手动测试已保存的腰部姿态变量定位；实体运动，禁止自动执行。"""
import json
import threading
import paho.mqtt.client as mqtt
VARIABLE_NAME = "腰部测试位"
finished = threading.Event()
def on_message(_client, _userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    if data.get("command") == "goto_result":
        print(data)
        finished.set()
client = mqtt.Client(client_id="test_waist_position_variable")
client.on_message = on_message
client.connect("localhost", 1883)
client.subscribe("/humanoid/positions/data"); client.loop_start()
input(f"确认腰部周围安全，并已保存变量“{VARIABLE_NAME}”后按回车执行：")
request = {"command": "goto", "data": {"type": "waist", "name": VARIABLE_NAME}}
client.publish("/humanoid/positions/control", json.dumps(request, ensure_ascii=False))
finished.wait(60); client.loop_stop(); client.disconnect()

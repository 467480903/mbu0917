#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_camera_controller.py - 摄像头控制器测试

测试 CameraController.capture() 函数

不涉及机器人运动，可直接运行
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))

# 加载配置
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '../../serivces2/config.json')
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 从配置获取参数
MQTT_BROKER = config["mqtt"]["broker"]
MQTT_PORT = config["mqtt"]["port"]
TOPIC_CAMERA_RESPONSE = config["topics"]["camera"]["response"]
IMAGE_SAVE_DIR = os.path.join(os.path.dirname(__file__), '../../images')

print("警告：需要 GDK 环境！")
print("运行前请执行: source ~/app/env.bash")

import agibot_gdk
import paho.mqtt.client as mqtt
from camera_controller import CameraController

# 初始化 GDK
agibot_gdk.gdk_init()
camera = agibot_gdk.Camera()

# 初始化 MQTT
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# 创建控制器
ctrl = CameraController(camera, mqtt_client, TOPIC_CAMERA_RESPONSE, IMAGE_SAVE_DIR)

# 测试拍照
filename = ctrl.capture(agibot_gdk, "kHeadColor")
print(f"拍照结果: {filename}")

mqtt_client.loop_stop()
mqtt_client.disconnect()
print("测试完成！")

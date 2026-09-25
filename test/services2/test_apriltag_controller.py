#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_apriltag_controller.py - Apriltag 控制器测试

测试 ApriltagController.detect_image() 函数

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
TOPIC_APRILTAG_RESPONSE = config["topics"]["apriltag"]["response"]
IMAGE_SAVE_DIR = os.path.join(os.path.dirname(__file__), '../../images')

import paho.mqtt.client as mqtt
from apriltag_controller import ApriltagController

# 初始化 MQTT
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# 创建控制器
ctrl = ApriltagController(mqtt_client, TOPIC_APRILTAG_RESPONSE, IMAGE_SAVE_DIR)
ctrl.init()

# 测试检测（需要提前拍照）
import cv2
test_image = os.path.join(IMAGE_SAVE_DIR, "kHeadColor_latest.jpg")
if os.path.exists(test_image):
    tags = ctrl.detect_file(test_image)
    print(f"检测到 {len(tags)} 个标签:")
    for tag in tags:
        print(f"  ID={tag['id']} center={tag['center']}")
else:
    print(f"测试图片不存在: {test_image}")

mqtt_client.loop_stop()
mqtt_client.disconnect()
print("测试完成！")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_end_effector_controller.py - 末端控制器测试

测试 EndEffectorController.left_gripper() 和 right_gripper() 函数

警告：涉及机器人运动，执行前需手动确认！
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
TOPIC_EE_RESPONSE = config["topics"]["ee"]["response"]
TOPIC_DONE = config["topics"]["done"]

print("警告：此测试涉及机器人运动！")
input("按回车继续...")

import agibot_gdk
import paho.mqtt.client as mqtt
from end_effector_controller import EndEffectorController

# 初始化 GDK
agibot_gdk.gdk_init()
robot = agibot_gdk.Robot()

# 初始化 MQTT
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# 创建控制器
ctrl = EndEffectorController(robot, mqtt_client, TOPIC_EE_RESPONSE, TOPIC_DONE)

# 测试爪子张开/闭合
ctrl.left_gripper_action("open")
ctrl.right_gripper_action("open")

mqtt_client.loop_stop()
mqtt_client.disconnect()
print("测试完成！")

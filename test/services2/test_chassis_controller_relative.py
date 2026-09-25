#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_chassis_controller_relative.py - 底盘控制器相对运动测试

测试 ChassisController.relative_move() 函数

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
TOPIC_BASE_RESPONSE = config["topics"]["base"]["response"]
TOPIC_DONE = config["topics"]["done"]

print("警告：此测试涉及机器人运动！")
input("按回车继续...")

import agibot_gdk
import paho.mqtt.client as mqtt
from chassis_controller import ChassisController

# 初始化 GDK
agibot_gdk.gdk_init()
pnc = agibot_gdk.Pnc()
slam = agibot_gdk.Slam()

# 初始化 MQTT
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

# 创建控制器
ctrl = ChassisController(pnc, slam, mqtt_client, TOPIC_BASE_RESPONSE, TOPIC_DONE)

# 测试相对运动：前进 100mm
ctrl.relative_move(agibot_gdk, 100, 0, 0)

mqtt_client.loop_stop()
mqtt_client.disconnect()
print("测试完成！")

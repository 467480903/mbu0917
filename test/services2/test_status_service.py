#!/usr/bin/env bash
''':'
source ~/app/env.sh /home/agi/app
exec python3 "$0" "$@"
'''
# -*- coding: utf-8 -*-
"""
test_status_service.py — 状态发布器服务启动程序（供 test_status_observer.sh 观察）

职责：
  - 初始化 GDK（Robot + Slam）
  - 创建 MQTT 客户端并连接 broker
  - 实例化 StatusPublisher，以 10Hz 周期把机器人实时状态发布到 /humanoid/status/data/

运行（需要 GDK 环境，不涉及机器人运动）：
  ./test/services2/test_status_service.py
  # 等价于：source ~/app/env.sh /home/agi/app && python3 test/services2/test_status_service.py
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))

# 加载配置
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '../../serivces2/config.json')
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

BROKER = config["mqtt"]["broker"]
PORT = config["mqtt"]["port"]
TOPIC_STATUS = config["topics"]["status"]["data"]
RATE_HZ = 10.0


def main():
    import agibot_gdk
    import paho.mqtt.client as mqtt
    from status_publisher import StatusPublisher

    # 初始化 GDK
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("[GDK] 初始化失败")
        sys.exit(1)
    print("[GDK] 初始化成功")
    robot = agibot_gdk.Robot()
    slam = agibot_gdk.Slam()
    time.sleep(2)  # 等待 DDS 连接就绪

    # 创建 MQTT 客户端（状态发布器为纯 publisher，无需订阅）
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"humanoid_status_{os.getpid()}",
    )
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    print(f"[MQTT] 已连接 {BROKER}:{PORT}")

    # 启动状态发布器
    publisher = StatusPublisher(robot, slam, client, TOPIC_STATUS, rate_hz=RATE_HZ)
    publisher.start()

    print(f"[状态] 状态发布服务已启动，主题: {TOPIC_STATUS}，周期: {RATE_HZ}Hz")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
    finally:
        publisher.stop()
        client.loop_stop()
        client.disconnect()
        print("[状态] 服务已停止")


if __name__ == "__main__":
    main()

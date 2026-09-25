#!/data/wxf/mbu0917/.venv-sync/bin/python3
# -*- coding: utf-8 -*-
"""
test_sync_service.py — 启动数据同步服务（供 test_sync_s7.sh / test_sync_modbus.sh 调用）

职责：
  - 创建 MQTT 客户端并连接 broker
  - 实例化 SyncController（读取 datas/ 下的 modbus.json / s7.json）
  - 订阅 /humanoid/sync/request/，把 readData / setData 报文分发给控制器
  - 启动后台轮询线程（周期读只读点位 + 写回 isChanged==1 的写点位）

运行（使用 .venv-sync 环境，shebang 已指向该环境）：
  ./test/services2/test_sync_service.py
  # 或
  source .venv-sync/bin/activate && python3 test/services2/test_sync_service.py

说明：
  设备（S7/Modbus）不可达时，轮询线程只打印错误日志，服务不会退出。
"""

import os
import sys
import json

import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from sync_controller import SyncController

BROKER = "localhost"
PORT = 1883
REQ_TOPIC = "/humanoid/sync/request/"
DATA_TOPIC = "/humanoid/sync/data/"
RESP_TOPIC = "/humanoid/sync/response/"
CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../datas'))


def on_connect(client, userdata, flags, rc, properties=None):
    """连接成功后订阅请求主题"""
    if rc == 0:
        print(f"[MQTT] 已连接 {BROKER}:{PORT}")
        client.subscribe(REQ_TOPIC, qos=2)
        print(f"[MQTT] 已订阅 {REQ_TOPIC}")
    else:
        print(f"[MQTT] 连接失败 rc={rc}")


def on_message(client, userdata, msg):
    """收到 MQTT 报文，按 cmd 分发给控制器"""
    controller = userdata
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception as e:
        print(f"[Sync] 非法报文: {e}")
        return
    cmd = payload.get("cmd")
    name = payload.get("name")
    if cmd == "readData":
        value = controller.read_data(name)
        print(f"[Sync] readData({name}) = {value}")
    elif cmd == "setData":
        ok = controller.set_data(name, payload.get("value"))
        print(f"[Sync] setData({name}, {payload.get('value')}) -> {ok}")
    else:
        print(f"[Sync] 未知命令: {cmd}")


def main():
    # 1. 实例化控制器，加载配置并启动轮询线程（mqtt_client 稍后注入）
    controller = SyncController(None, RESP_TOPIC, CONFIG_DIR, topic_data=DATA_TOPIC)
    controller.load_config()
    controller.start_polling()

    # 2. 创建 MQTT 客户端，把控制器作为 userdata 传给回调
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"humanoid_sync_{os.getpid()}",
    )
    client.user_data_set(controller)
    client.on_connect = on_connect
    client.on_message = on_message
    controller.mqtt_client = client

    # 3. 连接 broker 并进入消息循环
    client.connect(BROKER, PORT, 60)
    print("[Sync] 数据同步服务已启动，等待命令...")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
    finally:
        controller.stop_polling()
        client.disconnect()
        print("[Sync] 服务已停止")


if __name__ == "__main__":
    main()

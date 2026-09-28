#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_db_service.py — 数据库控制器服务启动程序（供 .sh 观察脚本调用）

职责：
  - 加载 DatabaseController（仅 CRUD，不注入运动控制器）
  - 订阅 /humanoid/db/request/，把 增删改读取/运动 命令分发给控制器
  - 把结果发布到 /humanoid/db/response/

运行（默认系统 python，需 paho-mqtt）：
  python3 test/services2/test_db_service.py [数据库路径] [broker] [port] [ws]
  # 默认使用 /tmp 下的临时测试库，不污染 datas/robot_data.db
  # 默认连接 10.20.17.77:1883 (TCP)；第 3 个参数传 ws 则走 WebSocket（路径 /mqtt）
  #   例：python3 test/services2/test_db_service.py /tmp/test.db 127.0.0.1 9111      # TCP
  #       python3 test/services2/test_db_service.py /tmp/test.db 10.20.17.77 9001 ws # WS
"""

import os
import sys
import json

import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../serivces2'))
from database_controller import DatabaseController

BROKER = "10.20.17.77"
PORT = 1883
REQ_TOPIC = "/humanoid/db/request/"
RESP_TOPIC = "/humanoid/db/response/"


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[MQTT] 已连接 {BROKER}:{PORT}")
        client.subscribe(REQ_TOPIC, qos=2)
        print(f"[MQTT] 已订阅 {REQ_TOPIC}")
    else:
        print(f"[MQTT] 连接失败 rc={rc}")


def dispatch(db, p):
    cmd = p.get("cmd")
    t = p.get("type")
    name = p.get("name")
    value = p.get("value")
    if cmd == "addJoint":
        return db.add_joints(t, name, value)
    if cmd == "updateJoint":
        return db.update_joints(t, name, value)
    if cmd == "deleteJoint":
        return db.delete_joints(t, name)
    if cmd == "getJoints":
        return db.get_joints()
    if cmd == "addPosition":
        return db.add_positions(t, name, value)
    if cmd == "updatePosition":
        return db.update_positions(t, name, value)
    if cmd == "deletePosition":
        return db.delete_positions(t, name)
    if cmd == "getPositions":
        return db.get_positions()
    if cmd == "addMapPoint":
        return db.add_map_point(name, p.get("position"), p.get("orientation"))
    if cmd == "updateMapPoint":
        return db.update_map_point(name, p.get("position"), p.get("orientation"))
    if cmd == "deleteMapPoint":
        return db.delete_map_point(name)
    if cmd == "getMapPoints":
        return db.get_map_points()
    # 运动到位置：功能存在，但需注入运动控制器，此处未注入 → 返回 False
    if cmd == "moveJoint":
        return db.move_joints(name)
    if cmd == "movePosition":
        return db.move_position(name)
    if cmd == "moveMapPoint":
        return db.move_map_point(name)
    return f"unknown cmd: {cmd}"


def on_message(client, userdata, msg):
    db = userdata
    print(msg)
    try:
        p = json.loads(msg.payload.decode("utf-8"))
    except Exception as e:
        print(f"[DB] 非法报文: {e}")
        return
    cmd = p.get("cmd")
    result = dispatch(db, p)
    client.publish(RESP_TOPIC, json.dumps({"cmd": cmd, "result": result}, ensure_ascii=False))
    print(f"[DB] {cmd} -> {result}")


def main():
    # 用法: python3 test_db_service.py [数据库路径] [broker] [port] [ws]
    #   默认:             /tmp/database_test.db + 10.20.17.77:1883 (TCP)
    #   指定 broker/port:  python3 test_db_service.py /tmp/test.db 127.0.0.1 9111
    #   WebSocket 模式:    python3 test_db_service.py /tmp/test.db 10.20.17.77 9001 ws
    global BROKER, PORT
    args = sys.argv[1:]
    db_path = args[0] if len(args) > 0 else os.path.join("/tmp", "database_test.db")
    if len(args) > 1:
        BROKER = args[1]
    if len(args) > 2:
        PORT = int(args[2])
    use_ws = len(args) > 3 and args[3].lower() in ("ws", "websocket", "websockets")

    db = DatabaseController(db_path)
    db.init()

    if use_ws:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"humanoid_db_{os.getpid()}",
                             transport="websockets")
        client.ws_set_options(path="/mqtt")
    else:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"humanoid_db_{os.getpid()}")
    client.user_data_set(db)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    print(f"[DB] 数据库服务已启动（库: {db_path}），等待命令...")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

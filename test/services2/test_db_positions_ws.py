#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_db_positions_ws.py — 数据库控制器「坐标姿态」增删改读取 观察脚本
（test_db_positions.sh 的 Python + MQTT WebSocket 版本）

与 test_db_positions.sh 的差别：
  - 不再依赖 mosquitto_pub / mosquitto_sub 命令行工具
  - 通过 WebSocket 端口连接（与 web/test/database/positions.html 页面相同的链路）

注意（2026-09-28 实测结论）：
  - 机器人上 9001 的 WebSocket 端点带有"主题白名单"（root 权限配置，agi 用户读不到；
    9001 的监听特征与 mosquitto websockets listener 一致，且 /etc/mosquitto/acl/ 目录
    存在，很可能是系统 mosquitto 的 websockets listener + 每监听器 ACL 白名单；
    可用 `sudo ss -tlnp | grep 9001`、sudo cat /etc/mosquitto/conf.d/robot-web-console.conf 确认）。
    白名单只放行 /humanoid/status/data、/humanoid/modbus/data 等旧控制台主题；
    /humanoid/db/# 和 /diag/# 等全部被过滤。
    因此本脚本连得上 9001（CONNECT/SUBSCRIBE/PUBLISH 均正常），但收不到 db 响应。
  - 根因与 web/test/database/positions.html "收不到响应" 完全相同。
  - 端到端验证方法（无需 root）：临时起一个用户态 mosquitto（WS+TCP 双 listener），
    test_db_service.py 连其 TCP 端口，本脚本连其 WS 端口即可全流程跑通，例如：
      /usr/sbin/mosquitto -c /tmp/mosq_ws.conf -d          # ws 9110 + tcp 9111
      python3 test/services2/test_db_service.py /tmp/ws_e2e.db 127.0.0.1 9111
      python3 test/services2/test_db_positions_ws.py 127.0.0.1 9110

前置：先运行 python3 test/services2/test_db_service.py

运行（默认系统 python，需 paho-mqtt）：
  python3 test/services2/test_db_positions_ws.py [broker] [port]
  # 默认 broker=10.20.17.77，port=9001（WebSocket，路径 /mqtt）
"""

import json
import sys
import threading
import time

import paho.mqtt.client as mqtt

BROKER = "10.20.17.77"
PORT = 9001            # WebSocket 端口（mosquitto websockets listener）
WS_PATH = "/mqtt"      # mosquitto WebSocket 默认路径，与 Paho JS 页面一致
REQ_TOPIC = "/humanoid/db/request/"
RESP_TOPIC = "/humanoid/db/response/"

# 请求序列（与 test_db_positions.sh 完全一致）
REQUESTS = [
    {"cmd": "addPosition",    "type": "left", "name": "b_pose", "value": {"x": 0.5, "y": 0.2, "z": 0.3}},
    {"cmd": "addPosition",    "type": "left", "name": "a_pose", "value": {"x": 0.1, "y": 0.2, "z": 0.3}},
    {"cmd": "getPositions"},
    {"cmd": "updatePosition", "type": "left", "name": "b_pose", "value": {"x": 0.9, "y": 0.2, "z": 0.3}},
    {"cmd": "getPositions"},
    {"cmd": "deletePosition", "type": "left", "name": "a_pose"},
    {"cmd": "getPositions"},
]

responses = []                # 收到的响应列表
lock = threading.Lock()
connected = threading.Event()
done = threading.Event()


def on_connect(client, userdata, flags, rc, properties=None):
    """连接成功后订阅响应主题（签名兼容 paho 1.x / 2.x）"""
    if rc == 0:
        print(f"[MQTT] 已连接 ws://{BROKER}:{PORT}{WS_PATH}")
        client.subscribe(RESP_TOPIC, qos=2)
        print(f"[MQTT] 已订阅 {RESP_TOPIC}")
        connected.set()
    else:
        print(f"[MQTT] 连接失败 rc={rc}")


def on_disconnect(client, userdata, *args):
    connected.clear()


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception as exc:
        print(f"[收] 非法报文: {exc}")
        return
    with lock:
        responses.append(payload)
    print(f"[收] {json.dumps(payload, ensure_ascii=False)}")
    if len(responses) >= len(REQUESTS):
        done.set()


def main():
    global BROKER, PORT
    if len(sys.argv) > 1:
        BROKER = sys.argv[1]
    if len(sys.argv) > 2:
        PORT = int(sys.argv[2])

    client_id = f"db_positions_ws_{int(time.time())}"
    try:
        # paho-mqtt 2.x
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=client_id, transport="websockets")
    except AttributeError:
        try:
            # 兼容 paho-mqtt 1.6+
            client = mqtt.Client(client_id=client_id, transport="websockets")
        except TypeError:
            print("[错误] paho-mqtt 版本过低（<1.6），不支持 WebSocket 传输，"
                  "请先升级: pip3 install --upgrade paho-mqtt")
            sys.exit(1)
    client.ws_set_options(path=WS_PATH)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:
        client.connect(BROKER, PORT, 60)
    except Exception as exc:
        print(f"[MQTT] 无法连接 {BROKER}:{PORT} -> {exc}")
        sys.exit(1)

    client.loop_start()
    try:
        if not connected.wait(timeout=5):
            print("[MQTT] 连接超时，请确认 Broker 已开启 WebSocket 9001 端口")
            sys.exit(1)

        total = len(REQUESTS)
        for i, req in enumerate(REQUESTS, 1):
            body = json.dumps(req, ensure_ascii=False)
            print(f"[发 {i}/{total}] {body}")
            client.publish(REQ_TOPIC, body, qos=2)
            time.sleep(0.3)  # 逐条发送，保持顺序、便于观察日志

        # 等待全部响应（每个请求对应一条响应）
        if not done.wait(timeout=5):
            with lock:
                got = len(responses)
            print(f"[MQTT] 等待响应超时（已收 {got}/{total} 条）")

        print("=== 坐标姿态 响应 ===")
        with lock:
            for item in responses:
                print(json.dumps(item, ensure_ascii=False))
        with lock:
            got = len(responses)
        print(f"共收到 {got}/{total} 条响应")
    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# 数据库控制器 - 坐标姿态 增删改读取 观察脚本
# 前置：先运行 python3 test/services2/test_db_service.py
BROKER="localhost"; PORT=1883
REQ="/humanoid/db/request/"; RESP="/humanoid/db/response/"
pub() { env -u LD_LIBRARY_PATH /usr/bin/mosquitto_pub -h "$BROKER" -p "$PORT" -q 2 -t "$REQ" -m "$1"; }

env -u LD_LIBRARY_PATH /usr/bin/mosquitto_sub -h "$BROKER" -p "$PORT" -q 2 -t "$RESP" > /tmp/db_positions.log &
SUB=$!
sleep 1
pub '{"cmd":"addPosition","type":"left","name":"b_pose","value":{"x":0.5,"y":0.2,"z":0.3}}'
pub '{"cmd":"addPosition","type":"left","name":"a_pose","value":{"x":0.1,"y":0.2,"z":0.3}}'
pub '{"cmd":"getPositions"}'
pub '{"cmd":"updatePosition","type":"left","name":"b_pose","value":{"x":0.9,"y":0.2,"z":0.3}}'
pub '{"cmd":"getPositions"}'
pub '{"cmd":"deletePosition","type":"left","name":"a_pose"}'
pub '{"cmd":"getPositions"}'
sleep 1
kill $SUB 2>/dev/null
echo "=== 坐标姿态 响应 ==="
cat /tmp/db_positions.log

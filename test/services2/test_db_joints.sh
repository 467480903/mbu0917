#!/usr/bin/env bash
# 数据库控制器 - 关节角 增删改读取 观察脚本
# 前置：先运行 python3 test/services2/test_db_service.py
BROKER="localhost"; PORT=1883
REQ="/humanoid/db/request/"; RESP="/humanoid/db/response/"
pub() { env -u LD_LIBRARY_PATH /usr/bin/mosquitto_pub -h "$BROKER" -p "$PORT" -q 2 -t "$REQ" -m "$1"; }

env -u LD_LIBRARY_PATH /usr/bin/mosquitto_sub -h "$BROKER" -p "$PORT" -q 2 -t "$RESP" > /tmp/db_joints.log &
SUB=$!
sleep 1
pub '{"cmd":"addJoint","type":"head","name":"b_joint","value":{"idx11_head_joint1":0.1}}'
pub '{"cmd":"addJoint","type":"head","name":"a_joint","value":{"idx11_head_joint1":0.2}}'
pub '{"cmd":"getJoints"}'
pub '{"cmd":"updateJoint","type":"head","name":"b_joint","value":{"idx11_head_joint1":0.9}}'
pub '{"cmd":"getJoints"}'
pub '{"cmd":"deleteJoint","type":"head","name":"a_joint"}'
pub '{"cmd":"getJoints"}'
sleep 1
kill $SUB 2>/dev/null
echo "=== 关节角 响应 ==="
cat /tmp/db_joints.log

#!/usr/bin/env bash
# 数据库控制器 - 地图点位 增删改读取 观察脚本
# 前置：先运行 python3 test/services2/test_db_service.py
BROKER="localhost"; PORT=1883
REQ="/humanoid/db/request/"; RESP="/humanoid/db/response/"
pub() { env -u LD_LIBRARY_PATH /usr/bin/mosquitto_pub -h "$BROKER" -p "$PORT" -q 2 -t "$REQ" -m "$1"; }

env -u LD_LIBRARY_PATH /usr/bin/mosquitto_sub -h "$BROKER" -p "$PORT" -q 2 -t "$RESP" > /tmp/db_map_points.log &
SUB=$!
sleep 1
pub '{"cmd":"addMapPoint","name":"b_point","position":[1.0,2.0,0.0],"orientation":[0,0,0,1]}'
pub '{"cmd":"addMapPoint","name":"a_point","position":[3.0,4.0,0.0],"orientation":[0,0,0,1]}'
pub '{"cmd":"getMapPoints"}'
pub '{"cmd":"updateMapPoint","name":"b_point","position":[9.0,8.0,0.0],"orientation":[0,0,0,1]}'
pub '{"cmd":"getMapPoints"}'
pub '{"cmd":"deleteMapPoint","name":"a_point"}'
pub '{"cmd":"getMapPoints"}'
sleep 1
kill $SUB 2>/dev/null
echo "=== 地图点位 响应 ==="
cat /tmp/db_map_points.log

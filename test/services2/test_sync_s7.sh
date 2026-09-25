#!/usr/bin/env bash
# S7 点位读写测试（MQTT）
#   setData 修改可写点位（isChanged=1，由数据同步控制器周期写回 PLC）
#   readData 读取点位，结果发布到 /humanoid/sync/data/
# 前置条件：mosquitto broker 已启动；数据同步服务（.venv-sync 环境）已运行。
set -u

BROKER="localhost"
PORT=1883
REQ_TOPIC="/humanoid/sync/request/"
DATA_TOPIC="/humanoid/sync/data/"

mqtt_pub() {
    env -u LD_LIBRARY_PATH /usr/bin/mosquitto_pub -h "$BROKER" -p "$PORT" -q 2 -t "$1" -m "$2"
}

LOG="/tmp/sync_s7_data.log"
: > "$LOG"

# 后台监听 data 主题，捕获 readData 的返回结果
env -u LD_LIBRARY_PATH /usr/bin/mosquitto_sub -h "$BROKER" -p "$PORT" -q 2 -t "$DATA_TOPIC" > "$LOG" &
SUB_PID=$!
sleep 1

echo "[S7] 写点位 setData ..."
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"heart_beat_g2","value":1}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"is_running","value":1}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"is_pick_done","value":0}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"is_place_done","value":0}'

echo "[S7] 读点位 readData ..."
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"heart_beat_plc"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"is_pickable"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"is_placeable"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"ES"}'

sleep 1
kill "$SUB_PID" 2>/dev/null

echo "=== S7 readData 反馈 ==="
cat "$LOG"

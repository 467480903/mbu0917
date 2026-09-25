#!/usr/bin/env bash
# Modbus 点位读写测试（MQTT）
#   setData 修改可写点位（isChanged=1，由数据同步控制器周期写回 Modbus 设备）
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

LOG="/tmp/sync_modbus_data.log"
: > "$LOG"

# 后台监听 data 主题，捕获 readData 的返回结果
env -u LD_LIBRARY_PATH /usr/bin/mosquitto_sub -h "$BROKER" -p "$PORT" -q 2 -t "$DATA_TOPIC" > "$LOG" &
SUB_PID=$!
sleep 1

echo "[Modbus] 写点位 setData ..."
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"m1_","value":111}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"m2_","value":222}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"m3_","value":333}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"m4_","value":0}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"m5_","value":0}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"setData","name":"m6_","value":0}'

echo "[Modbus] 读点位 readData ..."
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"m1"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"m2"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"m3"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"m4"}'
mqtt_pub "$REQ_TOPIC" '{"cmd":"readData","name":"m5"}'

sleep 1
kill "$SUB_PID" 2>/dev/null

echo "=== Modbus readData 反馈 ==="
cat "$LOG"

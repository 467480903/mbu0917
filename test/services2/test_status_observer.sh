#!/usr/bin/env bash
# 状态发布器 - 状态观察脚本
# 前置：先运行 python3 test/services2/test_status_service.py
BROKER="localhost"; PORT=1883
TOPIC="/humanoid/status/data/"

env -u LD_LIBRARY_PATH /usr/bin/mosquitto_sub -h "$BROKER" -p "$PORT" -q 0 -t "$TOPIC" -v

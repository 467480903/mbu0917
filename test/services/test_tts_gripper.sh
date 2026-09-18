#!/usr/bin/env bash
# TTS + 左夹爪示例：先播报，再张开并回零。
# 执行前请确认急停可用、周围无人且夹爪未夹持工件。

# TTS 播报
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"tts","data":"开始测试左侧夹爪"}'
sleep 1

# 左夹爪张开
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{"left":-0.70}}'
sleep 1

# 左夹爪回零
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{"left":0.0}}'
sleep 1

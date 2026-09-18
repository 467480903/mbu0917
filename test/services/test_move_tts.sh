#!/usr/bin/env bash
# 底盘相对运动 + TTS 测试：前进 0.3 米后播报提示。
# 执行前请确认急停可用、前方 0.3 米内无人无障碍物。

# 底盘相对运动：x 正方向为前进，单位米。
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"go_rel","data":{"x":0.3,"y":0.0,"yaw_rad":0.0}}'

# 语音播放。服务端会将该命令排在相对运动之后执行。
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"tts","data":"前进零点三米，你好"}'

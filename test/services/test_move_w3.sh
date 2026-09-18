#!/usr/bin/env bash
# 底盘相对运动 + 全身 W3 动作测试：前进 2 米后执行 WBC W3。
# 执行前请确认急停可用、前方 2 米内无人无障碍物，并确认 W3 动作安全。

# 底盘相对运动：x 正方向为前进，单位米。
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"go_rel_nowait","data":{"x":1.0,"y":0.0,"yaw_rad":0.0}}'

# 全身关节动作：W3。
# 服务端将关节与动作命令提交到同一个单线程执行队列，按接收顺序处理。
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/joints/control \
  -m '{"command":"WBC","data":"W3","speed":0.15}'

#!/usr/bin/env bash
# 真实夹爪测试：负值张开，0.0 回到闭合/零位。
# 执行前请确认急停可用、周围无人且夹爪未夹持工件。

# 左夹爪小幅张开
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{"left":-0.70}}'
sleep 1

# 左夹爪回零
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{"left":0.0}}'
sleep 1

# 右夹爪小幅张开
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{"right":-0.70}}'
sleep 1

# 右夹爪回零
mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{"right":0.0}}'
sleep 1

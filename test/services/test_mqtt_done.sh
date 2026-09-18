#!/usr/bin/env bash
# MQTT 服务链路探针：发送空的 grab 数据，不会控制左右夹爪。
# 服务端处理完后会向 /humanoid/commands/done 发布 done 消息。

mosquitto_pub -h localhost -p 1883 -q 2 \
  -t /humanoid/commands/data \
  -m '{"command":"grab","data":{}}'

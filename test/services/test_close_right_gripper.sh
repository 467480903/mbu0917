#!/usr/bin/env bash
# 关闭右手夹爪（right=0.0）。运行前确认急停可用，夹爪附近无人且无工件。
mosquitto_pub -h localhost -p 1883 -q 2 -t /humanoid/commands/data -m '{"command":"grab","data":{"right":0.0}}'
sleep 1
mosquitto_pub -h localhost -p 1883 -q 2 -t /humanoid/commands/data -m '{"command":"grab","data":{"right":-0.75}}'

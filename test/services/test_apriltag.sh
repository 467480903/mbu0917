#!/usr/bin/env bash
# 触发一次 AprilTag 双标签检测。
env -u LD_LIBRARY_PATH /usr/bin/mosquitto_pub -h localhost -p 1883 -q 0 -t /humanoid/apriltag -m '{"cmd":"detect2tagsForLineDistance","imgPath":"/data/wxf/mbu0917/images/","resultSavePath":"/data/wxf/mbu0917/detect"}'

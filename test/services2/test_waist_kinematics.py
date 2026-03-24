#!/usr/bin/env python3
"""腰腿 URDF 正逆运动学离线测试；不会连接 GDK，也不会驱动机器人。"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "service2"))

from pose_controller import PoseController


class FakeGdk:
    class Robot:
        pass


class FakeMqtt:
    def publish(self, *_args, **_kwargs):
        return None


controller = PoseController(FakeGdk, FakeMqtt(), "response", "done")
current = [-0.6968661544, 1.5097609848, -0.8703171433, 0.0, 0.0]
start = controller._waist_forward_kinematics(current)

for forward, up in ((0.02, 0.0), (-0.02, 0.0), (0.0, 0.02), (0.0, -0.02)):
    target, solved = controller._waist_inverse_kinematics(current, forward, up)
    assert math.isclose(solved["x"], start["x"] + forward, abs_tol=1e-8)
    assert math.isclose(solved["z"], start["z"] + up, abs_tol=1e-8)
    assert math.isclose(sum(target[:3]), sum(current[:3]), abs_tol=1e-8)
    assert target[3:] == current[3:]

print("腰腿正逆运动学离线测试通过")

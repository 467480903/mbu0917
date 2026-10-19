#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
end_effector_controller.py — 末端控制器

职责：
  - 控制末端爪子的张合
"""

import time


class EndEffectorController:
    """末端执行器控制器"""
    
    def __init__(self, agibot_gdk, mqtt_client, topic_response, topic_done):
        """构造函数
        
        Parameters
        ----------
        agibot_gdk : module
            已初始化的 GDK 模块
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        topic_done : str
            完成信号主题
        """
        self.agibot_gdk = agibot_gdk
        self.robot = agibot_gdk.Robot()
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.topic_done = topic_done
        
        # 爪子参数
        self.gripper_open = 1.0
        self.gripper_close = 0.0
        self.gripper_open_position = -0.7
        self.gripper_close_position = 0.0
        self.position_tolerance = 0.05
        self.motion_timeout = 6.0
        self.check_period = 0.1
        self.command_interval = 0.1
    
    def _publish_response(self, cmd, ts, success=False, extra=None):
        """发布反馈报文"""
        import json
        resp = {"cmd": cmd, "time": ts}
        if success:
            resp["success"] = True
        if extra:
            resp.update(extra)
        self.mqtt_client.publish(self.topic_response, json.dumps(resp, ensure_ascii=False))
    
    def _publish_done(self, cmd, ts):
        """发布完成报文"""
        import json
        self.mqtt_client.publish(self.topic_done, json.dumps({
            "cmd": cmd, "time": ts, "type": "ee"
        }, ensure_ascii=False))
    
    # ── 运动控制（不嵌套，直接调用 GDK）────────────────────

    def _read_gripper_position(self, side):
        """读取单侧夹爪的 GDK 实际位置。"""
        try:
            end_state = self.robot.get_end_state()
            states = (end_state.get(f"{side}_end_state") or {}).get("end_states") or []
            if states:
                return float(states[0].get("position", 0.0))
        except Exception as error:
            print(f"[末端] 读取 {side} 夹爪位置失败: {error}")
        return None

    def _send_gripper_position(self, side, position):
        """使用 GDK move_ee_pos 下发单侧夹爪位置。"""
        joint_states = self.agibot_gdk.JointStates()
        joint_states.group = f"{side}_tool"
        joint_states.target_type = "omnipicker"
        joint_state = self.agibot_gdk.JointState()
        joint_state.position = position
        joint_states.states = [joint_state]
        joint_states.nums = 1
        result = self.robot.move_ee_pos(joint_states)
        return result in (None, 0)

    def _move_grippers(self, positions):
        """连续下发所有指定夹爪，然后统一等待它们全部到位。"""
        targets = {}
        for side, position in positions.items():
            normalized = max(0.0, min(1.0, float(position)))
            target = self.gripper_open_position * normalized
            targets[side] = target
            print(f"[末端] {side} 夹爪: position={normalized:.2f}, GDK目标={target:.2f}")

        deadline = time.time() + self.motion_timeout

        while time.time() < deadline:
            # 双爪指令需要留出处理间隔，否则后一侧可能不响应。
            target_items = list(targets.items())
            for index, (side, target) in enumerate(target_items):
                if not self._send_gripper_position(side, target):
                    return False
                if index < len(target_items) - 1:
                    time.sleep(self.command_interval)

            time.sleep(self.check_period)

            actual_positions = {
                side: self._read_gripper_position(side) for side in targets
            }
            if all(
                actual_positions[side] is not None
                and abs(actual_positions[side] - target) <= self.position_tolerance
                for side, target in targets.items()
            ):
                actual_text = ", ".join(
                    f"{side}={actual_positions[side]:.3f}" for side in targets
                )
                print(f"[末端] 夹爪全部到位: {actual_text}")
                return True

        print(f"[末端] 夹爪到位超时: {', '.join(targets)}")
        return False
    
    def left_gripper(self, position):
        """控制左手爪子
        
        Parameters
        ----------
        position : float
            0.0~1.0，0=完全闭合，1=完全张开
        """
        try:
            return self._move_grippers({"left": position})
        except Exception as e:
            print(f"[末端] 错误: {e}")
            return False
    
    def right_gripper(self, position):
        """控制右手爪子
        
        Parameters
        ----------
        position : float
            0.0~1.0，0=完全闭合，1=完全张开
        """
        try:
            return self._move_grippers({"right": position})
        except Exception as e:
            print(f"[末端] 错误: {e}")
            return False
    
    def left_gripper_action(self, action):
        """控制左手爪子动作
        
        Parameters
        ----------
        action : str
            "open" 或 "close"
        """
        position = self.gripper_open if action == "open" else self.gripper_close
        return self.left_gripper(position)
    
    def right_gripper_action(self, action):
        """控制右手爪子动作
        
        Parameters
        ----------
        action : str
            "open" 或 "close"
        """
        position = self.gripper_open if action == "open" else self.gripper_close
        return self.right_gripper(position)
    
    def both_grippers(self, left_position, right_position):
        """同时控制双爪"""
        print(f"[末端] 双爪: 左={left_position:.2f} 右={right_position:.2f}")
        try:
            return self._move_grippers({
                "left": left_position,
                "right": right_position,
            })
        except Exception as e:
            print(f"[末端] 错误: {e}")
            return False

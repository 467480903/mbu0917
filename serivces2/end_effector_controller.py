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
    
    def __init__(self, robot, mqtt_client, topic_response, topic_done):
        """构造函数
        
        Parameters
        ----------
        robot : agibot_gdk.Robot
            GDK Robot 对象
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        topic_done : str
            完成信号主题
        """
        self.robot = robot
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.topic_done = topic_done
        
        # 爪子参数
        self.gripper_open = 1.0
        self.gripper_close = 0.0
        self.gripper_speed = 0.5
    
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
    
    def left_gripper(self, position):
        """控制左手爪子
        
        Parameters
        ----------
        position : float
            0.0~1.0，0=完全闭合，1=完全张开
        """
        position = max(0.0, min(1.0, float(position)))
        print(f"[末端] 左手爪: position={position:.2f}")
        
        try:
            self.robot.set_left_gripper(position, self.gripper_speed)
            time.sleep(0.5)
            return True
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
        position = max(0.0, min(1.0, float(position)))
        print(f"[末端] 右手爪: position={position:.2f}")
        
        try:
            self.robot.set_right_gripper(position, self.gripper_speed)
            time.sleep(0.5)
            return True
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
            self.robot.set_left_gripper(left_position, self.gripper_speed)
            self.robot.set_right_gripper(right_position, self.gripper_speed)
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"[末端] 错误: {e}")
            return False

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
joint_controller.py — 关节控制器

职责：
  - 底盘5关节控制（waist）
  - 全身22关节控制（WBC）
  - 头部3关节控制（head）
  - 左手7关节控制（left_arm）
  - 右手7关节控制（right_arm）
"""

import math


class JointController:
    """关节控制器"""
    
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
        self.robot = self.agibot_gdk.Robot()
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.topic_done = topic_done
        
        # 关节名分组（逻辑顺序：1, 2, 3）
        self.head_joint_keys = [
            "idx11_head_joint1", "idx12_head_joint2", "idx13_head_joint3",
        ]
        self.waist_joint_keys = [
            "idx01_body_joint1", "idx02_body_joint2", "idx03_body_joint3",
            "idx04_body_joint4", "idx05_body_joint5",
        ]
        self.left_arm_joint_keys = [
            "idx21_arm_l_joint1", "idx22_arm_l_joint2", "idx23_arm_l_joint3",
            "idx24_arm_l_joint4", "idx25_arm_l_joint5", "idx26_arm_l_joint6",
            "idx27_arm_l_joint7",
        ]
        self.right_arm_joint_keys = [
            "idx61_arm_r_joint1", "idx62_arm_r_joint2", "idx63_arm_r_joint3",
            "idx64_arm_r_joint4", "idx65_arm_r_joint5", "idx66_arm_r_joint6",
            "idx67_arm_r_joint7",
        ]
        
        # GDK 全身关节顺序（头部需调整为 1, 3, 2 以匹配底层接口）
        self.whole_body_joint_keys = (
            self.waist_joint_keys
            + self.head_joint_keys
            + self.left_arm_joint_keys
            + self.right_arm_joint_keys
        )
        
        # 默认速度
        self.head_speed = 0.3
        self.waist_speed = 0.3
        self.arm_speed = 0.2
    
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
            "cmd": cmd, "time": ts, "type": "joint"
        }, ensure_ascii=False))
    
    def _get_current_angles(self, keys):
        """读取当前关节角"""
        try:
            states = self.robot.get_joint_states()
            cur = {s['name']: s['motor_position'] for s in states['states']}
            return [cur.get(k, 0.0) for k in keys]
        except Exception as e:
            print(f"[关节] 读取关节角失败: {e}")
            return [0.0] * len(keys)

    def get_current_angles(self):
        """读取全部关节当前角度，返回关节名到弧度值的映射。"""
        states = self.robot.get_joint_states()
        if not isinstance(states, dict) or not isinstance(states.get("states"), list):
            raise RuntimeError("GDK 返回的关节状态格式不正确")

        angles = {}
        for state in states["states"]:
            name = state.get("name")
            if not name:
                continue
            value = state.get("position", state.get("motor_position"))
            if value is not None:
                angles[str(name)] = float(value)
        if not angles:
            raise RuntimeError("未读取到关节角")
        return angles
    
    # ── 运动控制（不嵌套，直接调用 GDK）────────────────────
    
    def move_head(self, joints, speed=None):
        """控制头部3个关节
        
        Parameters
        ----------
        joints : list
            3个关节角度（弧度）
        speed : float
            速度，默认 0.3
        """
        velocity = self.head_speed if speed is None else speed
        pos = joints[:3] if len(joints) >= 3 else joints + [0.0] * (3 - len(joints))
        vel = [velocity] * 3
        
        print(f"[关节] 头部: {pos}")
        self.robot.move_head_joint(pos, vel)
        return True
    
    def move_waist(self, joints, speed=None):
        """控制腰部5个关节
        
        Parameters
        ----------
        joints : list
            5个关节角度（弧度）
        speed : float
            速度，默认 0.3
        """
        velocity = self.waist_speed if speed is None else speed
        pos = joints[:5] if len(joints) >= 5 else joints + [0.0] * (5 - len(joints))
        vel = [velocity] * 5
        
        print(f"[关节] 腰部: {pos}")
        self.robot.move_waist_joint(pos, vel)
        return True
    
    def move_left_arm(self, joints, speed=None):
        """控制左臂7个关节
        
        Parameters
        ----------
        joints : list
            7个关节角度（弧度）
        speed : float
            速度，默认 0.2
        """
        velocity = self.arm_speed if speed is None else speed
        left = joints[:7] if len(joints) >= 7 else joints + [0.0] * (7 - len(joints))
        right = self._get_current_angles(self.right_arm_joint_keys)
        positions = left + right
        vel = [velocity] * 14
        
        print(f"[关节] 左臂: {left}")
        self.robot.move_arm_joint(positions, vel, 2)
        return True
    
    def move_right_arm(self, joints, speed=None):
        """控制右臂7个关节
        
        Parameters
        ----------
        joints : list
            7个关节角度（弧度）
        speed : float
            速度，默认 0.2
        """
        velocity = self.arm_speed if speed is None else speed
        left = self._get_current_angles(self.left_arm_joint_keys)
        right = joints[:7] if len(joints) >= 7 else joints + [0.0] * (7 - len(joints))
        positions = left + right
        vel = [velocity] * 14
        
        print(f"[关节] 右臂: {right}")
        self.robot.move_arm_joint(positions, vel, 2)
        return True
    
    def move_arms(self, joints_dict, speed=None):
        """控制双臂（14个关节）
        
        Parameters
        ----------
        joints_dict : dict
            关节名 -> 角度（弧度）的字典
        speed : float
            速度，默认 0.2
        """
        velocity = self.arm_speed if speed is None else speed
        left = [joints_dict.get(k, 0.0) for k in self.left_arm_joint_keys]
        right = [joints_dict.get(k, 0.0) for k in self.right_arm_joint_keys]
        positions = left + right
        vel = [velocity] * 14
        
        print(f"[关节] 双臂: 左={left} 右={right}")
        self.robot.move_arm_joint(positions, vel, 2)
        return True
    
    def move_wbc(self, joints_dict, speed=None):
        """控制全身22个关节（批量请求）
        
        Parameters
        ----------
        joints_dict : dict
            关节名 -> 角度（弧度）的字典，必须包含全部22个关节
        speed : float
            速度，默认按部位分配
        """
        # 验证完整性
        missing = [k for k in self.whole_body_joint_keys if k not in joints_dict]
        if missing:
            print(f"[关节] 缺少关节: {missing}")
            return False
        
        # 提取位置和速度
        positions = [joints_dict[k] for k in self.whole_body_joint_keys]
        if speed is not None:
            velocities = [speed] * 22
        else:
            velocities = (
                [self.waist_speed] * 5  # 腰部
                + [self.head_speed] * 3  # 头部
                + [self.arm_speed] * 14  # 双臂
            )
        
        # 构建批量请求
        request = self.agibot_gdk.JointControlReq()
        request.life_time = 0.1
        request.joint_names = self.whole_body_joint_keys
        request.joint_positions = positions
        request.joint_velocities = velocities
        
        print(f"[关节] WBC: 下发22个关节")
        self.robot.joint_control_request(request)
        return True
    
    def move_single_joint(self, name, value=None, offset=None, speed=None):
        """控制单个关节
        
        Parameters
        ----------
        name : str
            关节名
        value : float
            目标角度（弧度）
        offset : float
            增量角度（弧度）
        speed : float
            速度
        """
        try:
            states = self.robot.get_joint_states()
            current_angles = {s['name']: s['motor_position'] for s in states['states']}
        except Exception as error:
            print(f"[关节] 读取当前角度失败: {error}")
            return False

        if name not in current_angles:
            print(f"[关节] 未找到关节状态: {name}")
            return False

        current = current_angles[name]
        
        if value is not None:
            target = float(value)
        elif offset is not None:
            target = current + float(offset)
        else:
            print("[关节] 需要 value 或 offset")
            return False
        
        print(f"[关节] 单关节 {name}: {current:.4f} → {target:.4f}")
        
        velocity = float(speed) if speed is not None else None

        # 根据关节分组选择接口
        if name in self.head_joint_keys:
            keys = self.head_joint_keys
            if any(key not in current_angles for key in keys):
                print("[关节] 头部关节状态不完整")
                return False
            pos = [current_angles[k] for k in keys]
            idx = keys.index(name)
            pos[idx] = target
            joint_speed = self.head_speed if velocity is None else velocity
            self.robot.move_head_joint(pos, [joint_speed] * 3)
        
        elif name in self.waist_joint_keys:
            keys = self.waist_joint_keys
            if any(key not in current_angles for key in keys):
                print("[关节] 腰部关节状态不完整")
                return False
            pos = [current_angles[k] for k in keys]
            idx = keys.index(name)
            pos[idx] = target
            joint_speed = self.waist_speed if velocity is None else velocity
            self.robot.move_waist_joint(pos, [joint_speed] * 5)
        
        elif name in self.left_arm_joint_keys:
            keys = self.left_arm_joint_keys
            arm_keys = self.left_arm_joint_keys + self.right_arm_joint_keys
            if any(key not in current_angles for key in arm_keys):
                print("[关节] 双臂关节状态不完整")
                return False
            left = [current_angles[k] for k in keys]
            idx = keys.index(name)
            left[idx] = target
            right = [current_angles[k] for k in self.right_arm_joint_keys]
            joint_speed = self.arm_speed if velocity is None else velocity
            self.robot.move_arm_joint(left + right, [joint_speed] * 14, 2)
        
        elif name in self.right_arm_joint_keys:
            keys = self.right_arm_joint_keys
            arm_keys = self.left_arm_joint_keys + self.right_arm_joint_keys
            if any(key not in current_angles for key in arm_keys):
                print("[关节] 双臂关节状态不完整")
                return False
            right = [current_angles[k] for k in keys]
            idx = keys.index(name)
            right[idx] = target
            left = [current_angles[k] for k in self.left_arm_joint_keys]
            joint_speed = self.arm_speed if velocity is None else velocity
            self.robot.move_arm_joint(left + right, [joint_speed] * 14, 2)
        
        else:
            print(f"[关节] 未知关节名: {name}")
            return False
        
        return True

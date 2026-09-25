#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pose_controller.py — 位姿控制器

职责：
  - 控制左右手末端运动（世界坐标系绝对位姿）
  - 控制腰部运动（上下前后）
"""

import math
import time
import threading


class PoseController:
    """位姿控制器"""
    
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
        self._lock = threading.Lock()
        
        # 末端 link 名
        self.left_name = "arm_l_end_link"
        self.right_name = "arm_r_end_link"
        
        # 控制参数
        self.max_step_cm = 0.1
        self.lifetime = 0.02
        self.rate_hz = 50.0
    
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
            "cmd": cmd, "time": ts, "type": "pose"
        }, ensure_ascii=False))
    
    # ── 数学工具 ──────────────────────────────────────────
    
    @staticmethod
    def slerp(q0, q1, t):
        """四元数球面线性插值"""
        dot = sum(q0[i] * q1[i] for i in range(4))
        if dot < 0.0:
            dot = -dot
            q1 = [-v for v in q1]
        dot = max(-1.0, min(1.0, dot))
        if dot > 0.9995:
            result = [q0[i] + t * (q1[i] - q0[i]) for i in range(4)]
            norm = math.sqrt(sum(v * v for v in result))
            return [v / norm for v in result] if norm > 0 else result
        theta_0 = math.acos(dot)
        sin_t0 = math.sin(theta_0)
        theta = theta_0 * t
        s0 = math.cos(theta) - dot * math.sin(theta) / sin_t0
        s1 = math.sin(theta) / sin_t0
        return [s0 * q0[i] + s1 * q1[i] for i in range(4)]
    
    @staticmethod
    def euler_to_quaternion(rx_deg, ry_deg, rz_deg):
        """欧拉角（度，ZYX顺序）→ 四元数"""
        rx = math.radians(rx_deg) / 2.0
        ry = math.radians(ry_deg) / 2.0
        rz = math.radians(rz_deg) / 2.0
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)
        return [
            sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
            cx * cy * cz + sx * sy * sz,
        ]
    
    @staticmethod
    def quaternion_multiply(q1, q2):
        """四元数乘法"""
        x1, y1, z1, w1 = q1
        x2, y2, z2, w2 = q2
        return [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ]
    
    @staticmethod
    def distance(p1, p2):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))
    
    def _n_steps(self, start_pos, goal_pos, start_quat=None, goal_quat=None):
        """计算所需步数"""
        dist_cm = self.distance(start_pos, goal_pos) * 100.0
        steps = max(int(math.ceil(dist_cm / self.max_step_cm)), 1)
        if start_quat and goal_quat:
            dot = abs(sum(start_quat[i] * goal_quat[i] for i in range(4)))
            dot = min(1.0, dot)
            angle_deg = math.degrees(2.0 * math.acos(dot))
            steps = max(steps, int(math.ceil(angle_deg / 0.3)))
        return steps
    
    def _plan(self, start_pose, goal_pose, n_steps):
        """生成轨迹"""
        traj = []
        for i in range(n_steps):
            t = float(i) / (n_steps - 1) if n_steps > 1 else 0.0
            pos = [start_pose["position"][j] + t * (goal_pose["position"][j] - start_pose["position"][j])
                   for j in range(3)]
            quat = self.slerp(start_pose["orientation"], goal_pose["orientation"], t)
            traj.append({"position": pos, "orientation": quat})
        return traj
    
    def _find_pose(self, name):
        """从状态数据中寻找指定 link 的当前位姿"""
        status = self.robot.get_motion_control_status()
        for i, frame_name in enumerate(status.frame_names):
            if frame_name == name:
                p = status.frame_poses[i]
                return {
                    "position": [p.position.x, p.position.y, p.position.z],
                    "orientation": [p.orientation.x, p.orientation.y,
                                    p.orientation.z, p.orientation.w],
                }
        raise RuntimeError(f"帧名 '{name}' 未找到")
    
    def get_current_pose(self, side):
        """获取当前末端位姿"""
        name = self.left_name if side == "left" else self.right_name
        return self._find_pose(name)
    
    # ── 运动执行（不嵌套，直接调用 GDK）────────────────────
    
    def _send_trajectory(self, agibot_gdk, traj, group):
        """发送单臂轨迹"""
        dt = 1.0 / self.rate_hz
        
        for wp in traj:
            ep = agibot_gdk.EndEffectorPose()
            ep.life_time = self.lifetime
            ep.group = group
            
            if group == agibot_gdk.EndEffectorControlGroup.kLeftArm:
                p = ep.left_end_effector_pose
            else:
                p = ep.right_end_effector_pose
            
            p.position.x = wp["position"][0]
            p.position.y = wp["position"][1]
            p.position.z = wp["position"][2]
            p.orientation.x = wp["orientation"][0]
            p.orientation.y = wp["orientation"][1]
            p.orientation.z = wp["orientation"][2]
            p.orientation.w = wp["orientation"][3]
            
            try:
                ret = self.robot.end_effector_pose_control(ep)
                if ret != 0:
                    print(f"[位姿] 指令返回非零: {ret}")
            except Exception as e:
                print(f"[位姿] 错误: {e}")
                return False
            
            time.sleep(dt)
        
        return True
    
    def _send_dual_trajectory(self, agibot_gdk, traj_left, traj_right):
        """同时发送双臂轨迹"""
        dt = 1.0 / self.rate_hz
        
        for i in range(len(traj_left)):
            wp_l = traj_left[i]
            wp_r = traj_right[i]
            
            # 左臂
            ep_l = agibot_gdk.EndEffectorPose()
            ep_l.life_time = self.lifetime
            ep_l.group = agibot_gdk.EndEffectorControlGroup.kLeftArm
            ep_l.left_end_effector_pose.position.x = wp_l["position"][0]
            ep_l.left_end_effector_pose.position.y = wp_l["position"][1]
            ep_l.left_end_effector_pose.position.z = wp_l["position"][2]
            ep_l.left_end_effector_pose.orientation.x = wp_l["orientation"][0]
            ep_l.left_end_effector_pose.orientation.y = wp_l["orientation"][1]
            ep_l.left_end_effector_pose.orientation.z = wp_l["orientation"][2]
            ep_l.left_end_effector_pose.orientation.w = wp_l["orientation"][3]
            
            # 右臂
            ep_r = agibot_gdk.EndEffectorPose()
            ep_r.life_time = self.lifetime
            ep_r.group = agibot_gdk.EndEffectorControlGroup.kRightArm
            ep_r.right_end_effector_pose.position.x = wp_r["position"][0]
            ep_r.right_end_effector_pose.position.y = wp_r["position"][1]
            ep_r.right_end_effector_pose.position.z = wp_r["position"][2]
            ep_r.right_end_effector_pose.orientation.x = wp_r["orientation"][0]
            ep_r.right_end_effector_pose.orientation.y = wp_r["orientation"][1]
            ep_r.right_end_effector_pose.orientation.z = wp_r["orientation"][2]
            ep_r.right_end_effector_pose.orientation.w = wp_r["orientation"][3]
            
            try:
                self.robot.end_effector_pose_control(ep_l)
                time.sleep(0.002)
                self.robot.end_effector_pose_control(ep_r)
            except Exception as e:
                print(f"[位姿] 错误: {e}")
                return False
            
            time.sleep(max(0.0, dt - 0.002))
        
        return True
    
    def _hold_at_pose(self, agibot_gdk, pose_l, pose_r, hold_sec=1.0):
        """在指定位姿保持"""
        n = int(hold_sec * self.rate_hz)
        hold_life = 0.1
        
        for _ in range(n):
            for pose, group in [(pose_l, agibot_gdk.EndEffectorControlGroup.kLeftArm),
                                (pose_r, agibot_gdk.EndEffectorControlGroup.kRightArm)]:
                ep = agibot_gdk.EndEffectorPose()
                ep.life_time = hold_life
                ep.group = group
                
                if group == agibot_gdk.EndEffectorControlGroup.kLeftArm:
                    p = ep.left_end_effector_pose
                else:
                    p = ep.right_end_effector_pose
                
                p.position.x = pose["position"][0]
                p.position.y = pose["position"][1]
                p.position.z = pose["position"][2]
                p.orientation.x = pose["orientation"][0]
                p.orientation.y = pose["orientation"][1]
                p.orientation.z = pose["orientation"][2]
                p.orientation.w = pose["orientation"][3]
                
                try:
                    self.robot.end_effector_pose_control(ep)
                except Exception:
                    pass
                time.sleep(0.002)
            time.sleep(max(0.0, 1.0 / self.rate_hz - 0.004))
    
    def move_left_arm(self, agibot_gdk, position, orientation):
        """控制左臂到绝对位姿"""
        with self._lock:
            print(f"[位姿] 左臂: {position}")
            
            start = self._find_pose(self.left_name)
            target = {"position": position, "orientation": orientation}
            
            n_steps = self._n_steps(start["position"], target["position"],
                                    start["orientation"], target["orientation"])
            
            traj = self._plan(start, target, n_steps)
            success = self._send_trajectory(agibot_gdk, traj, agibot_gdk.EndEffectorControlGroup.kLeftArm)
            
            if success:
                for _ in range(int(1.0 * self.rate_hz)):
                    self._send_trajectory(agibot_gdk, [target], agibot_gdk.EndEffectorControlGroup.kLeftArm)
            
            print(f"[位姿] 左臂 {'完成' if success else '失败'}")
            return success
    
    def move_right_arm(self, agibot_gdk, position, orientation):
        """控制右臂到绝对位姿"""
        with self._lock:
            print(f"[位姿] 右臂: {position}")
            
            start = self._find_pose(self.right_name)
            target = {"position": position, "orientation": orientation}
            
            n_steps = self._n_steps(start["position"], target["position"],
                                    start["orientation"], target["orientation"])
            
            traj = self._plan(start, target, n_steps)
            success = self._send_trajectory(agibot_gdk, traj, agibot_gdk.EndEffectorControlGroup.kRightArm)
            
            if success:
                for _ in range(int(1.0 * self.rate_hz)):
                    self._send_trajectory(agibot_gdk, [target], agibot_gdk.EndEffectorControlGroup.kRightArm)
            
            print(f"[位姿] 右臂 {'完成' if success else '失败'}")
            return success
    
    def move_both_arms(self, agibot_gdk, left_target, right_target):
        """控制双臂到绝对位姿"""
        with self._lock:
            print(f"[位姿] 双臂")
            
            start_l = self._find_pose(self.left_name)
            start_r = self._find_pose(self.right_name)
            
            n_l = self._n_steps(start_l["position"], left_target["position"],
                               start_l["orientation"], left_target["orientation"])
            n_r = self._n_steps(start_r["position"], right_target["position"],
                               start_r["orientation"], right_target["orientation"])
            n_steps = max(n_l, n_r, 2)
            
            traj_l = self._plan(start_l, left_target, n_steps)
            traj_r = self._plan(start_r, right_target, n_steps)
            
            success = self._send_dual_trajectory(agibot_gdk, traj_l, traj_r)
            
            if success:
                self._hold_at_pose(agibot_gdk, traj_l[-1], traj_r[-1], hold_sec=1.0)
            
            print(f"[位姿] 双臂 {'完成' if success else '失败'}")
            return success
    
    def move_relative(self, agibot_gdk, side, offset, rotation):
        """相对运动"""
        with self._lock:
            name = self.left_name if side == "left" else self.right_name
            print(f"[位姿] {side}臂相对运动")
            
            start = self._find_pose(name)
            q_rot = self.euler_to_quaternion(*rotation)
            
            target = {
                "position": [
                    start["position"][0] + offset[0],
                    start["position"][1] + offset[1],
                    start["position"][2] + offset[2]
                ],
                "orientation": self.quaternion_multiply(q_rot, start["orientation"])
            }
            
            n_steps = self._n_steps(start["position"], target["position"],
                                    start["orientation"], target["orientation"])
            
            traj = self._plan(start, target, n_steps)
            group = (agibot_gdk.EndEffectorControlGroup.kLeftArm if side == "left"
                     else agibot_gdk.EndEffectorControlGroup.kRightArm)
            success = self._send_trajectory(agibot_gdk, traj, group)
            
            print(f"[位姿] {side}臂 {'完成' if success else '失败'}")
            return success
    
    def move_waist(self, agibot_gdk, offset):
        """腰部运动（上下前后）"""
        with self._lock:
            print(f"[位姿] 腰部: offset={offset}")
            
            start_l = self._find_pose(self.left_name)
            start_r = self._find_pose(self.right_name)
            
            target_l = {
                "position": [
                    start_l["position"][0] + offset[0],
                    start_l["position"][1] + offset[1],
                    start_l["position"][2] + offset[2]
                ],
                "orientation": start_l["orientation"]
            }
            target_r = {
                "position": [
                    start_r["position"][0] + offset[0],
                    start_r["position"][1] + offset[1],
                    start_r["position"][2] + offset[2]
                ],
                "orientation": start_r["orientation"]
            }
            
            return self.move_both_arms(agibot_gdk, target_l, target_r)
    
    @staticmethod
    def _recover_quat(data):
        """从 {rx, ry, rz} 恢复四元数"""
        qx = data.get("rx", 0)
        qy = data.get("ry", 0)
        qz = data.get("rz", 0)
        qw = math.sqrt(max(0, 1 - qx*qx - qy*qy - qz*qz))
        return [qx, qy, qz, qw]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pose_controller.py — 位姿控制器

职责：
  - 控制左右手末端运动（世界坐标系绝对位姿）
  - 控制腰部运动（上下前后）
"""

import json
import math
import time
import threading


class PoseController:
    """位姿控制器"""
    
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
        self._lock = threading.Lock()
        self.status_topic = "/humanoid/status/data"
        self._status_stop = threading.Event()
        self._status_thread = None
        
        # 末端 link 名
        self.left_name = "arm_l_end_link"
        self.right_name = "arm_r_end_link"
        
        # 控制参数
        self.max_step_cm = 0.1
        self.lifetime = 0.02
        self.rate_hz = 50.0

        # 腰腿串联链（web/meshes/model.urdf，base_link -> body_link5）。
        # 前三个关节均绕 Y 轴，负责 X/Z 平面运动；关节 4/5 为横滚/偏航，
        # 笛卡尔平移时保持当前值。这里使用 URDF 原点变换直接计算，它与
        # 对应的改进 DH 链等价，避免把非 Z 轴关节强行套入标准 DH 后丢失轴向。
        self.waist_joint_keys = [
            "idx01_body_joint1", "idx02_body_joint2", "idx03_body_joint3",
            "idx04_body_joint4", "idx05_body_joint5",
        ]
        self.waist_base_x = 0.102
        self.waist_base_z = 0.144
        self.waist_link_lengths = (0.360, 0.380, 0.149)
        self.waist_joint_limits = (
            (-1.0821, 0.0),
            (0.0, 2.6529),
            (-1.9190, 1.1170),
            (-0.436332313, 0.436332313),
            (-3.045599545, 3.045599545),
        )
        self.waist_speed = 0.20
        self.waist_max_cartesian_step = 0.03
        self.waist_max_joint_step = 0.20
    
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
        if side not in ("left", "right"):
            raise ValueError(f"未知末端侧别: {side}")
        name = self.left_name if side == "left" else self.right_name
        pose = self._find_pose(name)
        return {
            "position": [float(value) for value in pose["position"]],
            "orientation": [float(value) for value in pose["orientation"]],
        }

    def get_end_effector_status(self):
        """一次读取并返回左右末端位姿。"""
        status = self.robot.get_motion_control_status()
        left = self.find_pose_in_status(status, self.left_name)
        right = self.find_pose_in_status(status, self.right_name)
        return {"left_ee": left, "right_ee": right}

    def _get_current_waist_angles(self):
        """读取五个腰腿关节当前角度（弧度）。"""
        states = self.robot.get_joint_states()
        if not isinstance(states, dict) or not isinstance(states.get("states"), list):
            raise RuntimeError("GDK 返回的关节状态格式不正确")
        current = {}
        for state in states["states"]:
            name = state.get("name")
            value = state.get("position", state.get("motor_position"))
            if name and value is not None:
                current[str(name)] = float(value)
        missing = [name for name in self.waist_joint_keys if name not in current]
        if missing:
            raise RuntimeError(f"腰腿关节状态不完整: {missing}")
        return [current[name] for name in self.waist_joint_keys]

    def _waist_forward_kinematics(self, joints):
        """按 URDF 链计算 body_link5 在 base_link 下的 X/Z/俯仰。"""
        if len(joints) != 5:
            raise ValueError("腰腿正解需要 5 个关节角")
        q1, q2, q3, q4, _q5 = [float(value) for value in joints]
        link1, link2, link3 = self.waist_link_lengths
        pitch12 = q1 + q2
        pitch = pitch12 + q3
        roll_projection = math.cos(q4)
        x = (self.waist_base_x
             + link1 * math.sin(q1)
             + link2 * math.sin(pitch12)
             + link3 * math.sin(pitch) * roll_projection)
        z = (self.waist_base_z
             + link1 * math.cos(q1)
             + link2 * math.cos(pitch12)
             + link3 * math.cos(pitch) * roll_projection)
        y = -link3 * math.sin(q4)
        return {
            "x": x, "y": y, "z": z,
            "pitch": pitch, "roll": q4, "yaw": joints[4],
        }

    def _solve_waist_target(self, current, target_x, target_z,
                            target_pitch, target_roll, target_yaw,
                            limit_joint_step=False):
        """求解腰腿绝对目标；目标坐标位于 base_link 坐标系。"""
        values = [*current, target_x, target_z, target_pitch,
                  target_roll, target_yaw]
        if len(current) != 5 or not all(math.isfinite(float(v)) for v in values):
            raise ValueError("腰腿绝对目标必须包含有效的五轴当前角和 X/Z/RX/RY/RZ")
        link1, link2, link3 = self.waist_link_lengths
        projection = math.cos(target_roll)
        planar_x = (target_x - self.waist_base_x
                    - link3 * math.sin(target_pitch) * projection)
        planar_z = (target_z - self.waist_base_z
                    - link3 * math.cos(target_pitch) * projection)
        cosine_q2 = ((planar_x * planar_x + planar_z * planar_z
                      - link1 * link1 - link2 * link2)
                     / (2.0 * link1 * link2))
        if cosine_q2 < -1.0 - 1e-8 or cosine_q2 > 1.0 + 1e-8:
            raise ValueError("目标超出腰腿 X/Z 可达工作空间")
        cosine_q2 = max(-1.0, min(1.0, cosine_q2))

        candidates = []
        for q2 in (math.acos(cosine_q2), -math.acos(cosine_q2)):
            q1 = (math.atan2(planar_x, planar_z)
                  - math.atan2(link2 * math.sin(q2),
                               link1 + link2 * math.cos(q2)))
            q3 = target_pitch - q1 - q2
            candidate = [q1, q2, q3, target_roll, target_yaw]
            if all(lower + 1e-6 <= value <= upper - 1e-6
                   for value, (lower, upper)
                   in zip(candidate, self.waist_joint_limits)):
                distance = sum((candidate[index] - current[index]) ** 2
                               for index in range(5))
                candidates.append((distance, candidate))
        if not candidates:
            raise ValueError("腰腿逆解超出 URDF 关节限位")

        target = min(candidates, key=lambda item: item[0])[1]
        max_delta = max(abs(target[index] - current[index]) for index in range(5))
        if limit_joint_step and max_delta > self.waist_max_joint_step:
            raise ValueError(
                f"腰腿单次关节变化 {max_delta:.3f} rad 超过安全限制 "
                f"{self.waist_max_joint_step:.3f} rad")
        return target, self._waist_forward_kinematics(target)

    def _waist_inverse_kinematics(self, current, forward, up):
        """解析逆解 X/Z 增量，并保持上身俯仰及关节 4/5 不变。"""
        if len(current) != 5:
            raise ValueError("腰腿逆解需要 5 个当前关节角")
        if not all(math.isfinite(value) for value in [*current, forward, up]):
            raise ValueError("腰腿运动参数必须是有限数值")
        if abs(forward) > self.waist_max_cartesian_step or abs(up) > self.waist_max_cartesian_step:
            raise ValueError(
                f"单次腰腿位移不得超过 {self.waist_max_cartesian_step:.3f} m")

        current_pose = self._waist_forward_kinematics(current)
        target_x = current_pose["x"] + float(forward)
        target_z = current_pose["z"] + float(up)
        return self._solve_waist_target(
            current, target_x, target_z, current_pose["pitch"],
            current[3], current[4], limit_joint_step=True)

    def get_waist_status(self):
        """返回网页显示所需的腰腿笛卡尔位置和当前关节角。"""
        joints = self._get_current_waist_angles()
        pose = self._waist_forward_kinematics(joints)
        return {
            "x": round(pose["x"], 6), "y": round(pose["y"], 6),
            "z": round(pose["z"], 6),
            "rx": round(pose["roll"], 6),
            "ry": round(pose["pitch"], 6),
            "rz": round(pose["yaw"], 6),
            "pitch": round(pose["pitch"], 6),
            "joints": [round(value, 6) for value in joints],
        }

    @staticmethod
    def find_pose_in_status(status, target_name):
        """从已有运动状态中读取指定末端，避免重复调用 GDK。"""
        for index, frame_name in enumerate(status.frame_names):
            if frame_name != target_name:
                continue
            pose = status.frame_poses[index]
            return {
                "position": [
                    round(float(pose.position.x), 6),
                    round(float(pose.position.y), 6),
                    round(float(pose.position.z), 6),
                ],
                "orientation": [
                    round(float(pose.orientation.x), 6),
                    round(float(pose.orientation.y), 6),
                    round(float(pose.orientation.z), 6),
                    round(float(pose.orientation.w), 6),
                ],
            }
        return None

    def publish_status(self):
        payload = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        payload.update(self.get_end_effector_status())
        payload["waist_pose"] = self.get_waist_status()
        self.mqtt_client.publish(
            self.status_topic, json.dumps(payload, ensure_ascii=False), qos=0)
        return payload

    def _status_loop(self, interval):
        while not self._status_stop.is_set():
            try:
                self.publish_status()
            except Exception as error:
                print(f"[末端位姿状态] 发布失败: {error}")
            self._status_stop.wait(interval)

    def start_status_publishing(self, interval=0.2):
        if self._status_thread and self._status_thread.is_alive():
            return
        self._status_stop.clear()
        self._status_thread = threading.Thread(
            target=self._status_loop, args=(interval,), daemon=True,
            name="pose-status")
        self._status_thread.start()
        print(f"[末端位姿状态] 发布线程已启动，频率={1.0 / interval:.1f}Hz")

    def stop_status_publishing(self):
        self._status_stop.set()
    
    # ── 运动执行（不嵌套，直接调用 GDK）────────────────────
    
    def _send_trajectory(self, traj, group):
        """发送单臂轨迹"""
        dt = 1.0 / self.rate_hz
        
        for wp in traj:
            ep = self.agibot_gdk.EndEffectorPose()
            ep.life_time = self.lifetime
            ep.group = group
            
            if group == self.agibot_gdk.EndEffectorControlGroup.kLeftArm:
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
    
    def _send_dual_trajectory(self, traj_left, traj_right):
        """同时发送双臂轨迹"""
        dt = 1.0 / self.rate_hz
        
        for i in range(len(traj_left)):
            wp_l = traj_left[i]
            wp_r = traj_right[i]
            
            # 左臂
            ep_l = self.agibot_gdk.EndEffectorPose()
            ep_l.life_time = self.lifetime
            ep_l.group = self.agibot_gdk.EndEffectorControlGroup.kLeftArm
            ep_l.left_end_effector_pose.position.x = wp_l["position"][0]
            ep_l.left_end_effector_pose.position.y = wp_l["position"][1]
            ep_l.left_end_effector_pose.position.z = wp_l["position"][2]
            ep_l.left_end_effector_pose.orientation.x = wp_l["orientation"][0]
            ep_l.left_end_effector_pose.orientation.y = wp_l["orientation"][1]
            ep_l.left_end_effector_pose.orientation.z = wp_l["orientation"][2]
            ep_l.left_end_effector_pose.orientation.w = wp_l["orientation"][3]
            
            # 右臂
            ep_r = self.agibot_gdk.EndEffectorPose()
            ep_r.life_time = self.lifetime
            ep_r.group = self.agibot_gdk.EndEffectorControlGroup.kRightArm
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
    
    def _hold_at_pose(self, pose_l, pose_r, hold_sec=1.0):
        """在指定位姿保持"""
        n = int(hold_sec * self.rate_hz)
        hold_life = 0.1
        
        for _ in range(n):
            for pose, group in [(pose_l, self.agibot_gdk.EndEffectorControlGroup.kLeftArm),
                                (pose_r, self.agibot_gdk.EndEffectorControlGroup.kRightArm)]:
                ep = self.agibot_gdk.EndEffectorPose()
                ep.life_time = hold_life
                ep.group = group
                
                if group == self.agibot_gdk.EndEffectorControlGroup.kLeftArm:
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
    
    def move_left_arm(self, position, orientation):
        """控制左臂到绝对位姿"""
        with self._lock:
            print(f"[位姿] 左臂: {position}")
            
            start = self._find_pose(self.left_name)
            target = {"position": position, "orientation": orientation}
            
            n_steps = self._n_steps(start["position"], target["position"],
                                    start["orientation"], target["orientation"])
            
            traj = self._plan(start, target, n_steps)
            success = self._send_trajectory(traj, self.agibot_gdk.EndEffectorControlGroup.kLeftArm)
            
            if success:
                for _ in range(int(1.0 * self.rate_hz)):
                    self._send_trajectory([target], self.agibot_gdk.EndEffectorControlGroup.kLeftArm)
            
            print(f"[位姿] 左臂 {'完成' if success else '失败'}")
            return success
    
    def move_right_arm(self, position, orientation):
        """控制右臂到绝对位姿"""
        with self._lock:
            print(f"[位姿] 右臂: {position}")
            
            start = self._find_pose(self.right_name)
            target = {"position": position, "orientation": orientation}
            
            n_steps = self._n_steps(start["position"], target["position"],
                                    start["orientation"], target["orientation"])
            
            traj = self._plan(start, target, n_steps)
            success = self._send_trajectory(traj, self.agibot_gdk.EndEffectorControlGroup.kRightArm)
            
            if success:
                for _ in range(int(1.0 * self.rate_hz)):
                    self._send_trajectory([target], self.agibot_gdk.EndEffectorControlGroup.kRightArm)
            
            print(f"[位姿] 右臂 {'完成' if success else '失败'}")
            return success
    
    def move_both_arms(self, left_target, right_target):
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
            
            success = self._send_dual_trajectory(traj_l, traj_r)
            
            if success:
                self._hold_at_pose(traj_l[-1], traj_r[-1], hold_sec=1.0)
            
            print(f"[位姿] 双臂 {'完成' if success else '失败'}")
            return success
    
    def move_relative(self, side, offset, rotation):
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
            group = (self.agibot_gdk.EndEffectorControlGroup.kLeftArm if side == "left"
                     else self.agibot_gdk.EndEffectorControlGroup.kRightArm)
            success = self._send_trajectory(traj, group)
            
            print(f"[位姿] {side}臂 {'完成' if success else '失败'}")
            return success
    
    def move_waist(self, offset, speed=None):
        """腰腿笛卡尔相对运动：offset=[前后X, 侧向Y, 上下Z]，单位米。"""
        with self._lock:
            if not isinstance(offset, (list, tuple)) or len(offset) != 3:
                raise ValueError("腰腿 offset 必须是 [前后, 侧向, 上下]")
            forward, lateral, up = [float(value) for value in offset]
            if abs(lateral) > 1e-9:
                raise ValueError("腰腿当前只支持前后 X 和上下 Z，不支持侧向 Y")
            current = self._get_current_waist_angles()
            target, solved_pose = self._waist_inverse_kinematics(
                current, forward, up)
            velocity = self.waist_speed if speed is None else float(speed)
            if not 0.02 <= velocity <= 0.50:
                raise ValueError("腰腿关节速度必须在 0.02~0.50 rad/s")
            print(
                f"[位姿] 腰腿 X/Z: ({forward:+.3f}, {up:+.3f}) m, "
                f"目标=({solved_pose['x']:.3f}, {solved_pose['z']:.3f}) m")
            self.robot.move_waist_joint(target, [velocity] * 5)
            print("[位姿] 腰腿运动完成")
            return True

    def move_waist_to_pose(self, pose, speed=None):
        """腰腿绝对定位到保存的 x/y/z/rx/ry/rz 位姿。"""
        with self._lock:
            if not isinstance(pose, dict):
                raise ValueError("腰腿定位目标必须是 x/y/z/rx/ry/rz 对象")
            current = self._get_current_waist_angles()
            target, solved_pose = self._solve_waist_target(
                current,
                float(pose.get("x", 0.0)), float(pose.get("z", 0.0)),
                float(pose.get("ry", pose.get("pitch", 0.0))),
                float(pose.get("rx", pose.get("roll", 0.0))),
                float(pose.get("rz", pose.get("yaw", 0.0))))
            velocity = self.waist_speed if speed is None else float(speed)
            if not 0.02 <= velocity <= 0.50:
                raise ValueError("腰腿关节速度必须在 0.02~0.50 rad/s")
            print(
                f"[位姿] 腰腿绝对定位: X={solved_pose['x']:.3f}, "
                f"Z={solved_pose['z']:.3f}, RY={solved_pose['pitch']:.3f}")
            self.robot.move_waist_joint(target, [velocity] * 5)
            print("[位姿] 腰腿绝对定位完成")
            return True
    
    @staticmethod
    def _recover_quat(data):
        """从 {rx, ry, rz} 恢复四元数"""
        qx = data.get("rx", 0)
        qy = data.get("ry", 0)
        qz = data.get("rz", 0)
        qw = math.sqrt(max(0, 1 - qx*qx - qy*qy - qz*qz))
        return [qx, qy, qz, qw]

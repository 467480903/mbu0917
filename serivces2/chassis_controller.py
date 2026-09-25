#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chassis_controller.py — 底盘控制器

职责：
  - 相对运动（relative）：基于 GDK relative_move 接口
  - 到点运动（point）：读取数据库点位，使用 GDK normal_navi
  - 多点运动（points）：多个点位依次导航
  - 停止（stop）：停止底盘运动
  - 相对运动2（relative2）：带速度参数的相对运动，使用 move_chassis

注意：
  - 单位：x/y 为毫米，rotate 为角度，vel_line 为米/秒，vel_rotate 为度/秒
"""

import math
import time
import signal
import sys


class ChassisController:
    """底盘控制器"""
    
    def __init__(self, pnc, slam, mqtt_client, topic_response, topic_done):
        """构造函数
        
        Parameters
        ----------
        pnc : agibot_gdk.Pnc
            GDK Pnc 对象
        slam : agibot_gdk.Slam
            GDK Slam 对象
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        topic_done : str
            完成信号主题
        """
        self.pnc = pnc
        self.slam = slam
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.topic_done = topic_done
        self._chassis_mode = -1  # -1=未申请, 0=Ackermann, 1=蟹行
        
        # 导航任务状态码
        self._task_states = {
            0: "空闲", 1: "启动中", 2: "运行中", 3: "暂停中",
            4: "已暂停", 5: "恢复中", 6: "取消中", 7: "已取消",
            8: "失败", 9: "成功",
        }
        self._done_states = {7, 8, 9}
        
        # 默认参数
        self.ctrl_hz = 20
        self.ctrl_dt = 1.0 / self.ctrl_hz
        self.stop_speed_thresh = 0.05
        
        # 注册退出信号
        signal.signal(signal.SIGINT, self._on_exit)
        signal.signal(signal.SIGTERM, self._on_exit)
    
    def _on_exit(self, *_):
        print("\n[底盘] 收到退出信号，停止机器人...")
        self._stop_chassis()
        self._cancel_navi()
        sys.exit(0)
    
    # ── 工具函数（不嵌套，直接调用 GDK）────────────────────
    
    def _task_state(self):
        """获取当前任务状态"""
        ts = self.pnc.get_task_state()
        return ts.state, ts.id, ts.message
    
    def _cancel_navi(self):
        """取消导航任务"""
        try:
            ts = self.pnc.get_task_state()
            if ts.state not in self._done_states:
                self.pnc.cancel_task(ts.id)
                time.sleep(0.3)
        except Exception:
            pass
    
    def _request_chassis(self, mode, agibot_gdk):
        """申请底盘控制权"""
        if self._chassis_mode != mode:
            self.pnc.request_chassis_control(mode)
            time.sleep(0.3)
            self._chassis_mode = mode
    
    def _make_twist(self, agibot_gdk, vx=0.0, vy=0.0, wz=0.0):
        """创建 Twist 消息"""
        twist = agibot_gdk.Twist()
        twist.linear = agibot_gdk.Vector3()
        twist.angular = agibot_gdk.Vector3()
        twist.linear.x = vx
        twist.linear.y = vy
        twist.linear.z = 0.0
        twist.angular.x = 0.0
        twist.angular.y = 0.0
        twist.angular.z = wz
        return twist
    
    def _stop_chassis(self, agibot_gdk):
        """停止底盘"""
        try:
            twist = self._make_twist(agibot_gdk)
            for _ in range(5):
                self.pnc.move_chassis(twist)
                time.sleep(0.05)
        except Exception:
            pass
    
    def _get_speed(self):
        """获取当前速度"""
        try:
            odom = self.slam.get_odom_info()
            return math.hypot(odom.velocity.x, odom.velocity.y)
        except Exception:
            return 0.0
    
    def _wait_stop(self, timeout=3.0):
        """等待停止"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._get_speed() < self.stop_speed_thresh:
                break
            time.sleep(0.1)
    
    def _get_current_pose(self):
        """获取当前位姿"""
        pose = self.slam.get_curr_pose()
        return {
            "x": pose.position.x,
            "y": pose.position.y,
            "yaw": self._quat_to_yaw(
                pose.orientation.x, pose.orientation.y,
                pose.orientation.z, pose.orientation.w
            )
        }
    
    @staticmethod
    def _quat_to_yaw(x, y, z, w):
        """四元数转 yaw"""
        return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    
    @staticmethod
    def _normalize_angle(angle):
        """角度归一化到 [-π, π)"""
        return (angle + math.pi) % (2.0 * math.pi) - math.pi
    
    def _wait_navi_done(self, timeout):
        """等待导航完成"""
        start = time.time()
        
        # 等待启动
        started = False
        for _ in range(20):
            time.sleep(0.5)
            state, _, msg = self._task_state()
            if state == 2:
                started = True
                break
            if state in self._done_states:
                break
        
        if not started:
            state, _, msg = self._task_state()
            if state == 9:
                print("[底盘] 已在目标点附近")
                return True
            print(f"[底盘] 任务未能启动: {self._task_states.get(state, state)}")
            return False
        
        # 等待完成
        while time.time() - start < timeout:
            time.sleep(0.5)
            state, _, msg = self._task_state()
            
            if state == 9:
                self._wait_stop()
                print(f"[底盘] 完成，耗时 {time.time()-start:.1f}s")
                return True
            
            if state in {7, 8}:
                print(f"[底盘] 失败: {self._task_states.get(state, state)}")
                return False
        
        print("[底盘] 超时")
        self._cancel_navi()
        return False
    
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
            "cmd": cmd, "time": ts, "type": "base"
        }, ensure_ascii=False))
    
    # ── 运动命令（不嵌套，直接调用 GDK）────────────────────
    
    def relative_move(self, agibot_gdk, x_mm, y_mm, rotate_deg, timeout=60.0):
        """相对运动（基于 GDK relative_move）
        
        Parameters
        ----------
        agibot_gdk : module
            GDK 模块
        x_mm : float
            x 方向位移（毫米）
        y_mm : float
            y 方向位移（毫米）
        rotate_deg : float
            旋转角度（度）
        timeout : float
            超时时间（秒）
        """
        # 转换单位：毫米 → 米，度 → 弧度
        dx = x_mm / 1000.0
        dy = y_mm / 1000.0
        yaw_rad = math.radians(rotate_deg)
        
        # 无位移无旋转
        if abs(dx) < 0.001 and abs(dy) < 0.001 and abs(yaw_rad) < 0.001:
            return True
        
        # 取消旧任务
        state, _, _ = self._task_state()
        if state not in self._done_states and state != 0:
            self._cancel_navi()
        
        # yaw 转四元数
        half = yaw_rad / 2.0
        qz = math.sin(half)
        qw = math.cos(half)
        
        # 构建请求
        req = agibot_gdk.NaviReq()
        req.target.position.x = dx
        req.target.position.y = dy
        req.target.position.z = 0.0
        req.target.orientation.x = 0.0
        req.target.orientation.y = 0.0
        req.target.orientation.z = qz
        req.target.orientation.w = qw
        
        print(f"[底盘] 相对运动: dx={dx:+.3f}m dy={dy:+.3f}m yaw={rotate_deg:+.1f}°")
        
        try:
            self.pnc.relative_move(req)
        except Exception as e:
            print(f"[底盘] 发送失败: {e}")
            return False
        
        return self._wait_navi_done(timeout)
    
    def point_move(self, agibot_gdk, point, timeout=120.0):
        """到点运动
        
        Parameters
        ----------
        agibot_gdk : module
            GDK 模块
        point : dict
            地图点位 {position: [x,y,z], orientation: [x,y,z,w], name: str}
        timeout : float
            超时时间（秒）
        """
        pos = point["position"]
        ori = point["orientation"]
        name = point.get("name", "")
        
        print(f"[底盘] 到点运动: {name} ({pos[0]:.3f}, {pos[1]:.3f})")
        
        # 构建导航请求
        req = agibot_gdk.NaviReq()
        req.target.position.x = pos[0]
        req.target.position.y = pos[1]
        req.target.position.z = pos[2] if len(pos) > 2 else 0.0
        req.target.orientation.x = ori[0]
        req.target.orientation.y = ori[1]
        req.target.orientation.z = ori[2]
        req.target.orientation.w = ori[3]
        
        # 取消旧任务
        state, _, _ = self._task_state()
        if state not in self._done_states and state != 0:
            self._cancel_navi()
        
        try:
            self.pnc.normal_navi(req)
        except Exception as e:
            print(f"[底盘] 发送失败: {e}")
            return False
        
        return self._wait_navi_done(timeout)
    
    def points_move(self, agibot_gdk, points, vel_line=0.25, vel_rotate_deg=10.0, timeout=120.0):
        """多点运动
        
        Parameters
        ----------
        agibot_gdk : module
            GDK 模块
        points : list
            地图点位列表，每个元素为 {position, orientation, name}
        vel_line : float
            线速度（米/秒）
        vel_rotate_deg : float
            角速度（度/秒）
        timeout : float
            每个点的超时时间（秒）
        """
        print(f"[底盘] 多点运动: {' → '.join(p.get('name', '') for p in points)}")
        
        for i, point in enumerate(points):
            name = point.get("name", "")
            # 最后一个点用 normal_navi（高精度）
            if i == len(points) - 1:
                ok = self.point_move(agibot_gdk, point, timeout)
            else:
                # 计算到下一个点的相对位置
                current = self._get_current_pose()
                dx = (point["position"][0] - current["x"]) * 1000  # 米 → 毫米
                dy = (point["position"][1] - current["y"]) * 1000
                target_yaw = self._quat_to_yaw(*point["orientation"])
                d_yaw = math.degrees(self._normalize_angle(target_yaw - current["yaw"]))
                
                ok = self.relative2_move(agibot_gdk, dx, dy, d_yaw, vel_line, vel_rotate_deg, timeout=timeout)
            
            if not ok:
                print(f"[底盘] 在 {name} 失败")
                return False
            
            time.sleep(0.5)
        
        print("[底盘] 多点运动完成")
        return True
    
    def stop(self, agibot_gdk):
        """停止底盘运动"""
        print("[底盘] 停止")
        self._cancel_navi()
        self._stop_chassis(agibot_gdk)
        self._wait_stop()
        return True
    
    def relative2_move(self, agibot_gdk, x_mm, y_mm, rotate_deg, vel_line=0.25, vel_rotate_deg=10.0, timeout=60.0):
        """相对运动2（带速度参数，使用 move_chassis）
        
        实现要点：
          1. 计算当前位置到目标位置的斜率和目标角度
          2. 执行转角运动（角速度 vel_rotate）
          3. 蟹行直线运动（分12段：前4段加速，中4段匀速，后4段减速）
          4. 到达后再执行最终转角
        
        Parameters
        ----------
        agibot_gdk : module
            GDK 模块
        x_mm : float
            x 方向位移（毫米）
        y_mm : float
            y 方向位移（毫米）
        rotate_deg : float
            最终旋转角度（度）
        vel_line : float
            线速度（米/秒）
        vel_rotate_deg : float
            角速度（度/秒）
        timeout : float
            超时时间（秒）
        """
        # 转换单位
        dx = x_mm / 1000.0  # 米
        dy = y_mm / 1000.0  # 米
        final_yaw = math.radians(rotate_deg)
        wz = math.radians(vel_rotate_deg)  # rad/s
        
        # 无位移无旋转
        if abs(dx) < 0.001 and abs(dy) < 0.001 and abs(final_yaw) < 0.001:
            return True
        
        print(f"[底盘] 相对运动2: dx={dx:+.3f}m dy={dy:+.3f}m yaw={rotate_deg:+.1f}°")
        
        current = self._get_current_pose()
        start_time = time.time()
        
        try:
            # 第一步：转向目标方向
            if abs(dx) > 0.001 or abs(dy) > 0.001:
                target_angle = math.atan2(dy, dx)
                yaw_diff = self._normalize_angle(target_angle - current["yaw"])
                
                if abs(yaw_diff) > 0.02:  # > 1度
                    print(f"[底盘] 转向目标方向: {math.degrees(yaw_diff):.1f}°")
                    self._rotate_to(agibot_gdk, current["yaw"] + yaw_diff, wz, timeout - (time.time() - start_time))
            
            # 第二步：直线运动（分12段）
            if abs(dx) > 0.001 or abs(dy) > 0.001:
                distance = math.hypot(dx, dy)
                print(f"[底盘] 直线运动: {distance:.3f}m")
                self._move_line(agibot_gdk, dx, dy, vel_line, timeout - (time.time() - start_time))
            
            # 第三步：最终旋转
            if abs(final_yaw) > 0.001:
                print(f"[底盘] 最终旋转: {rotate_deg:.1f}°")
                self._rotate_to(agibot_gdk, current["yaw"] + final_yaw, wz, timeout - (time.time() - start_time))
            
            return True
        
        except Exception as e:
            print(f"[底盘] 错误: {e}")
            return False
        
        finally:
            self._stop_chassis(agibot_gdk)
            self._wait_stop()
    
    def _rotate_to(self, agibot_gdk, target_yaw, wz, timeout):
        """旋转到目标角度"""
        self._request_chassis(0, agibot_gdk)  # Ackermann 模式
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            current = self._get_current_pose()
            yaw_diff = self._normalize_angle(target_yaw - current["yaw"])
            
            if abs(yaw_diff) < 0.02:  # < 1度
                break
            
            actual_wz = max(-abs(wz), min(abs(wz), yaw_diff))
            twist = self._make_twist(agibot_gdk, wz=actual_wz)
            self.pnc.move_chassis(twist)
            time.sleep(self.ctrl_dt)
    
    def _move_line(self, agibot_gdk, dx, dy, max_speed, timeout):
        """直线运动（蟹行，分12段）"""
        self._request_chassis(1, agibot_gdk)  # 蟹行模式
        deadline = time.time() + timeout
        
        distance = math.hypot(dx, dy)
        if distance < 0.01:
            return
        
        # 方向向量
        dir_x = dx / distance
        dir_y = dy / distance
        
        # 12段运动队列
        segments = []
        seg_dist = distance / 12.0
        
        # 前4段加速
        for i in range(4):
            speed = max_speed * (i + 1) / 4.0
            segments.append((seg_dist / speed, speed))
        
        # 中4段匀速
        for _ in range(4):
            segments.append((seg_dist / max_speed, max_speed))
        
        # 后4段减速
        for i in range(4):
            speed = max_speed * (4 - i) / 4.0
            segments.append((seg_dist / speed, speed))
        
        # 执行运动
        start_pose = self._get_current_pose()
        
        for duration, speed in segments:
            if time.time() > deadline:
                break
            
            vx = dir_x * speed
            vy = dir_y * speed
            
            twist = self._make_twist(agibot_gdk, vx=vx, vy=vy)
            
            seg_start = time.time()
            while time.time() - seg_start < duration and time.time() < deadline:
                self.pnc.move_chassis(twist)
                time.sleep(self.ctrl_dt)
                
                current = self._get_current_pose()
                traveled = math.hypot(
                    current["x"] - start_pose["x"],
                    current["y"] - start_pose["y"]
                )
                if traveled >= distance * 0.95:
                    return

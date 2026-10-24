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

import base64
import gzip
import json
import math
import signal
import struct
import sys
import threading
import time


class ChassisController:
    """底盘控制器"""
    
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
        self.pnc = self.agibot_gdk.Pnc()
        self.slam = self.agibot_gdk.Slam()
        self.map = self.agibot_gdk.Map()
        self.lidar = self.agibot_gdk.Lidar()
        self.robot = self.agibot_gdk.Robot()
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.topic_done = topic_done
        self.status_topic = "/humanoid/status/data"
        self.cloud_topic = "/humanoid/status/cloud"
        self._status_stop = threading.Event()
        self._status_thread = None
        self._cloud_enabled = threading.Event()
        self._is_mapping = False
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
    
    def _request_chassis(self, mode):
        """申请底盘控制权"""
        if self._chassis_mode != mode:
            self.pnc.request_chassis_control(mode)
            time.sleep(0.3)
            self._chassis_mode = mode
    
    def _make_twist(self, vx=0.0, vy=0.0, wz=0.0):
        """创建 Twist 消息"""
        twist = self.agibot_gdk.Twist()
        twist.linear = self.agibot_gdk.Vector3()
        twist.angular = self.agibot_gdk.Vector3()
        twist.linear.x = vx
        twist.linear.y = vy
        twist.linear.z = 0.0
        twist.angular.x = 0.0
        twist.angular.y = 0.0
        twist.angular.z = wz
        return twist
    
    def _stop_chassis(self):
        """停止底盘"""
        try:
            twist = self._make_twist()
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

    def get_map_points(self):
        """读取当前地图中的全部引导点。

        Returns
        -------
        list[dict]
            按点位名称排序的列表。每项包含 map_id、name、source、
            position、orientation 和 type。
        """
        time.sleep(1.0)
        current_map = self.map.get_curr_map()
        map_info = self.map.get_map(current_map.id)
        points = []

        for point in map_info.guide_pts:
            points.append({
                "map_id": current_map.id,
                "name": str(point.id),
                "source": "map",
                "position": [
                    point.pt.position.x,
                    point.pt.position.y,
                    point.pt.position.z,
                ],
                "orientation": [
                    point.pt.orientation.x,
                    point.pt.orientation.y,
                    point.pt.orientation.z,
                    point.pt.orientation.w,
                ],
                "type": str(point.type),
            })

        points.sort(key=lambda item: item["name"])
        print(f"[底盘] 当前地图 id={current_map.id}，读取到 {len(points)} 个点位")
        return points

    def get_map_data(self):
        """读取当前地图的 OccupancyGrid，并编码为浏览器可传输的数据。"""
        current_map = self.map.get_curr_map()
        map_info = self.map.get_map(current_map.id)
        grid = map_info.grid_map
        origin = grid.origin
        raw = struct.pack(f"{len(grid.data)}b", *grid.data)
        compressed = gzip.compress(raw, compresslevel=6)
        return {
            "id": current_map.id,
            "name": str(getattr(map_info, "name", "")),
            "width": grid.width,
            "height": grid.height,
            "resolution": grid.resolution,
            "origin": {
                "position": [origin.position.x, origin.position.y, origin.position.z],
                "orientation": [
                    origin.orientation.x, origin.orientation.y,
                    origin.orientation.z, origin.orientation.w,
                ],
            },
            "data_encoding": "gzip-base64",
            "data_b64": base64.b64encode(compressed).decode("ascii"),
        }

    def get_legacy_map_grid(self, map_id=None):
        """读取旧 web 使用的未压缩 base64 栅格地图。"""
        if map_id is None:
            map_id = self.map.get_curr_map().id
        map_info = self.map.get_map(int(map_id))
        grid = map_info.grid_map
        origin = grid.origin
        raw = struct.pack(f"{len(grid.data)}b", *grid.data)
        return {
            "map_id": map_info.id,
            "map_name": str(getattr(map_info, "name", "")),
            "width": grid.width,
            "height": grid.height,
            "resolution": grid.resolution,
            "origin": {
                "position": [origin.position.x, origin.position.y, origin.position.z],
                "orientation": [
                    origin.orientation.x, origin.orientation.y,
                    origin.orientation.z, origin.orientation.w,
                ],
            },
            "data_b64": base64.b64encode(raw).decode("ascii"),
        }

    def get_maps(self):
        """读取机器人内全部地图，用于旧 web 地图选择器。"""
        return [
            {
                "id": item.id,
                "name": str(item.name),
                "is_current": bool(item.is_curr_map),
            }
            for item in self.map.get_all_map()
        ]

    def switch_map(self, map_id):
        self.map.switch_map(int(map_id))
        return True

    def start_mapping(self):
        self.slam.start_mapping()
        self._is_mapping = True
        return True

    def stop_mapping(self):
        self.slam.stop_mapping()
        self._is_mapping = False
        return True

    def is_mapping(self):
        return self._is_mapping

    @staticmethod
    def _point_field_offsets(pointcloud):
        return {
            field.name: field.offset
            for field in pointcloud.fields
            if field.name in {"x", "y", "z"}
        }

    def _read_lidar_points(self, lidar_type, source, sample_step, max_distance):
        pointcloud = None
        last_error = None
        for _ in range(3):
            try:
                pointcloud = self.lidar.get_latest_pointcloud(lidar_type, 1000.0)
            except Exception as exc:
                last_error = exc
            if pointcloud is not None:
                break
            time.sleep(0.2)
        if pointcloud is None and last_error is not None:
            print(f"[底盘] {source} 激光点云暂不可用: {last_error}")
        if pointcloud is None or pointcloud.point_step <= 0:
            return []
        offsets = self._point_field_offsets(pointcloud)
        if not {"x", "y", "z"}.issubset(offsets):
            return []
        raw = bytes(pointcloud.data)
        count = len(raw) // pointcloud.point_step
        points = []
        for index in range(0, count, sample_step):
            base = index * pointcloud.point_step
            x = struct.unpack_from("<f", raw, base + offsets["x"])[0]
            y = struct.unpack_from("<f", raw, base + offsets["y"])[0]
            z = struct.unpack_from("<f", raw, base + offsets["z"])[0]
            if not all(math.isfinite(value) for value in (x, y, z)):
                continue
            if math.sqrt(x * x + y * y + z * z) > max_distance:
                continue
            points.append([round(x, 3), round(y, 3), round(z, 3), source])
        return points

    def get_laser_points(self, sample_step=4, max_distance=30.0):
        """读取前后激光雷达点云，过滤并降采样。"""
        front = self._read_lidar_points(
            self.agibot_gdk.LidarType.kLidarFront,
            "front", sample_step, max_distance)
        back = self._read_lidar_points(
            self.agibot_gdk.LidarType.kLidarBack,
            "back", sample_step, max_distance)
        return {
            "points": front + back,
            "count": len(front) + len(back),
            "front": len(front),
            "back": len(back),
        }

    def get_current_map_pose(self):
        """读取底盘当前在地图坐标系中的位置、朝向与定位状态。"""
        pose = self.slam.get_curr_pose()
        result = {
            "position": [pose.position.x, pose.position.y, pose.position.z],
            "orientation": [
                pose.orientation.x, pose.orientation.y,
                pose.orientation.z, pose.orientation.w,
            ],
            "yaw": self._quat_to_yaw(
                pose.orientation.x, pose.orientation.y,
                pose.orientation.z, pose.orientation.w),
            "loc_state": -1,
            "loc_confidence": 0.0,
        }
        try:
            odom = self.slam.get_odom_info()
            result["loc_state"] = odom.loc_state
            result["loc_confidence"] = odom.loc_confidence
        except Exception:
            pass
        return result

    def publish_status(self):
        """发布旧 web 所需的底盘地图坐标状态片段。"""
        pose = self.get_current_map_pose()
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "chassis": {
                "x": round(float(pose["position"][0]), 6),
                "y": round(float(pose["position"][1]), 6),
                "z": round(float(pose["position"][2]), 6),
                "yaw": round(float(pose["yaw"]), 6),
                "loc_state": pose["loc_state"],
                "loc_confidence": round(float(pose["loc_confidence"]), 4),
            },
        }
        self.mqtt_client.publish(
            self.status_topic, json.dumps(payload, ensure_ascii=False), qos=0)
        return payload

    def publish_cloud(self):
        """按旧 web 格式发布降采样后的前后激光点云。"""
        laser = self.get_laser_points()
        payload = {
            "timestamp": int(time.time() * 1_000_000_000),
            "count": laser["count"],
            "front_count": laser["front"],
            "back_count": laser["back"],
            "points": [point[:3] for point in laser["points"]],
        }
        self.mqtt_client.publish(
            self.cloud_topic, json.dumps(payload, ensure_ascii=False), qos=0)
        return payload

    def set_cloud_publishing(self, enabled):
        if enabled:
            self._cloud_enabled.set()
        else:
            self._cloud_enabled.clear()
        print(f"[底盘状态] 激光点云发布{'开启' if enabled else '关闭'}")

    def _status_loop(self, status_interval, cloud_interval):
        last_cloud = 0.0
        while not self._status_stop.is_set():
            started = time.monotonic()
            try:
                self.publish_status()
            except Exception as error:
                print(f"[底盘状态] 发布失败: {error}")
            if self._cloud_enabled.is_set() and started - last_cloud >= cloud_interval:
                try:
                    self.publish_cloud()
                except Exception as error:
                    print(f"[激光点云] 发布失败: {error}")
                last_cloud = started
            elapsed = time.monotonic() - started
            self._status_stop.wait(max(0.0, status_interval - elapsed))

    def start_status_publishing(self, status_interval=0.2, cloud_interval=1.0):
        if self._status_thread and self._status_thread.is_alive():
            return
        self._status_stop.clear()
        self._status_thread = threading.Thread(
            target=self._status_loop,
            args=(status_interval, cloud_interval), daemon=True,
            name="chassis-status")
        self._status_thread.start()
        print(f"[底盘状态] 发布线程已启动，频率={1.0 / status_interval:.1f}Hz")

    def stop_status_publishing(self):
        self._status_stop.set()

    def get_battery(self):
        """读取底盘电池组状态与平均电量。"""
        power = self.robot.get_chassis_power_state()
        batteries = []
        for index, state in enumerate(power.battery_states):
            batteries.append({
                "index": index + 1,
                "soc": state.battery_soc,
                "soh": state.battery_soh,
                "voltage": state.battery_output_voltage,
                "current": state.battery_output_current,
                "temperature": state.battery_temperature,
                "charging": bool(state.battery_charging_status),
            })
        soc = sum(item["soc"] for item in batteries) / len(batteries) if batteries else None
        return {"soc": round(soc, 1) if soc is not None else None, "batteries": batteries}

    def get_map_snapshot(self):
        """一次读取页面展示所需的全部真实机器人地图数据。"""
        return {
            "map": self.get_map_data(),
            "laser": self.get_laser_points(),
            "points": self.get_map_points(),
            "pose": self.get_current_map_pose(),
            "battery": self.get_battery(),
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
    
    # X + , 前进, Y + , 靠左， rot + 逆时针
    def relative_move(self, x_mm, y_mm, rotate_deg, timeout=60.0):
        """相对运动（基于 GDK relative_move）
        
        Parameters
        ----------
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
        req = self.agibot_gdk.NaviReq()
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
    
    def point_move2(self, point):
        """到点运动
        
        Parameters
        ----------
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
        req = self.agibot_gdk.NaviReq()
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
            return True
        except Exception as e:
            print(f"[底盘] 发送失败: {e}")
            return False
        

    def point_move(self, point, timeout=120.0):
        if not self.point_move2(point):
            return False
        return self._wait_navi_done(timeout)
    
    def points_move(self, points, vel_line=0.25, vel_rotate_deg=10.0, timeout=120.0):
        """多点运动
        
        Parameters
        ----------
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
                ok = self.point_move(point, timeout)
            else:
                # 计算到下一个点的相对位置
                current = self._get_current_pose()
                dx = (point["position"][0] - current["x"]) * 1000  # 米 → 毫米
                dy = (point["position"][1] - current["y"]) * 1000
                target_yaw = self._quat_to_yaw(*point["orientation"])
                d_yaw = math.degrees(self._normalize_angle(target_yaw - current["yaw"]))
                
                ok = self.relative2_move(dx, dy, d_yaw, vel_line, vel_rotate_deg, timeout=timeout)
            
            if not ok:
                print(f"[底盘] 在 {name} 失败")
                return False
            
            time.sleep(0.5)
        
        print("[底盘] 多点运动完成")
        return True
    
    def stop(self):
        """停止底盘运动"""
        print("[底盘] 停止")
        self._cancel_navi()
        self._stop_chassis()
        self._wait_stop()
        return True
    
    def relative2_move(self, x_mm, y_mm, rotate_deg, vel_line=0.25, vel_rotate_deg=10.0, timeout=60.0):
        """相对运动2（带速度参数，使用 move_chassis）
        
        实现要点：
          1. 计算当前位置到目标位置的斜率和目标角度
          2. 执行转角运动（角速度 vel_rotate）
          3. 蟹行直线运动（分12段：前4段加速，中4段匀速，后4段减速）
          4. 到达后再执行最终转角
        
        Parameters
        ----------
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
                    self._rotate_to(current["yaw"] + yaw_diff, wz, timeout - (time.time() - start_time))
            
            # 第二步：直线运动（分12段）
            if abs(dx) > 0.001 or abs(dy) > 0.001:
                distance = math.hypot(dx, dy)
                print(f"[底盘] 直线运动: {distance:.3f}m")
                self._move_line(dx, dy, vel_line, timeout - (time.time() - start_time))
            
            # 第三步：最终旋转
            if abs(final_yaw) > 0.001:
                print(f"[底盘] 最终旋转: {rotate_deg:.1f}°")
                self._rotate_to(current["yaw"] + final_yaw, wz, timeout - (time.time() - start_time))
            
            return True
        
        except Exception as e:
            print(f"[底盘] 错误: {e}")
            return False
        
        finally:
            self._stop_chassis()
            self._wait_stop()
    
    def _rotate_to(self, target_yaw, wz, timeout):
        """旋转到目标角度"""
        self._request_chassis(0)  # Ackermann 模式
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            current = self._get_current_pose()
            yaw_diff = self._normalize_angle(target_yaw - current["yaw"])
            
            if abs(yaw_diff) < 0.02:  # < 1度
                break
            
            actual_wz = max(-abs(wz), min(abs(wz), yaw_diff))
            twist = self._make_twist(wz=actual_wz)
            self.pnc.move_chassis(twist)
            time.sleep(self.ctrl_dt)
    
    def _move_line(self, dx, dy, max_speed, timeout):
        """直线运动（蟹行，分12段）"""
        self._request_chassis(1)  # 蟹行模式
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
            
            twist = self._make_twist(vx=vx, vy=vy)
            
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
camera_controller.py — 摄像头控制器

职责：
  - 控制头部彩色相机、头部深度相机、左右手腕相机的视频流输出和拍照保存
"""

import os
import time
import base64
import json
import threading
from datetime import datetime

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class CameraController:
    """摄像头控制器"""
    
    def __init__(self, agibot_gdk, mqtt_client, topic_response, image_save_dir):
        """构造函数
        
        Parameters
        ----------
        agibot_gdk : module
            已初始化的 GDK 模块
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        image_save_dir : str
            图片保存目录
        """
        self.agibot_gdk = agibot_gdk
        self.camera = self.agibot_gdk.Camera()
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.image_save_dir = image_save_dir
        self.camera_data_topic = "/humanoid/camera/data"
        self._camera_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._latest_frames = {}
        self._cache_stop = threading.Event()
        self._cache_thread = None
        self._stream_enabled = threading.Event()
        self._continuous_enabled = threading.Event()
        self._last_continuous_capture = 0.0
        
        # JPEG 质量
        self.jpeg_quality = 60
    
    def _publish_response(self, cmd, ts, success=False, extra=None):
        """发布反馈报文"""
        import json
        resp = {"cmd": cmd, "time": ts}
        if success:
            resp["success"] = True
        if extra:
            resp.update(extra)
        self.mqtt_client.publish(self.topic_response, json.dumps(resp, ensure_ascii=False))
    
    def _get_camera_type(self, camera_name):
        """获取相机类型枚举"""
        camera_map = {
            "kHeadColor": self.agibot_gdk.CameraType.kHeadColor,
            "kHeadDepth": self.agibot_gdk.CameraType.kHeadDepth,
            "kHandLeftColor": self.agibot_gdk.CameraType.kHandLeftColor,
            "kHandRightColor": self.agibot_gdk.CameraType.kHandRightColor,
        }
        return camera_map.get(camera_name)
    
    # ── 拍照（不嵌套，直接调用 GDK）────────────────────
    
    def _encode_jpeg(self, image, camera_name):
        """把 GDK 图像统一编码为可供网页显示和保存的 JPEG。"""
        raw = bytes(image.data)
        encoding = getattr(image, "encoding", None)
        if encoding == self.agibot_gdk.Encoding.JPEG:
            return raw
        if not HAS_CV2:
            print(f"[摄像头] {camera_name} 不是 JPEG，且未安装 OpenCV")
            return None

        try:
            if encoding == self.agibot_gdk.Encoding.PNG:
                bgr = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            elif camera_name == "kHeadDepth":
                pixel_count = image.width * image.height
                dtype = np.uint16 if len(raw) == pixel_count * 2 else np.uint8
                depth = np.frombuffer(raw, dtype=dtype).reshape((image.height, image.width))
                valid = depth > 0
                if np.any(valid):
                    minimum = depth[valid].min()
                    maximum = depth[valid].max()
                    if maximum > minimum:
                        normalized = ((depth.astype(np.float32) - minimum) /
                                      (maximum - minimum) * 255).astype(np.uint8)
                    else:
                        normalized = np.zeros_like(depth, dtype=np.uint8)
                else:
                    normalized = np.zeros_like(depth, dtype=np.uint8)
                bgr = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
            else:
                pixels = np.frombuffer(raw, dtype=np.uint8)
                color_format = getattr(image, "color_format", None)
                if color_format == self.agibot_gdk.ColorFormat.GRAY8:
                    gray = pixels.reshape((image.height, image.width))
                    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                else:
                    color = pixels.reshape((image.height, image.width, 3))
                    bgr = (cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
                           if color_format == self.agibot_gdk.ColorFormat.RGB
                           else color)
            ok, buffer = cv2.imencode(
                ".jpg", bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
            )
            return bytes(buffer) if ok else None
        except Exception as exc:
            print(f"[摄像头] {camera_name} JPEG 编码失败: {exc}")
            return None

    def _save_jpeg(self, camera_name, jpeg_data):
        """同时保存带时间戳的日志图片和供识别使用的 latest 图片。"""
        os.makedirs(self.image_save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{camera_name}-{timestamp}.jpg"
        latest_filename = f"{camera_name}-latest.jpg"
        with open(os.path.join(self.image_save_dir, filename), "wb") as stream:
            stream.write(jpeg_data)
        with open(os.path.join(self.image_save_dir, latest_filename), "wb") as stream:
            stream.write(jpeg_data)
        print(f"[摄像头] 拍照: {filename}；最新图片: {latest_filename}")
        return filename

    def capture(self, camera_name):
        """拍照并保存
        
        Parameters
        ----------
        camera_name : str
            相机名称，如 "kHeadColor"
        
        Returns
        -------
        str
            保存的文件名，失败返回 None
        """
        camera_type = self._get_camera_type(camera_name)
        if camera_type is None:
            print(f"[摄像头] 未知相机: {camera_name}")
            return None
        
        try:
            with self._camera_lock:
                image = self.camera.get_latest_image(camera_type, 1000.0)
            if image is None or image.data is None:
                print(f"[摄像头] {camera_name} 无数据")
                return None
            
            jpeg_data = self._encode_jpeg(image, camera_name)
            return self._save_jpeg(camera_name, jpeg_data) if jpeg_data else None
        
        except Exception as e:
            print(f"[摄像头] 错误: {e}")
            return None
    
    def capture_all(self):
        """拍摄所有相机"""
        saved = []
        for camera_name in ["kHeadColor", "kHeadDepth", "kHandLeftColor", "kHandRightColor"]:
            filename = self.capture(camera_name)
            if filename:
                saved.append({"camera": camera_name, "file": filename})
        return saved
    
    def get_image_base64(self, camera_name):
        """获取图像的 base64 编码"""
        with self._frame_lock:
            cached = self._latest_frames.get(camera_name)
        if cached:
            return cached
        camera_type = self._get_camera_type(camera_name)
        if camera_type is None:
            return None
        
        try:
            with self._camera_lock:
                image = self.camera.get_latest_image(camera_type, 1000.0)
            if image is None or image.data is None:
                return None
            
            jpeg_data = self._encode_jpeg(image, camera_name)
            return base64.b64encode(jpeg_data).decode("ascii") if jpeg_data else None
        
        except Exception as e:
            print(f"[摄像头] 错误: {e}")
            return None

    def get_cached_frames(self):
        """返回线程安全的四路相机内存快照。"""
        with self._frame_lock:
            return dict(self._latest_frames)

    def set_streaming(self, enabled):
        """控制是否将内存中的相机帧发布给旧 web。"""
        if enabled:
            self._stream_enabled.set()
        else:
            self._stream_enabled.clear()
        print(f"[摄像头] 网页图像流{'开启' if enabled else '关闭'}")

    def set_continuous_capture(self, enabled):
        if enabled:
            self._continuous_enabled.set()
        else:
            self._continuous_enabled.clear()
        print(f"[摄像头] 连续拍照{'开启' if enabled else '关闭'}")

    def publish_cached_frames(self):
        """按旧 web 字段名发布当前四路相机缓存。"""
        key_map = {
            "kHeadColor": "head_color",
            "kHeadDepth": "head_depth",
            "kHandLeftColor": "left_wrist",
            "kHandRightColor": "right_wrist",
        }
        cached = self.get_cached_frames()
        payload = {"timestamp": int(time.time() * 1_000_000_000)}
        for camera_name, output_key in key_map.items():
            if cached.get(camera_name):
                payload[output_key] = cached[camera_name]
        self.mqtt_client.publish(
            self.camera_data_topic, json.dumps(payload, ensure_ascii=False), qos=0)
        return payload

    def _refresh_frame_cache(self):
        frames = {}
        for camera_name in (
            "kHeadColor", "kHeadDepth", "kHandLeftColor", "kHandRightColor"
        ):
            camera_type = self._get_camera_type(camera_name)
            try:
                with self._camera_lock:
                    image = self.camera.get_latest_image(camera_type, 1000.0)
                jpeg_data = self._encode_jpeg(image, camera_name) if image is not None else None
                if jpeg_data:
                    frames[camera_name] = base64.b64encode(jpeg_data).decode("ascii")
            except Exception as error:
                print(f"[摄像头缓存] {camera_name} 读取失败: {error}")
        with self._frame_lock:
            self._latest_frames.update(frames)
        return frames

    def _cache_loop(self, interval):
        while not self._cache_stop.is_set():
            started = time.monotonic()
            frames = {}
            try:
                frames = self._refresh_frame_cache()
                if self._stream_enabled.is_set():
                    self.publish_cached_frames()
                if (self._continuous_enabled.is_set()
                        and started - self._last_continuous_capture >= 0.5):
                    cached = self.get_cached_frames().get("kHeadColor")
                    if cached:
                        self._save_jpeg("kHeadColor", base64.b64decode(cached))
                    self._last_continuous_capture = started
            except Exception as error:
                print(f"[摄像头缓存] 更新失败: {error}")
            elapsed = time.monotonic() - started
            # 相机驱动尚未出帧时降低轮询频率，避免 GDK 错误刷屏；
            # 一旦有任一路出帧，立即恢复 3Hz 内存更新。
            target_interval = interval if frames else 2.0
            self._cache_stop.wait(max(0.0, target_interval - elapsed))

    def start_frame_cache(self, interval=1.0 / 3.0):
        """以 3Hz 更新内存图像；默认不向 MQTT 发布大图。"""
        if self._cache_thread and self._cache_thread.is_alive():
            return
        self._cache_stop.clear()
        self._cache_thread = threading.Thread(
            target=self._cache_loop, args=(interval,), daemon=True,
            name="camera-cache")
        self._cache_thread.start()
        print(f"[摄像头缓存] 更新线程已启动，频率={1.0 / interval:.1f}Hz")

    def stop_frame_cache(self):
        self._cache_stop.set()

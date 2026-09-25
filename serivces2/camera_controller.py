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

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class CameraController:
    """摄像头控制器"""
    
    def __init__(self, camera, mqtt_client, topic_response, image_save_dir):
        """构造函数
        
        Parameters
        ----------
        camera : agibot_gdk.Camera
            GDK Camera 对象
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        image_save_dir : str
            图片保存目录
        """
        self.camera = camera
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.image_save_dir = image_save_dir
        
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
    
    def _get_camera_type(self, agibot_gdk, camera_name):
        """获取相机类型枚举"""
        camera_map = {
            "kHeadColor": agibot_gdk.CameraType.kHeadColor,
            "kHeadDepth": agibot_gdk.CameraType.kHeadDepth,
            "kHandLeftColor": agibot_gdk.CameraType.kHandLeftColor,
            "kHandRightColor": agibot_gdk.CameraType.kHandRightColor,
        }
        return camera_map.get(camera_name)
    
    # ── 拍照（不嵌套，直接调用 GDK）────────────────────
    
    def capture(self, agibot_gdk, camera_name):
        """拍照并保存
        
        Parameters
        ----------
        agibot_gdk : module
            GDK 模块
        camera_name : str
            相机名称，如 "kHeadColor"
        
        Returns
        -------
        str
            保存的文件名，失败返回 None
        """
        camera_type = self._get_camera_type(agibot_gdk, camera_name)
        if camera_type is None:
            print(f"[摄像头] 未知相机: {camera_name}")
            return None
        
        try:
            image = self.camera.get_latest_image(camera_type, 1000.0)
            if image is None or image.data is None:
                print(f"[摄像头] {camera_name} 无数据")
                return None
            
            os.makedirs(self.image_save_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 检查是否为 JPEG
            if hasattr(image, "encoding") and image.encoding == agibot_gdk.Encoding.JPEG:
                filename = f"{camera_name}_{timestamp}.jpg"
                filepath = os.path.join(self.image_save_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(image.data)
                print(f"[摄像头] 拍照: {filename}")
                return filename
            
            # 使用 OpenCV 编码
            if HAS_CV2:
                raw = image.data
                if camera_name == "kHeadDepth":
                    depth = np.frombuffer(raw, dtype=np.uint16).reshape(
                        (image.height, image.width))
                    normalized = ((depth - depth.min()) / (depth.max() - depth.min() + 1) * 255).astype(np.uint8)
                    bgr = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
                else:
                    pixels = np.frombuffer(raw, dtype=np.uint8)
                    color_format = getattr(image, "color_format", None)
                    if color_format == agibot_gdk.ColorFormat.RGB:
                        bgr = cv2.cvtColor(
                            pixels.reshape((image.height, image.width, 3)),
                            cv2.COLOR_RGB2BGR)
                    else:
                        bgr = pixels.reshape((image.height, image.width, 3))
                
                filename = f"{camera_name}_{timestamp}.jpg"
                filepath = os.path.join(self.image_save_dir, filename)
                cv2.imwrite(filepath, bgr)
                print(f"[摄像头] 拍照: {filename}")
                return filename
            
            # 保存原始数据
            filename = f"{camera_name}_{timestamp}.raw"
            filepath = os.path.join(self.image_save_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image.data)
            print(f"[摄像头] 拍照: {filename}")
            return filename
        
        except Exception as e:
            print(f"[摄像头] 错误: {e}")
            return None
    
    def capture_all(self, agibot_gdk):
        """拍摄所有相机"""
        saved = []
        for camera_name in ["kHeadColor", "kHeadDepth", "kHandLeftColor", "kHandRightColor"]:
            filename = self.capture(agibot_gdk, camera_name)
            if filename:
                saved.append({"camera": camera_name, "file": filename})
        return saved
    
    def get_image_base64(self, agibot_gdk, camera_name):
        """获取图像的 base64 编码"""
        camera_type = self._get_camera_type(agibot_gdk, camera_name)
        if camera_type is None:
            return None
        
        try:
            image = self.camera.get_latest_image(camera_type, 1000.0)
            if image is None or image.data is None:
                return None
            
            if hasattr(image, "encoding") and image.encoding == agibot_gdk.Encoding.JPEG:
                return base64.b64encode(image.data).decode("ascii")
            
            if HAS_CV2:
                raw = image.data
                if camera_name == "kHeadDepth":
                    depth = np.frombuffer(raw, dtype=np.uint16).reshape(
                        (image.height, image.width))
                    normalized = ((depth - depth.min()) / (depth.max() - depth.min() + 1) * 255).astype(np.uint8)
                    bgr = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
                else:
                    pixels = np.frombuffer(raw, dtype=np.uint8)
                    color_format = getattr(image, "color_format", None)
                    if color_format == agibot_gdk.ColorFormat.RGB:
                        bgr = cv2.cvtColor(
                            pixels.reshape((image.height, image.width, 3)),
                            cv2.COLOR_RGB2BGR)
                    else:
                        bgr = pixels.reshape((image.height, image.width, 3))
                
                ok, buffer = cv2.imencode(".jpg", bgr,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
                if ok:
                    return base64.b64encode(buffer).decode("ascii")
            
            return base64.b64encode(image.data).decode("ascii")
        
        except Exception as e:
            print(f"[摄像头] 错误: {e}")
            return None

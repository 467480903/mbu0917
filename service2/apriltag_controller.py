#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apriltag_controller.py — Apriltag 图片解析控制器

职责：
  - 对摄像头控制器保存的图片做识别解析
"""

import os

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from dt_apriltags import Detector
    HAS_APRILTAG = True
except ImportError:
    HAS_APRILTAG = False


class ApriltagController:
    """Apriltag 控制器"""
    
    def __init__(self, mqtt_client, topic_response, image_save_dir):
        """构造函数
        
        Parameters
        ----------
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        image_save_dir : str
            图片保存目录
        """
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self.image_save_dir = image_save_dir
        self._detector = None
        
        # 相机参数（需要根据实际相机标定）
        self._camera_params = (500.0, 500.0, 320.0, 240.0)
        self._tag_size = 0.05
    
    def _publish_response(self, cmd, ts, success=False, extra=None):
        """发布反馈报文"""
        import json
        resp = {"cmd": cmd, "time": ts}
        if success:
            resp["success"] = True
        if extra:
            resp.update(extra)
        self.mqtt_client.publish(self.topic_response, json.dumps(resp, ensure_ascii=False))
    
    def init(self):
        """初始化 Apriltag 检测器"""
        if not HAS_APRILTAG:
            print("[Apriltag] 未安装 pupil-apriltags")
            return False
        
        try:
            self._detector = Detector(
                searchpath=['apriltags'],
                families='tag36h11',
                nthreads=4,
                quad_decimate=1.0,
                quad_sigma=0.0,
                refine_edges=1,
                decode_sharpening=0.25,
                debug=0
            )
            print("[Apriltag] 初始化完成")
            return True
        except Exception as e:
            print(f"[Apriltag] 初始化失败: {e}")
            return False
    
    # ── 检测（不嵌套，直接调用）────────────────────
    
    def detect_image(self, image):
        """检测图像中的 Apriltag
        
        Parameters
        ----------
        image : numpy.ndarray
            BGR 格式图像
        
        Returns
        -------
        list
            检测到的标签列表
        """
        if self._detector is None:
            if not self.init():
                return []
        
        if image is None:
            return []
        
        # 转灰度
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        try:
            results = self._detector.detect(
                gray,
                estimate_tag_pose=True,
                camera_params=self._camera_params,
                tag_size=self._tag_size
            )
        except Exception as e:
            print(f"[Apriltag] 检测失败: {e}")
            return []
        
        tags = []
        for r in results:
            tag_info = {
                "id": r.tag_id,
                "center": [float(r.center[0]), float(r.center[1])],
                "corners": [[float(c[0]), float(c[1])] for c in r.corners],
                "size": float(max(
                    np.linalg.norm(r.corners[0] - r.corners[1]),
                    np.linalg.norm(r.corners[1] - r.corners[2])
                ))
            }
            
            if r.pose_t is not None and r.pose_R is not None:
                tag_info["pose"] = {
                    "position": [float(x) for x in r.pose_t.flatten()],
                    "orientation": self._rotmat_to_quat(r.pose_R)
                }
            
            tags.append(tag_info)
        
        return tags
    
    @staticmethod
    def _rotmat_to_quat(R):
        """旋转矩阵转四元数"""
        trace = R[0, 0] + R[1, 1] + R[2, 2]
        if trace > 0:
            s = 0.5 / np.sqrt(trace + 1.0)
            w = 0.25 / s
            x = (R[2, 1] - R[1, 2]) * s
            y = (R[0, 2] - R[2, 0]) * s
            z = (R[1, 0] - R[0, 1]) * s
        else:
            if R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
                s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
                w = (R[2, 1] - R[1, 2]) / s
                x = 0.25 * s
                y = (R[0, 1] + R[1, 0]) / s
                z = (R[0, 2] + R[2, 0]) / s
            elif R[1, 1] > R[2, 2]:
                s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
                w = (R[0, 2] - R[2, 0]) / s
                x = (R[0, 1] + R[1, 0]) / s
                y = 0.25 * s
                z = (R[1, 2] + R[2, 1]) / s
            else:
                s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
                w = (R[1, 0] - R[0, 1]) / s
                x = (R[0, 2] + R[2, 0]) / s
                y = (R[1, 2] + R[2, 1]) / s
                z = 0.25 * s
        return [x, y, z, w]
    
    def detect_file(self, filepath):
        """检测图片文件"""
        if not HAS_CV2:
            print("[Apriltag] 未安装 OpenCV")
            return []
        
        if not os.path.exists(filepath):
            print(f"[Apriltag] 文件不存在: {filepath}")
            return []
        
        image = cv2.imread(filepath)
        return self.detect_image(image)
    
    def detect_saved_image(self, filename):
        """检测已保存的图片"""
        filepath = os.path.join(self.image_save_dir, filename)
        return self.detect_file(filepath)

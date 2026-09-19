#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G2 相机驱动、图像流发布与图片保存组件。

提供四路相机（头部彩色/深度、左右手腕彩色）的采集、编码、MQTT 图像流
发布和本地文件保存功能。本模块只负责相机驱动与文件保存，不承担视觉分析。

控制主题 ``/humanoid/camera/control`` 支持：
  - ``start`` / ``stop``：启停相机图像流发布；
  - ``save_photo``：保存指定相机图片；
  - ``start_continuous_capture`` / ``stop_continuous_capture``：启停头部彩色
    相机的连续保存。
"""

import base64
import os
import threading
import time

import agibot_gdk

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

import common


# ── 相机配置 ───────────────────────────────────────────────
# (输出字段名, GDK CameraType 枚举, 中文名)
CAMERA_LIST = [
    ("head_color", agibot_gdk.CameraType.kHeadColor, "头部彩色"),
    ("head_depth", agibot_gdk.CameraType.kHeadDepth, "头部深度"),
    ("left_wrist", agibot_gdk.CameraType.kHandLeftColor, "左手腕"),
    ("right_wrist", agibot_gdk.CameraType.kHandRightColor, "右手腕"),
]

# save_photo 命令使用的相机名称。
CAMERA_NAME_MAP = {
    "kHeadColor": agibot_gdk.CameraType.kHeadColor,
    "kHeadDepth": agibot_gdk.CameraType.kHeadDepth,
    "kHandLeftColor": agibot_gdk.CameraType.kHandLeftColor,
    "kHandRightColor": agibot_gdk.CameraType.kHandRightColor,
}

LOOP_INTERVAL = 0.8
JPEG_QUALITY = 60

_publishing = False
_publish_lock = threading.Lock()

_continuous_capturing = False
_continuous_lock = threading.Lock()
_continuous_interval = 0.8
_continuous_count = 0


def is_publishing():
    """返回当前是否发布相机流。"""
    with _publish_lock:
        return _publishing


def set_publishing(flag):
    """设置相机流发布开关。"""
    global _publishing
    with _publish_lock:
        _publishing = bool(flag)


def is_continuous_capturing():
    """返回当前是否连续保存头部彩色图片。"""
    with _continuous_lock:
        return _continuous_capturing


def set_continuous_capturing(flag):
    """设置连续拍照开关；停止时重置序号。"""
    global _continuous_capturing, _continuous_count
    with _continuous_lock:
        _continuous_capturing = bool(flag)
        if not flag:
            _continuous_count = 0


# ═══════════════════════════════════════════════════════════
#  图像编码与流发布
# ═══════════════════════════════════════════════════════════

def encode_image(image, key):
    """将 GDK Image 编码为 base64 字符串。

    JPEG/PNG 数据直接编码；未压缩彩色图重新编码为 JPEG；深度图转换为伪
    彩色 JPEG。若 OpenCV 不可用，未压缩数据以原始 bytes 编码。
    """
    if image is None or not hasattr(image, "data") or image.data is None:
        return None

    raw = image.data
    encoding = getattr(image, "encoding", None)
    if encoding in (agibot_gdk.Encoding.JPEG, agibot_gdk.Encoding.PNG):
        return base64.b64encode(bytes(raw)).decode("ascii")
    if not HAS_CV2:
        return base64.b64encode(bytes(raw)).decode("ascii")

    try:
        color_format = getattr(image, "color_format", None)
        if key == "head_depth":
            if len(raw) == image.width * image.height * 2:
                depth = np.frombuffer(raw, dtype=np.uint16).reshape((image.height, image.width))
            elif len(raw) == image.width * image.height:
                depth = np.frombuffer(raw, dtype=np.uint8).reshape((image.height, image.width))
            else:
                depth = np.frombuffer(raw, dtype=np.uint16)
                if depth.size != image.width * image.height:
                    return None
                depth = depth.reshape((image.height, image.width))

            valid = depth > 0
            if np.any(valid):
                minimum, maximum = depth[valid].min(), depth[valid].max()
                if maximum > minimum:
                    normalized = ((depth.astype(np.float32) - minimum) /
                                  (maximum - minimum) * 255).astype(np.uint8)
                else:
                    normalized = np.zeros_like(depth, dtype=np.uint8)
            else:
                normalized = np.zeros_like(depth, dtype=np.uint8)
            encoded_image = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
        else:
            pixels = np.frombuffer(raw, dtype=np.uint8)
            if color_format == agibot_gdk.ColorFormat.RGB:
                rgb = pixels.reshape((image.height, image.width, 3))
                encoded_image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            elif color_format == agibot_gdk.ColorFormat.GRAY8:
                gray = pixels.reshape((image.height, image.width))
                encoded_image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            else:
                encoded_image = pixels.reshape((image.height, image.width, 3))

        ok, buffer = cv2.imencode(
            ".jpg", encoded_image,
            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
        )
        if ok:
            return base64.b64encode(buffer).decode("ascii")
    except Exception as exc:
        print(f"[相机] 编码失败 {key}: {exc}")
    return None


def streaming_loop():
    """相机流发布与连续保存的后台循环。"""
    print("[相机] 发布线程已启动，等待 start 命令")
    last_capture_time = 0.0
    while True:
        try:
            started_at = time.time()
            if is_publishing():
                _capture_and_publish()
            if is_continuous_capturing():
                now = time.time()
                if now - last_capture_time >= _continuous_interval:
                    _save_continuous_head_color()
                    last_capture_time = now

            sleep_time = min(LOOP_INTERVAL, _continuous_interval)
            elapsed = time.time() - started_at
            if elapsed < sleep_time:
                time.sleep(sleep_time - elapsed)
        except Exception as exc:
            print(f"[相机] 循环异常: {exc}")
            time.sleep(1.0)


def _capture_and_publish():
    """采集四路相机图片并发布至 ``/humanoid/camera/data``。"""
    message = {"timestamp": int(time.time() * 1e9)}
    for key, camera_type, camera_name in CAMERA_LIST:
        try:
            image = common.camera.get_latest_image(camera_type, 1000.0)
            encoded = encode_image(image, key) if image is not None else None
        except Exception as exc:
            encoded = None
            print(f"  [{camera_name}] 读取异常: {exc}")
        if encoded:
            message[key] = encoded
        else:
            print(f"  [{camera_name}] 无数据")
    common.publish(common.TOPIC_CAMERA_DATA, message, qos=0)


# ═══════════════════════════════════════════════════════════
#  图片保存
# ═══════════════════════════════════════════════════════════

def save_camera_images(camera_names):
    """保存指定相机的当前图片到 ``images/``，返回已保存文件名列表。"""
    os.makedirs(common.IMAGE_SAVE_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    saved_files = []

    for name in camera_names:
        camera_type = CAMERA_NAME_MAP.get(name)
        if camera_type is None:
            print(f"  [保存] 未知相机名: {name}")
            continue
        try:
            image = common.camera.get_latest_image(camera_type, 1000.0)
        except Exception as exc:
            print(f"  [保存] {name} 读取异常: {exc}")
            continue
        if image is None or image.data is None:
            print(f"  [保存] {name} 无数据")
            continue

        filename = _save_single_image(image, name, timestamp)
        if filename:
            saved_files.append(filename)

    print(f"[保存] 完成，共 {len(saved_files)} 个文件 → {common.IMAGE_SAVE_DIR}")
    return saved_files


def _save_single_image(image, name, timestamp):
    """保存单张彩色图；深度图交由专用保存逻辑处理。"""
    if name == "kHeadDepth":
        return _save_depth_image(image, name, timestamp)

    if getattr(image, "encoding", None) == agibot_gdk.Encoding.JPEG:
        filename = f"{name}_{timestamp}.jpg"
        with open(os.path.join(common.IMAGE_SAVE_DIR, filename), "wb") as output:
            output.write(image.data)
        print(f"  [保存] {filename}")
        return filename

    if HAS_CV2:
        try:
            pixels = np.frombuffer(image.data, dtype=np.uint8)
            if getattr(image, "color_format", None) == agibot_gdk.ColorFormat.RGB:
                bgr = cv2.cvtColor(
                    pixels.reshape((image.height, image.width, 3)), cv2.COLOR_RGB2BGR
                )
            else:
                bgr = pixels.reshape((image.height, image.width, 3))
            filename = f"{name}_{timestamp}.jpg"
            cv2.imwrite(os.path.join(common.IMAGE_SAVE_DIR, filename), bgr)
            print(f"  [保存] {filename}")
            return filename
        except Exception as exc:
            print(f"  [保存] {name} 编码失败: {exc}")

    filename = f"{name}_{timestamp}.raw"
    with open(os.path.join(common.IMAGE_SAVE_DIR, filename), "wb") as output:
        output.write(image.data)
    print(f"  [保存] {filename}")
    return filename


def _save_depth_image(image, name, timestamp):
    """保存深度原始数据；可用 OpenCV 时另外保存伪彩图。"""
    raw_filename = f"{name}_raw_{timestamp}.raw"
    with open(os.path.join(common.IMAGE_SAVE_DIR, raw_filename), "wb") as output:
        output.write(image.data)
    print(f"  [保存] {raw_filename}")

    if not HAS_CV2:
        return raw_filename

    try:
        depth = np.frombuffer(image.data, dtype=np.uint16).reshape((image.height, image.width))
        valid = depth > 0
        minimum, maximum = (depth[valid].min(), depth[valid].max()) if np.any(valid) else (0, 1)
        if maximum > minimum:
            normalized = ((depth - minimum) / (maximum - minimum) * 255).astype(np.uint8)
        else:
            normalized = np.zeros_like(depth, dtype=np.uint8)
        colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
        cv2.putText(colored, f"Depth: {minimum}-{maximum}mm", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        filename = f"{name}_{timestamp}.jpg"
        cv2.imwrite(os.path.join(common.IMAGE_SAVE_DIR, filename), colored)
        print(f"  [保存] {filename}")
        return filename
    except Exception as exc:
        print(f"  [保存] 深度伪彩色失败: {exc}")
        return raw_filename


def _save_continuous_head_color():
    """连续保存一张头部彩色图，文件名附带递增序号。"""
    global _continuous_count
    try:
        os.makedirs(common.IMAGE_SAVE_DIR, exist_ok=True)
        image = common.camera.get_latest_image(
            agibot_gdk.CameraType.kHeadColor, 1000.0
        )
        if image is None or image.data is None:
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        _continuous_count += 1
        sequence = f"{_continuous_count:04d}"
        if getattr(image, "encoding", None) == agibot_gdk.Encoding.JPEG:
            filename = f"cap_{timestamp}_{sequence}.jpg"
            with open(os.path.join(common.IMAGE_SAVE_DIR, filename), "wb") as output:
                output.write(image.data)
        elif HAS_CV2:
            pixels = np.frombuffer(image.data, dtype=np.uint8)
            if getattr(image, "color_format", None) == agibot_gdk.ColorFormat.RGB:
                bgr = cv2.cvtColor(
                    pixels.reshape((image.height, image.width, 3)), cv2.COLOR_RGB2BGR
                )
            else:
                bgr = pixels.reshape((image.height, image.width, 3))
            filename = f"cap_{timestamp}_{sequence}.jpg"
            cv2.imwrite(os.path.join(common.IMAGE_SAVE_DIR, filename), bgr)
        else:
            filename = f"cap_{timestamp}_{sequence}.raw"
            with open(os.path.join(common.IMAGE_SAVE_DIR, filename), "wb") as output:
                output.write(image.data)
        print(f"  [连拍] 第{_continuous_count}张: {filename}")
    except Exception as exc:
        print(f"  [连拍] 保存失败: {exc}")


# ═══════════════════════════════════════════════════════════
#  命令处理
# ═══════════════════════════════════════════════════════════

def handle_control(payload):
    """处理相机流和图片保存控制命令。"""
    command = payload.get("command", "").lower()
    if command == "start":
        set_publishing(True)
        print("[相机] 开始发布")
    elif command == "stop":
        set_publishing(False)
        print("[相机] 停止发布")
    elif command == "start_continuous_capture":
        set_continuous_capturing(True)
        print("[相机] 开始持续拍照（头部彩色，间隔0.8秒）")
    elif command == "stop_continuous_capture":
        set_continuous_capturing(False)
        print("[相机] 停止持续拍照")
    elif command == "save_photo":
        cameras = payload.get("cameras", [])
        if not cameras:
            print("[相机] save_photo 缺少 cameras 字段")
            return
        print(f"[相机] 保存图片: {cameras}")
        threading.Thread(target=_run_save, args=(cameras,), daemon=True).start()
    else:
        print(f"[相机] 未知命令: {command}")


def _run_save(cameras):
    """异步保存图片，并向命令完成主题发送通知。"""
    try:
        save_camera_images(cameras)
    except Exception as exc:
        print(f"[相机] 保存异常: {exc}")
    finally:
        common.publish_done("save_photo")


def start_streaming_thread():
    """启动相机流发布后台线程。"""
    threading.Thread(target=streaming_loop, daemon=True).start()
    print("[相机] 发布线程已启动")

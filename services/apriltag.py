#!/data/wxf/mbu0917/.venv-apriltag/bin/python
# -*- coding: utf-8 -*-
"""独立 AprilTag 双标签线距检测 MQTT 服务。

使用工程根目录的 ``.venv-apriltag`` 运行，不导入 GDK 或 camera.py。

订阅 ``/humanoid/apriltag``，处理：
    {
      "cmd": "detect2tagsForLineDistance",
      "imgPath": "/data/wxf/mbu0917/images/",
      "resultSavePath": "/data/wxf/mbu0917/detect"
    }

服务固定从 ``imgPath`` 读取 ``kHeadColor_latest.jpg`` 和
``kHeadDepth_raw_latest.raw``。深度 RAW 按与 RGB 对齐的 uint16 毫米图处理，
在两个标签中心周围各取 3×3 有效像素的平均深度。
"""

import json
import math
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
from pupil_apriltags import Detector


MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
REQUEST_TOPIC = "/humanoid/apriltag"
DONE_TOPIC = "/humanoid/apriltag/done"
COMMAND = "detect2tagsForLineDistance"
DEFAULT_FAMILY = "tag36h11"
COLOR_FILENAME = "kHeadColor_latest.jpg"
DEPTH_FILENAME = "kHeadDepth_raw_latest.raw"

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="apriltag")
_detector_lock = threading.Lock()
_detectors = {}


def _timestamp():
    now = datetime.now()
    return now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"


def _json_value(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _get_detector(family):
    with _detector_lock:
        detector = _detectors.get(family)
        if detector is None:
            detector = Detector(
                families=family,
                nthreads=1,
                quad_decimate=1.0,
                quad_sigma=0.0,
                refine_edges=1,
                decode_sharpening=0.25,
                debug=0,
            )
            _detectors[family] = detector
        return detector


def _atomic_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.stem}_", suffix=".tmp", delete=False,
    ) as output:
        json.dump(value, output, ensure_ascii=False, indent=2, default=_json_value)
        output.write("\n")
        temporary_path = output.name
    os.replace(temporary_path, path)


def _atomic_image(path, image):
    path = Path(path)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.stem}_", suffix=".jpg"
    )
    os.close(descriptor)
    try:
        if not cv2.imwrite(temporary_path, image):
            raise RuntimeError(f"unable to write image: {path}")
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _load_depth_raw(path, width, height):
    """读取与 RGB 同尺寸、little-endian uint16（毫米）的深度 RAW。"""
    raw = np.fromfile(path, dtype="<u2")
    expected_count = width * height
    if raw.size != expected_count:
        raise ValueError(
            f"depth raw size mismatch: got {raw.size} pixels, expected {expected_count}"
        )
    return raw.reshape((height, width))


def _mean_depth_3x3(depth_image, center_px):
    """返回标签中心周围 3×3 范围内有效（>0）深度的均值，单位毫米。"""
    x = int(round(float(center_px[0])))
    y = int(round(float(center_px[1])))
    x_start, x_end = max(0, x - 1), min(depth_image.shape[1], x + 2)
    y_start, y_end = max(0, y - 1), min(depth_image.shape[0], y + 2)
    samples = depth_image[y_start:y_end, x_start:x_end]
    valid_samples = samples[samples > 0]
    if valid_samples.size == 0:
        return None, 0
    return float(valid_samples.mean()), int(valid_samples.size)


def _tag_record(detection, depth_image):
    center = np.asarray(detection.center, dtype=float)
    depth_mm, valid_samples = _mean_depth_3x3(depth_image, center)
    family = detection.tag_family.decode("ascii") if isinstance(detection.tag_family, bytes) else str(detection.tag_family)
    return {
        "id": int(detection.tag_id),
        "family": family,
        "hamming": int(detection.hamming),
        "decision_margin": float(detection.decision_margin),
        "center_px": center,
        "corners_px": np.asarray(detection.corners, dtype=float),
        "depth_3x3_mean_mm": depth_mm,
        "depth_valid_samples": valid_samples,
    }


def _centerline(first, second, image_width):
    """计算双标签中心连线、其中点与两条垂线的水平偏距。"""
    dx = float(second["center_px"][0] - first["center_px"][0])
    dy = float(second["center_px"][1] - first["center_px"][1])
    midpoint_x = (float(first["center_px"][0]) + float(second["center_px"][0])) / 2.0
    midpoint_y = (float(first["center_px"][1]) + float(second["center_px"][1])) / 2.0
    image_center_x = image_width / 2.0
    vertical = abs(dx) < 1e-9
    return {
        "ordered_by": "center_x_ascending",
        "dx_px": dx,
        "dy_px": dy,
        "slope_dy_dx": None if vertical else dy / dx,
        "angle_rad": math.atan2(dy, dx),
        "is_vertical": vertical,
        "center_distance_px": math.hypot(dx, dy),
        "midpoint_px": [midpoint_x, midpoint_y],
        "midpoint_vertical_x_px": midpoint_x,
        "image_center_vertical_x_px": image_center_x,
        "vertical_line_horizontal_distance_px": abs(midpoint_x - image_center_x),
        "midpoint_offset_from_image_center_px": midpoint_x - image_center_x,
    }


def _draw_detection(image, tags, centerline, mean_depth_mm):
    """绘制标签、中心连线、白色中点垂线和黑色图像中心垂线。"""
    canvas = image.copy()
    height, width = canvas.shape[:2]

    # 黑线：图像几何中心的垂线和水平线。
    cv2.line(canvas, (width // 2, 0), (width // 2, height - 1),
             (0, 0, 0), 1, cv2.LINE_AA)
    cv2.line(canvas, (0, height // 2), (width - 1, height // 2),
             (0, 0, 0), 1, cv2.LINE_AA)

    for tag in tags:
        corners = np.asarray(tag["corners_px"], dtype=np.int32).reshape((-1, 1, 2))
        center = tuple(np.rint(tag["center_px"]).astype(int))
        cv2.polylines(canvas, [corners], True, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.circle(canvas, center, 5, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.putText(canvas, f"ID {tag['id']}", (center[0] + 8, center[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA)

    if centerline is not None:
        first = tuple(np.rint(tags[0]["center_px"]).astype(int))
        second = tuple(np.rint(tags[1]["center_px"]).astype(int))
        midpoint_x = int(round(centerline["midpoint_vertical_x_px"]))
        # 蓝线：两个标签中心的连线；白线：其垂直中点线。
        cv2.line(canvas, first, second, (255, 0, 0), 1, cv2.LINE_AA)
        cv2.line(canvas, (midpoint_x, 0), (midpoint_x, height - 1),
                 (255, 255, 255), 1, cv2.LINE_AA)
        cv2.circle(canvas, tuple(np.rint(centerline["midpoint_px"]).astype(int)),
                   5, (255, 255, 255), -1, cv2.LINE_AA)

    angle_text = "Angle(rad): N/A"
    distance_text = "Line offset: N/A"
    if centerline is not None:
        angle_text = f"Angle(rad): {centerline['angle_rad']:.6f}"
        distance_text = f"Line offset: {centerline['vertical_line_horizontal_distance_px']:.2f} px"
    depth_text = "Depth avg: N/A"
    if mean_depth_mm is not None:
        depth_text = f"Depth avg: {mean_depth_mm:.1f} mm"

    cv2.putText(canvas, angle_text, (16, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(canvas, depth_text, (16, 58), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 0, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, distance_text, (16, 86), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 0, 0), 2, cv2.LINE_AA)
    return canvas


def _result_paths(result_dir, timestamp):
    base_name = f"{COMMAND}_{timestamp}"
    return {
        "result_json": result_dir / f"{base_name}.json",
        "result_jpg": result_dir / f"{base_name}.jpg",
        "latest_json": result_dir / f"{COMMAND}_latest.json",
        "latest_jpg": result_dir / f"{COMMAND}_latest.jpg",
    }


def _write_result(paths, result, annotated):
    _atomic_json(paths["result_json"], result)
    if annotated is not None:
        _atomic_image(paths["result_jpg"], annotated)
    _atomic_json(paths["latest_json"], result)
    if annotated is not None:
        _atomic_image(paths["latest_jpg"], annotated)


def process_detection(request):
    """执行一次双 AprilTag 检测并生成 JSON/JPG 结果。"""
    timestamp = _timestamp()
    image_dir_text = str(request.get("imgPath", "")).strip()
    result_dir_text = str(request.get("resultSavePath", "")).strip()
    family = str(request.get("family", DEFAULT_FAMILY))

    if not image_dir_text or not result_dir_text:
        return {
            "cmd": COMMAND,
            "time": timestamp,
            "success": False,
            "error": "imgPath and resultSavePath are required",
        }

    image_dir = Path(image_dir_text).expanduser()
    result_dir = Path(result_dir_text).expanduser()
    result_dir.mkdir(parents=True, exist_ok=True)
    paths = _result_paths(result_dir, timestamp)
    color_path = image_dir / COLOR_FILENAME
    depth_path = image_dir / DEPTH_FILENAME
    result = {
        "cmd": COMMAND,
        "time": timestamp,
        "success": False,
        "imgPath": str(image_dir),
        "resultSavePath": str(result_dir),
        "color_image": str(color_path),
        "depth_raw": str(depth_path),
        "family": family,
        "tags": [],
        "centerline": None,
        "mean_tag_depth_mm": None,
        "depth_unit": "mm",
        **{name: str(path) for name, path in paths.items()},
    }

    image = cv2.imread(str(color_path), cv2.IMREAD_COLOR)
    if image is None:
        result["error"] = f"unable to read color image: {color_path}"
        _write_result(paths, result, None)
        return result

    try:
        height, width = image.shape[:2]
        depth_image = _load_depth_raw(depth_path, width, height)
        detector = _get_detector(family)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        detections = detector.detect(gray)
        tags = [_tag_record(detection, depth_image) for detection in detections]
        tags.sort(key=lambda tag: tag["center_px"][0])
        result["detected_count"] = len(tags)
        result["tags"] = tags

        if len(tags) != 2:
            result["error"] = "expected exactly two AprilTags"
            annotated = _draw_detection(image, tags, None, None)
        else:
            centerline = _centerline(tags[0], tags[1], width)
            depths = [tag["depth_3x3_mean_mm"] for tag in tags]
            valid_depths = [depth for depth in depths if depth is not None]
            result["centerline"] = centerline
            result["mean_tag_depth_mm"] = (
                sum(valid_depths) / len(valid_depths) if valid_depths else None
            )
            result["depth_status"] = (
                "ok" if len(valid_depths) == 2 else "partial_or_missing_depth"
            )
            result["success"] = len(valid_depths) == 2
            if not result["success"]:
                result["error"] = "one or both tag center 3x3 depth regions contain no valid depth"
            annotated = _draw_detection(
                image, tags, centerline, result["mean_tag_depth_mm"]
            )
    except Exception as exc:
        result["error"] = str(exc)
        annotated = _draw_detection(image, result["tags"], result["centerline"], None)

    _write_result(paths, result, annotated)
    return result


def _publish_done(client, timestamp):
    payload = {"cmd": "done", "time": timestamp}
    client.publish(DONE_TOPIC, json.dumps(payload, ensure_ascii=False), qos=0)


def _handle_request(client, request):
    try:
        result = process_detection(request)
        print(f"[AprilTag] success={result['success']} result={result.get('result_json')}")
        timestamp = result["time"]
    except Exception as exc:
        timestamp = _timestamp()
        print(f"[AprilTag] 未处理异常: {exc}")
    finally:
        _publish_done(client, timestamp)


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe(REQUEST_TOPIC, qos=0)
        print(f"[AprilTag] 已订阅 {REQUEST_TOPIC}")
    else:
        print(f"[AprilTag] MQTT 连接失败，返回码: {reason_code}")


def on_message(client, userdata, message):
    try:
        request = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"[AprilTag] 非法 JSON: {exc}")
        return
    if request.get("cmd") != COMMAND:
        print(f"[AprilTag] 忽略未知命令: {request.get('cmd')}")
        return
    _executor.submit(_handle_request, client, request)


def main():
    client = mqtt.Client(
        client_id=f"humanoid_apriltag_{os.getpid()}",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    print(f"[AprilTag] 服务启动：{MQTT_BROKER}:{MQTT_PORT}")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("[AprilTag] 服务停止")
    finally:
        _executor.shutdown(wait=False, cancel_futures=True)
        client.disconnect()


if __name__ == "__main__":
    main()

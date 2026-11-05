"""Apriltag 视觉闭环测试辅助代码，不导入 GDK，不启动任何后台服务。"""
import argparse
import json
import math
from pathlib import Path
import statistics
import threading
import time
import uuid
import xml.etree.ElementTree as ET


WAIST = "idx05_body_joint5"
DONE = "/humanoid/done/"
STATUS = "/humanoid/status/data"
EMERGENCY = "/humanoid/emergency/control"


def line_geometry(tags, ids=None):
    """图像 Y 向下；按 X 从左到右排列，负斜率表示右边标签更高。"""
    if ids is None:
        if len(tags) != 2:
            raise ValueError(f"需要恰好两个标签，实际 {len(tags)}；可用 --ids 指定")
        ids = tuple(sorted(int(tag["id"]) for tag in tags))
    selected = [tag for tag in tags if int(tag["id"]) in ids]
    if len(selected) != 2 or len({int(t["id"]) for t in selected}) != 2:
        raise ValueError(f"标签 {ids} 丢失或 ID 重复，停止测试")
    centers = sorted([list(map(float, t["center"])) for t in selected])
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in centers):
        raise ValueError("标签中心坐标无效")
    dx, dy = (centers[1][i] - centers[0][i] for i in (0, 1))
    if dx < 50:
        raise ValueError("两标签水平间距小于 50 像素，不适合斜率闭环")
    return {"ids": list(ids), "centers": centers, "dx": dx, "dy": dy,
            "slope": dy / dx, "angle_deg": math.degrees(math.atan2(dy, dx))}


def correction(angle, change, actual_turn, minimum, maximum):
    """依据实测响应估计局部梯度；不把图像斜率符号直接当成转向。"""
    if abs(change) < 0.08 or abs(actual_turn) < 0.05:
        return None
    proposal = -angle / (change / actual_turn)
    return math.copysign(min(maximum, max(minimum, abs(proposal))), proposal)


class AlignmentTest:
    def __init__(self, args):
        import paho.mqtt.client as mqtt
        self.args = args
        self.ids = tuple(args.ids) if args.ids else None
        self.condition = threading.Condition()
        self.ready = threading.Event()
        self.failure = None
        self.pending = None
        self.answer = None
        self.status = {}
        self.moving = False
        self.records = []
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="tag_alignment_" + uuid.uuid4().hex[:12])
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def record(self, event, **values):
        row = {"event": event, "timestamp": time.time(), **values}
        self.records.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def _on_connect(self, client, _userdata, _flags, reason, _properties):
        if reason.is_failure:
            self.failure = f"MQTT 连接失败: {reason}"
            self.ready.set()
            return
        topics = [(f"/humanoid/{name}/response/", 0)
                  for name in ("camera", "apriltag", "base", "joint")]
        client.subscribe(topics + [(DONE, 0), (STATUS, 0)])

    def _on_subscribe(self, _client, _userdata, _mid, reasons, _properties):
        if any(reason.is_failure for reason in reasons):
            self.failure = "MQTT 订阅被拒绝"
        self.ready.set()

    def _on_disconnect(self, _client, _userdata, _flags, reason, _properties):
        with self.condition:
            self.failure = f"MQTT 已断开: {reason}"
            self.condition.notify_all()

    def _on_message(self, _client, _userdata, message):
        if message.retain:
            return  # 不使用历史 done 或历史状态。
        try:
            payload = json.loads(message.payload.decode())
            if not isinstance(payload, dict):
                return
            with self.condition:
                if message.topic == STATUS:
                    for key in ("chassis", "joints"):
                        if isinstance(payload.get(key), dict):
                            self.status[key] = (time.monotonic(), payload[key])
                elif self.pending:
                    token, group, command, motion = self.pending
                    response_topic = f"/humanoid/{group}/response/"
                    valid = message.topic in (response_topic, DONE)
                    valid &= payload.get("time") == token and payload.get("cmd") == command
                    if message.topic == DONE:
                        valid &= payload.get("type") == group
                    if valid and (payload.get("success") is False or
                                  message.topic == (DONE if motion else response_topic)):
                        self.answer = payload
                self.condition.notify_all()
        except (ValueError, TypeError):
            return

    def connect(self):
        self.client.connect(self.args.broker, self.args.port, 30)
        self.client.loop_start()
        if not self.ready.wait(10) or self.failure:
            raise RuntimeError(self.failure or "MQTT 订阅超时")

    def request(self, group, command, motion=False, **values):
        token = uuid.uuid4().hex
        payload = {"cmd": command, "time": token, **values}
        deadline = time.monotonic() + (70 if motion else 20)
        with self.condition:
            if self.failure:
                raise RuntimeError(self.failure)
            self.pending = (token, group, command, motion)
            self.answer = None
            if motion:
                self.moving = True
            # 不重试运动请求；现有服务不提供运动命令去重。
            info = self.client.publish(f"/humanoid/{group}/request/",
                                       json.dumps(payload), qos=0, retain=False)
            if info.rc != 0:
                raise RuntimeError(f"MQTT 下发失败: {info.rc}")
            while self.answer is None:
                remaining = deadline - time.monotonic()
                if self.failure or remaining <= 0:
                    raise RuntimeError(self.failure or f"{group}/{command} 等待超时")
                self.condition.wait(min(remaining, 0.2))
            answer = self.answer
            self.pending = None
        if answer.get("success") is not True:
            raise RuntimeError(f"服务失败: {answer}")
        if motion:
            self.moving = False
            self.record("done", response=answer)
        return answer

    def yaw(self, stage, after=0):
        key = "chassis" if stage == "base" else "joints"
        deadline = time.monotonic() + 5
        with self.condition:
            while True:
                received, data = self.status.get(key, (0, {}))
                if received > after and time.monotonic() - received < 1:
                    value = float(data["yaw" if stage == "base" else WAIST])
                    if not math.isfinite(value):
                        raise ValueError("旋转角状态无效")
                    return math.degrees(value)
                if self.failure or time.monotonic() >= deadline:
                    raise RuntimeError(self.failure or f"{stage} 无新鲜角度状态")
                self.condition.wait(0.2)

    def observe(self):
        frames = []
        for _ in range(3):
            photo = self.request("camera", "capture", camera="kHeadColor")
            filename = photo["result"]
            if not isinstance(filename, str) or not filename:
                raise ValueError("相机未返回照片文件名")
            result = self.request("apriltag", "detect_saved", file=filename)
            geometry = line_geometry(result["result"], self.ids)
            self.ids = tuple(geometry["ids"])
            self.record("frame", file=filename, **geometry)
            frames.append(geometry)
            time.sleep(0.2)
        angles = [frame["angle_deg"] for frame in frames]
        if max(angles) - min(angles) > 0.3:
            raise RuntimeError("连续三张照片倾角波动超过 0.3°，请固定标签/头部并重试")
        angle = statistics.median(angles)
        self.record("measurement", angle_deg=angle,
                    slope=math.tan(math.radians(angle)))
        return angle

    def move(self, stage, turn):
        before = self.yaw(stage)
        if stage == "base":
            self.request("base", "relative2", motion=True, x=0, y=0,
                         rotate=turn, vel_line=0.02, vel_rotate=2.0)
        else:
            target = math.radians(before + turn)
            # 直接从当前项目 URDF 读取腰部偏航轴硬限位，再留 5° 裕量。
            model = Path(__file__).resolve().parents[2] / "web/meshes/model.urdf"
            joint = ET.parse(model).getroot().find(f"joint[@name='{WAIST}']")
            limit = joint.find("limit")
            margin = math.radians(5)
            if not float(limit.get("lower")) + margin < target < float(limit.get("upper")) - margin:
                raise ValueError("腰部目标接近/超过 URDF 限位，拒绝执行")
            self.request("joint", "single_joint", motion=True,
                         name=WAIST, value=target, speed=0.03)
        finished = time.monotonic()
        time.sleep(1.0)  # done 后等待画面稳定，再读取新的状态/照片。
        after = self.yaw(stage, after=finished)
        actual = (after - before + 180) % 360 - 180
        self.record("turn", stage=stage, requested_deg=turn, actual_deg=actual)
        # relative2 的现有到位容差是 0.02 rad；不能把 done 当精确到位。
        tolerance = 1.3 if stage == "base" else 0.2
        if actual * turn <= 0 or abs(actual) < 0.05 or abs(actual - turn) > tolerance:
            raise RuntimeError("实际转角未按要求完成，停止测试")
        return actual

    def stage(self, stage, angle):
        maximum = 2.0 if stage == "base" else 0.5
        minimum = 1.5 if stage == "base" else 0.1
        turn = maximum * self.args.probe_sign
        total = 0.0
        for index in range(1, 5):
            if abs(angle) <= self.args.tolerance:
                break
            if abs(angle) > 15:
                raise RuntimeError("倾角超过 15°；不适合用本小角度偏航测试纠正")
            print(f"{stage} 第 {index}/4 次，拟旋转 {turn:+.2f}°；"
                  "请确认机器人周围安全且无其他控制程序运行。")
            input("按回车执行本次运动，Ctrl+C 取消：")
            total += abs(turn)
            if abs(turn) > maximum or total > maximum * 4 + 1e-6:
                raise RuntimeError("超过阶段角度预算")
            actual = self.move(stage, turn)
            updated = self.observe()
            change = updated - angle
            next_turn = correction(updated, change, actual, minimum, maximum)
            self.record("iteration", stage=stage, iteration=index, before_deg=angle,
                        after_deg=updated, accumulated_command_deg=total)
            # 首步为探测，允许一次反向修正；之后变差则停止该阶段。
            worse = abs(updated) > abs(angle) + 0.08
            angle = updated
            if abs(angle) <= self.args.tolerance:
                break
            if next_turn is None or (index > 1 and worse):
                self.record("stage_stopped", stage=stage,
                            reason="视觉响应太小或调整继续变差，不盲目增加转角")
                break
            turn = next_turn
        return angle

    def close(self):
        if self.moving:
            # 仅未确认运动结束时异常退出才发软件急停；绝不自动解除急停。
            info = self.client.publish(EMERGENCY, json.dumps({"action": "press"}), qos=0)
            try:
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                pass
            print("已尝试软件急停；网络可能失效，请现场确认并使用实体急停！")
        self.client.disconnect()
        self.client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description="两 Apriltag 中心连线调平；默认只拍照")
    parser.add_argument("--move", action="store_true", help="开启人工确认后的底盘/腰部调整")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--ids", type=int, nargs=2, help="固定两个标签 ID；默认首帧自动选择")
    parser.add_argument("--tolerance", type=float, default=0.3, help="水平误差容许角度，默认 0.3°")
    parser.add_argument("--probe-sign", type=int, choices=(-1, 1), default=1)
    parser.add_argument("--log", type=Path, help="可选：将测量和运动结果保存为新 JSONL 文件")
    args = parser.parse_args()
    if not math.isfinite(args.tolerance) or not 0.1 <= args.tolerance <= 2:
        parser.error("--tolerance 必须在 0.1 至 2 度之间")
    if args.ids and args.ids[0] == args.ids[1]:
        parser.error("两个标签 ID 不能相同")
    logfile = args.log.open("x", encoding="utf-8") if args.log else None
    test = AlignmentTest(args)
    try:
        test.connect()
        initial = angle = test.observe()
        if args.move:
            angle = test.stage("base", angle)
            angle = test.stage("waist", angle)
        test.record("summary", initial_deg=initial, final_deg=angle,
                    reached=abs(angle) <= args.tolerance, motion_enabled=args.move)
        return 0 if not args.move or abs(angle) <= args.tolerance else 2
    except (Exception, KeyboardInterrupt) as error:
        test.record("aborted", reason=str(error) or "用户取消")
        return 1
    finally:
        try:
            test.close()
        finally:
            if logfile:
                for row in test.records:
                    logfile.write(json.dumps(row, ensure_ascii=False) + "\n")
                logfile.close()

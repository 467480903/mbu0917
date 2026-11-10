#!/usr/bin/env python3
"""独立 LLM MQTT 服务；使用 .venv-llm，不导入 GDK。"""
import json
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import paho.mqtt.client as mqtt
from llm_controller import LlmController


class LlmApplication:
    request_topic = "/humanoid/vision/llm/request"
    response_topic = "/humanoid/vision/llm/result"

    def __init__(self):
        self.controller = LlmController()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.slot = threading.BoundedSemaphore(1)
        self.seen = set()
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="g2_llm_service")
        self.client.on_connect = self._connect
        self.client.on_message = self._message

    def _connect(self, client, _userdata, _flags, reason, _properties):
        if not reason.is_failure:
            client.subscribe(self.request_topic, qos=1)
            print(f"[LLM] 已订阅 {self.request_topic}", flush=True)

    def _reply(self, request, **result):
        self.client.publish(self.response_topic, json.dumps({
            "time": request.get("time"), "camera": request.get("camera"),
            "cmd": request.get("cmd"), **result}, ensure_ascii=False), qos=1)

    def _message(self, _client, _userdata, message):
        if message.retain or len(message.payload) > 8192:
            return
        try:
            request = json.loads(message.payload)
            if not isinstance(request, dict):
                return
            token = request.get("time")
            if not isinstance(token, str) or not 1 <= len(token) <= 128:
                raise ValueError("time 必须是唯一请求编号")
            if token in self.seen:
                return
            if request.get("cmd") != "detect_file":
                raise ValueError("只支持 detect_file")
            if not self.slot.acquire(blocking=False):
                self._reply(request, success=False, error="LLM 正在识别，请稍后重试")
                return
            if len(self.seen) > 1000:
                self.seen.clear()
            self.seen.add(token)
            self.pool.submit(self._detect, request)
        except (ValueError, TypeError) as error:
            if isinstance(locals().get("request"), dict):
                self._reply(request, success=False, error=str(error))

    def _detect(self, request):
        try:
            result = self.controller.detect_file(request["file"], request.get("prompt_id"))
            self._reply(request, success=True, result=result)
            print(f"[LLM] 完成 {request['time']}: found={result['found']}", flush=True)
        except Exception as error:
            # 不输出 HTTP 请求体、Authorization 或模型推理过程。
            self._reply(request, success=False, error=str(error))
            print(f"[LLM] 请求失败: {type(error).__name__}: {error}", flush=True)
        finally:
            self.slot.release()

    def run(self):
        config = json.loads((Path(__file__).parent / "config.json").read_text())
        self.client.connect(config["mqtt"]["broker"], int(config["mqtt"]["port"]), 30)
        try:
            self.client.loop_forever()
        finally:
            self.client.disconnect()
            self.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    LlmApplication().run()

#!/usr/bin/env python3
"""runtime2 用户程序管理与单步调试 MQTT 服务。"""

import argparse
import json
import os
import runpy
import sys
import tempfile
import threading
import traceback
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:  # 文件管理与模拟测试不需要 MQTT
    mqtt = None


CONTROL_TOPIC = "/humanoid/programs/control"
STEP_TOPIC = "/humanoid/programs/step"
CODES_TOPIC = "/humanoid/programs/codes"
FILES_TOPIC = "/humanoid/programs/files"
STATUS_TOPIC = "/humanoid/programs/status"


class StopExecution(Exception):
    """用于从 trace 回调中停止用户程序。"""


class RuntimeProgramManager:
    """管理 runtime2 程序文件、普通执行和 trace 单步执行。"""

    def __init__(self, runtime_dir=None, publisher=None):
        self.runtime_dir = Path(runtime_dir or Path(__file__).resolve().parent).resolve()
        self.programs_dir = self.runtime_dir / "programs"
        self.main_file = self.runtime_dir / "main.py"
        self.publisher = publisher or (lambda topic, payload: None)
        self.programs_dir.mkdir(parents=True, exist_ok=True)
        self._state_lock = threading.Lock()
        self._step_event = threading.Event()
        self._stop_event = threading.Event()
        self._running = False
        self._debugging = False
        self._worker = None
        self._source_lines = []

    @property
    def running(self):
        with self._state_lock:
            return self._running

    @property
    def debugging(self):
        with self._state_lock:
            return self._debugging

    def list_programs(self):
        return sorted(
            path.name for path in self.programs_dir.iterdir()
            if path.is_file() and path.suffix == ".py" and path.name != "__init__.py"
        )

    def publish_programs(self):
        files = self.list_programs()
        self.publisher(FILES_TOPIC, {"command": "read_files", "success": True, "files": files})
        return files

    def _program_path(self, filename):
        """校验程序文件名，禁止绝对路径和目录穿越。"""
        if not isinstance(filename, str) or not filename.endswith(".py"):
            raise ValueError("程序必须是 .py 文件")
        if Path(filename).name != filename or filename == "__init__.py":
            raise ValueError("程序文件名不合法")
        path = (self.programs_dir / filename).resolve()
        if path.parent != self.programs_dir or not path.is_file():
            raise FileNotFoundError(f"程序不存在: {filename}")
        return path

    def copy_program(self, filename):
        """将选中程序原样复制为 runtime2/main.py。"""
        if self.running:
            raise RuntimeError("程序运行中，不能替换 main.py")
        source = self._program_path(filename)
        content = source.read_text(encoding="utf-8")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.runtime_dir,
            prefix=".main-", suffix=".py", delete=False,
        ) as stream:
            stream.write(content)
            temporary_name = stream.name
        os.replace(temporary_name, self.main_file)
        self.publisher(STATUS_TOPIC, {
            "command": "copy", "state": "copied", "success": True,
            "filename": filename,
        })
        return self.main_file

    def read_main(self):
        if not self.main_file.is_file():
            raise FileNotFoundError("runtime2/main.py 不存在，请先选择程序")
        return self.main_file.read_text(encoding="utf-8")

    def publish_main(self):
        code = self.read_main()
        self.publisher(CODES_TOPIC, {
            "command": "codes", "success": True,
            "filename": "main.py", "code": code,
        })
        return code

    def start(self, debug=False):
        """在独立线程中启动 main.py；debug=True 时每行等待 next。"""
        with self._state_lock:
            if self._running:
                raise RuntimeError("已有用户程序在运行")
            if not self.main_file.is_file():
                raise FileNotFoundError("runtime2/main.py 不存在，请先选择程序")
            self._running = True
            self._debugging = bool(debug)

        self._stop_event.clear()
        self._step_event.clear()
        self._worker = threading.Thread(
            target=self._execute,
            name="runtime2-debug" if debug else "runtime2-run",
            daemon=True,
        )
        self._worker.start()
        return True

    def next_step(self):
        if not self.debugging:
            raise RuntimeError("当前不在单步调试状态")
        self._step_event.set()

    def stop(self):
        if not self.running:
            raise RuntimeError("当前没有运行中的程序")
        self._stop_event.set()
        self._step_event.set()

    def _execute(self):
        command = "debug" if self.debugging else "run"
        state = "debugging" if self.debugging else "running"
        self.publisher(STATUS_TOPIC, {
            "command": command, "state": state, "success": True,
            "filename": "main.py",
        })
        try:
            self._source_lines = self.main_file.read_text(encoding="utf-8").splitlines()
            # main.py 位于 runtime2/ 内；导入 ``runtime2`` 包需要把项目根目录
            # 加入 sys.path。runtime2 目录本身仍保留，以兼容用户程序导入同级模块。
            search_paths = (self.runtime_dir, self.runtime_dir.parent)
            for search_path in search_paths:
                path_text = str(search_path)
                if path_text not in sys.path:
                    sys.path.insert(0, path_text)
            old_trace = sys.gettrace()
            sys.settrace(self._trace_lines)
            try:
                runpy.run_path(str(self.main_file), run_name="__main__")
            finally:
                sys.settrace(old_trace)
            self.publisher(STATUS_TOPIC, {
                "command": command, "state": "completed", "success": True,
                "filename": "main.py",
            })
        except StopExecution:
            self.publisher(STATUS_TOPIC, {
                "command": command, "state": "stopped", "success": True,
                "filename": "main.py",
            })
        except Exception as error:
            self.publisher(STATUS_TOPIC, {
                "command": command, "state": "error", "success": False,
                "filename": "main.py", "error": str(error),
                "traceback": traceback.format_exc(),
            })
        finally:
            with self._state_lock:
                self._running = False
                self._debugging = False
            self._step_event.set()

    def _trace_lines(self, frame, event, arg):
        if event != "line":
            return self._trace_lines
        try:
            frame_path = Path(frame.f_code.co_filename).resolve()
        except OSError:
            return self._trace_lines
        if frame_path != self.main_file:
            return self._trace_lines
        if self._stop_event.is_set():
            raise StopExecution()

        line_number = frame.f_lineno
        code = self._source_lines[line_number - 1] if 0 < line_number <= len(self._source_lines) else ""
        self.publisher(STEP_TOPIC, {
            "command": "debug" if self.debugging else "run",
            "filename": "main.py", "lineno": line_number,
            "code": code, "waiting": self.debugging,
        })

        if self.debugging:
            while not self._stop_event.is_set():
                if self._step_event.wait(0.2):
                    self._step_event.clear()
                    break
            if self._stop_event.is_set():
                raise StopExecution()
        return self._trace_lines


class RuntimeDebugService:
    """MQTT 命令入口，文件和执行逻辑由 RuntimeProgramManager 完成。"""

    def __init__(self, broker="localhost", port=1883, runtime_dir=None, mqtt_client=None):
        if mqtt_client is None:
            if mqtt is None:
                raise RuntimeError("启动 MQTT 服务需要安装 paho-mqtt")
            mqtt_client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"runtime2_debug_{os.getpid()}",
            )
        self.broker = broker
        self.port = int(port)
        self.client = mqtt_client
        self.manager = RuntimeProgramManager(runtime_dir, self._publish)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _publish(self, topic, payload):
        self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=2)

    def _publish_error(self, command, error):
        self._publish(STATUS_TOPIC, {
            "command": command, "state": "error", "success": False,
            "error": str(error),
        })

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        failed = reason_code.is_failure if hasattr(reason_code, "is_failure") else reason_code != 0
        if failed:
            print(f"[runtime2] MQTT 连接失败: {reason_code}")
            return
        client.subscribe(CONTROL_TOPIC, qos=2)
        print(f"[runtime2] 已订阅 {CONTROL_TOPIC}")

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            command = payload.get("command", payload.get("cmd"))
            data = payload.get("data")
            self._dispatch(command, data)
        except Exception as error:
            command = locals().get("command") or "unknown"
            print(f"[runtime2] {command} 失败: {error}")
            self._publish_error(command, error)

    def _dispatch(self, command, data=None):
        if command in ("read_files", "read_program_files"):
            self.manager.publish_programs()
        elif command == "copy":
            filename = data.get("filename") if isinstance(data, dict) else data
            self.manager.copy_program(filename)
        elif command == "codes":
            self.manager.publish_main()
        elif command == "run":
            self.manager.start(debug=False)
        elif command == "debug":
            self.manager.start(debug=True)
        elif command == "next":
            self.manager.next_step()
        elif command == "stop":
            self.manager.stop()
        else:
            raise ValueError(f"未知程序命令: {command}")

    def run(self):
        self.client.connect(self.broker, self.port, 60)
        print(f"[runtime2] 程序调试服务已启动，MQTT={self.broker}:{self.port}")
        print(f"[runtime2] programs={self.manager.programs_dir}")
        self.client.loop_forever()


def main():
    parser = argparse.ArgumentParser(description="runtime2 MQTT 程序调试服务")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    args = parser.parse_args()
    RuntimeDebugService(args.broker, args.port).run()


if __name__ == "__main__":
    main()

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
FILE_CONTENT_TOPIC = "/humanoid/programs/file_content"
UPLOAD_RESULT_TOPIC = "/humanoid/programs/upload_result"
DELETE_RESULT_TOPIC = "/humanoid/programs/delete_result"

# runtime2 根目录中属于运行框架的 Python 文件，不向用户程序列表暴露。
INTERNAL_PYTHON_FILES = frozenset({
    "__init__.py",
    "main.py",
    "minth.py",
    "run.py",
})


class StopExecution(Exception):
    """用于从 trace 回调中停止用户程序。"""


class RuntimeProgramManager:
    """管理 runtime2 程序文件、普通执行和 trace 单步执行。"""

    def __init__(self, runtime_dir=None, publisher=None):
        self.runtime_dir = Path(runtime_dir or Path(__file__).resolve().parent).resolve()
        self.main_file = self.runtime_dir / "main.py"
        self.publisher = publisher or (lambda topic, payload: None)
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
        """列出 runtime2 根目录中的用户 Python 程序。"""
        return sorted(
            path.name for path in self.runtime_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".py"
            and path.name not in INTERNAL_PYTHON_FILES
        )

    def publish_programs(self):
        files = self.list_programs()
        self.publisher(FILES_TOPIC, {"command": "read_files", "success": True, "files": files})
        return files

    def _program_target(self, filename):
        """校验程序文件名并返回 runtime2 根目录中的目标路径。"""
        if not isinstance(filename, str) or not filename.lower().endswith(".py"):
            raise ValueError("程序必须是 .py 文件")
        if Path(filename).name != filename or filename in INTERNAL_PYTHON_FILES:
            raise ValueError("程序文件名不合法")
        path = (self.runtime_dir / filename).resolve()
        if path.parent != self.runtime_dir:
            raise ValueError("程序文件名不合法")
        return path

    def _program_path(self, filename):
        """返回已经存在的用户程序路径。"""
        path = self._program_target(filename)
        if not path.is_file():
            raise FileNotFoundError(f"程序不存在: {filename}")
        return path

    def read_program(self, filename):
        """读取用户程序并发布给网页编辑器或下载功能。"""
        source = self._program_path(filename)
        code = source.read_text(encoding="utf-8")
        self.publisher(FILE_CONTENT_TOPIC, {
            "command": "read_file", "success": True,
            "filename": source.name, "code": code,
        })
        return code

    def upload_program(self, filename, content):
        """新增或保存用户程序，使用同目录临时文件原子替换。"""
        target = self._program_target(filename)
        if not isinstance(content, str):
            raise ValueError("程序内容必须是文本")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.runtime_dir,
            prefix=f".{target.stem}-", suffix=".py", delete=False,
        ) as stream:
            stream.write(content)
            temporary_name = stream.name
        os.replace(temporary_name, target)
        self.publisher(UPLOAD_RESULT_TOPIC, {
            "command": "upload", "success": True, "filename": target.name,
        })
        return target

    def delete_program(self, filename):
        """删除指定用户程序；框架文件由文件名校验保护。"""
        target = self._program_path(filename)
        target.unlink()
        self.publisher(DELETE_RESULT_TOPIC, {
            "command": "delete", "success": True, "filename": target.name,
        })
        return target

    def copy_program(self, filename):
        """将选中程序复制为 main.py，并在首行记录原始文件名。"""
        if self.running:
            raise RuntimeError("程序运行中，不能替换 main.py")
        source = self._program_path(filename)
        content = source.read_text(encoding="utf-8")
        source_comment = f"# 本文件内容复制自用户程序：{source.name}\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.runtime_dir,
            prefix=".main-", suffix=".py", delete=False,
        ) as stream:
            stream.write(source_comment)
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

    def _publish_error(self, command, error, data=None):
        result_topic = {
            "read_file": FILE_CONTENT_TOPIC,
            "upload": UPLOAD_RESULT_TOPIC,
            "delete": DELETE_RESULT_TOPIC,
        }.get(command, STATUS_TOPIC)
        filename = data.get("filename") if isinstance(data, dict) else data
        payload = {
            "command": command, "state": "error", "success": False,
            "error": str(error),
        }
        if isinstance(filename, str):
            payload["filename"] = filename
        self._publish(result_topic, payload)

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
            self._publish_error(command, error, locals().get("data"))

    def _dispatch(self, command, data=None):
        if command in ("read_files", "read_program_files"):
            self.manager.publish_programs()
        elif command == "copy":
            filename = data.get("filename") if isinstance(data, dict) else data
            self.manager.copy_program(filename)
        elif command == "read_file":
            filename = data.get("filename") if isinstance(data, dict) else data
            self.manager.read_program(filename)
        elif command == "upload":
            if not isinstance(data, dict):
                raise ValueError("upload 命令缺少 filename 和 content")
            self.manager.upload_program(data.get("filename"), data.get("content"))
            self.manager.publish_programs()
        elif command == "delete":
            filename = data.get("filename") if isinstance(data, dict) else data
            self.manager.delete_program(filename)
            self.manager.publish_programs()
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
        print(f"[runtime2] 用户程序目录={self.manager.runtime_dir}")
        self.client.loop_forever()


def main():
    parser = argparse.ArgumentParser(description="runtime2 MQTT 程序调试服务")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    args = parser.parse_args()
    RuntimeDebugService(args.broker, args.port).run()


if __name__ == "__main__":
    main()

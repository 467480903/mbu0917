from pathlib import Path
from unittest.mock import Mock
import common
import programs


def test_upload_read_and_delete_program(tmp_path, monkeypatch):
    common.PROGRAMS_DIR = str(tmp_path)
    monkeypatch.setattr(common, "publish", Mock())
    programs.handle_upload({"filename":"demo.py", "code":"value = 1\n"})
    assert (tmp_path / "demo.py").read_text() == "value = 1\n"
    programs.handle_read_file("demo.py")
    assert common.publish.call_args.args[1]["code"] == "value = 1\n"
    programs.handle_delete("demo.py")
    assert not (tmp_path / "demo.py").exists()


def test_program_file_operations_reject_path_traversal(tmp_path, monkeypatch):
    common.PROGRAMS_DIR = str(tmp_path)
    monkeypatch.setattr(common, "publish", Mock())
    programs.handle_upload({"filename":"../escape.py", "code":"x=1"})
    assert not (tmp_path.parent / "escape.py").exists()
    programs.handle_read_file("../escape.py")
    assert common.publish.call_args.args[1]["success"] is False

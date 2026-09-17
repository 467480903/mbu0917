from types import SimpleNamespace
from unittest.mock import Mock
import common
import data
import positions


def test_value_pose_conversion_and_mm_offset():
    pose = positions._value_to_pose({"x": 1, "y": 2, "z": 3, "rx": 0, "ry": 0, "rz": 0})
    assert pose["orientation"] == [0.0, 0.0, 0.0, 1.0]
    assert positions._apply_offset({"x": 1}, {"x": 100})["x"] == 1.1


def test_goto_saved_left_position_publishes_success(monkeypatch):
    data.init_db()
    data.save_positions("left", "pick", {"x":1,"y":2,"z":3,"rx":0,"ry":0,"rz":0})
    common.ee_controller = Mock(move_arms_to=Mock(return_value=True))
    monkeypatch.setattr(common, "publish", Mock())
    positions.handle_goto("left", "pick")
    common.ee_controller.move_arms_to.assert_called_once()
    assert common.publish.call_args.args[0] == common.TOPIC_POSITIONS_DATA


def test_control_rejects_invalid_position_request(monkeypatch):
    monkeypatch.setattr(common, "publish", Mock())
    positions.handle_control({"command":"goto", "data":{"type":"invalid"}})
    assert common.publish.call_args.args[1]["data"]["success"] is False

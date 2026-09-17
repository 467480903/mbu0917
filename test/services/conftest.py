"""Shared isolation layer for services tests.

The production services import robot/PLC libraries at module import time.  This
file supplies small, in-process substitutes so tests never open hardware,
MQTT, or PLC connections.
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))


def _install_module_stubs():
    if "agibot_gdk" not in sys.modules:
        gdk = types.ModuleType("agibot_gdk")
        gdk.GDKRes = SimpleNamespace(kSuccess=0)
        gdk.CameraType = SimpleNamespace(kHeadColor=0, kHeadDepth=1, kLeftHandColor=2, kRightHandColor=3)
        gdk.Encoding = SimpleNamespace(JPEG=0, PNG=1)
        gdk.ColorFormat = SimpleNamespace(RGB=0, BGR=1, GRAY8=2)
        gdk.LidarType = SimpleNamespace(kLidarFront=0, kLidarBack=1)
        gdk.EndEffectorControlGroup = SimpleNamespace(kLeftArm=0, kRightArm=1)
        gdk.gdk_init = Mock(return_value=0)
        gdk.gdk_release = Mock(return_value=0)
        for name in ("Robot", "Interaction", "Camera", "Slam", "Map", "Lidar", "Pnc", "Twist", "Vector3", "NaviReq", "EndEffectorPose", "JointStates", "JointState"):
            setattr(gdk, name, type(name, (), {}))
        sys.modules["agibot_gdk"] = gdk

    if "paho.mqtt.client" not in sys.modules:
        paho = types.ModuleType("paho")
        mqtt_pkg = types.ModuleType("paho.mqtt")
        client = types.ModuleType("paho.mqtt.client")
        client.CallbackAPIVersion = SimpleNamespace(VERSION2=2)
        client.Client = Mock
        sys.modules.update({"paho": paho, "paho.mqtt": mqtt_pkg, "paho.mqtt.client": client})

    if "snap7" not in sys.modules:
        snap7 = types.ModuleType("snap7")
        snap7_client = types.ModuleType("snap7.client")
        snap7_client.Client = Mock
        snap7_util = types.ModuleType("snap7.util")
        snap7_util.get_bool = lambda raw, offset, bit: bool(raw[offset] & (1 << bit))
        snap7_util.set_bool = lambda raw, offset, bit, value: raw.__setitem__(offset, (raw[offset] | (1 << bit)) if value else (raw[offset] & ~(1 << bit)))
        snap7.client, snap7.util = snap7_client, snap7_util
        sys.modules.update({"snap7": snap7, "snap7.client": snap7_client, "snap7.util": snap7_util})


_install_module_stubs()

import pytest


@pytest.fixture(autouse=True)
def reset_service_globals(tmp_path, monkeypatch):
    """Reset mutable module globals and redirect persistent paths per test."""
    import common
    import data
    common.DATAS_DIR = str(tmp_path / "datas")
    common.IMAGE_SAVE_DIR = str(tmp_path / "images")
    common.DETECT_SAVE_DIR = str(tmp_path / "detect")
    common.PROGRAMS_DIR = str(tmp_path / "programs")
    common.MAIN_PY = str(tmp_path / "runtime_main.py")
    common.mqtt_client = None
    common._state = "idle"
    common._gdk_ready = False
    for name in ("robot", "interaction", "camera", "slam", "gmap", "lidar", "ee_controller", "nav"):
        setattr(common, name, None)
    data.DB_PATH = str(tmp_path / "datas" / "robot_data.db")
    data.synch.clear()
    if data._mem_conn:
        data._mem_conn.close()
    if data._file_conn:
        data._file_conn.close()
    data._mem_conn = data._file_conn = None
    yield
    if data._mem_conn:
        data._mem_conn.close()
    if data._file_conn:
        data._file_conn.close()

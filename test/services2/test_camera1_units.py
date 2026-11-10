"""不加载 GDK、不联网：检查单路隔离、断线到期及 LLM 输出校验。"""
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "service2"))
from camera_controller import CameraController
from llm_controller import LlmController


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.camera = CameraController(SimpleNamespace(Camera=lambda: None),
            SimpleNamespace(publish=lambda *a, **k: self.messages.append(a)), "response", "/unused")
        self.camera._save_jpeg = lambda name, data: name + ".jpg"
        self.camera._preview_image = lambda data: data

    def test_independent_start_stop(self):
        self.camera.channel_control("kHeadColor", "start")
        self.camera.channel_control("kHandLeftColor", "start")
        self.camera.channel_control("kHeadColor", "stop")
        self.assertTrue(self.camera.channel_control("kHandLeftColor", "status")["streaming"])
        self.assertFalse(self.camera.channel_control("kHeadDepth", "status")["streaming"])

    def test_only_requested_camera_published_and_saved(self):
        self.camera.channel_control("kHandRightColor", "start")
        self.camera.channel_control("kHandRightColor", "continuous_start")
        self.camera._publish_channels({"kHeadColor": "eA==", "kHandRightColor": "eA=="})
        self.assertEqual(len(self.messages), 1)
        self.assertIn("kHandRightColor/frame", self.messages[0][0])
        self.assertEqual(self.camera.channel_control("kHandRightColor", "status")["saved_count"], 1)
        self.assertEqual(self.camera.channel_control("kHeadColor", "status")["saved_count"], 0)

    def test_expired_lease_stops(self):
        self.camera.channel_control("kHeadColor", "start")
        self.camera.channel_control("kHeadColor", "continuous_start")
        self.camera._channels["kHeadColor"]["expires"] = time.monotonic() - 1
        self.camera._publish_channels({"kHeadColor": "eA=="})
        self.assertEqual(self.messages, [])
        self.assertFalse(self.camera.channel_control("kHeadColor", "status")["continuous"])

    def test_llm_coordinates_and_not_found(self):
        controller = LlmController()
        valid = {"found": True, "points": [[900, 600], [100, 700]], "confidence": .8}
        self.assertEqual(controller._parse_result(json.dumps(valid))["points"][0], [100, 700])
        valid["points"][0][0] = 1001
        with self.assertRaises(ValueError):
            controller._parse_result(json.dumps(valid))
        self.assertEqual(controller._parse_result('{"found":false,"confidence":0}')["points"], [])
        with self.assertRaises(ValueError):
            controller._image_path("../../etc/passwd")


if __name__ == "__main__":
    unittest.main(verbosity=2)

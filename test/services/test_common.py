from types import SimpleNamespace
from unittest.mock import Mock
import common


def test_state_and_publish_serializes_json():
    client = Mock()
    common.mqtt_client = client
    common.set_state("busy")
    assert common.get_state() == "busy"
    common.publish("topic", {"中文": "值"}, qos=2)
    client.publish.assert_called_once_with("topic", '{"中文": "值"}', qos=2)


def test_setup_mqtt_configures_callbacks(monkeypatch):
    client = Mock()
    monkeypatch.setattr(common.mqtt, "Client", Mock(return_value=client))
    on_connect, on_message = Mock(), Mock()
    common.setup_mqtt(on_connect, on_message)
    assert common.mqtt_client is client
    assert client.on_connect is on_connect and client.on_message is on_message
    client.connect.assert_called_once_with("localhost", 1883, keepalive=60)


def test_release_gdk_closes_camera_even_when_close_fails(monkeypatch):
    common._gdk_ready = True
    common.camera = SimpleNamespace(close_camera=Mock(side_effect=RuntimeError("close")))
    common.agibot_gdk.gdk_release = Mock(return_value=common.agibot_gdk.GDKRes.kSuccess)
    common.release_gdk()
    assert common._gdk_ready is False

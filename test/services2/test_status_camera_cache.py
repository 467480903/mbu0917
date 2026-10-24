import json, sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
from camera_controller import CameraController
class MQTT:
    def publish(self, topic, data, qos=0): self.sent = (topic, json.loads(data))
c = CameraController.__new__(CameraController)
c.mqtt_client, c.camera_data_topic = MQTT(), "/humanoid/camera/data"
c.get_cached_frames = lambda: {"kHeadColor":"abc", "kHandLeftColor":"xyz"}
msg = c.publish_cached_frames()
assert msg["head_color"] == "abc" and msg["left_wrist"] == "xyz"
assert c.mqtt_client.sent[0] == "/humanoid/camera/data"
print("PASS camera cache")

import json, sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
from pose_controller import PoseController
class MQTT:
    def publish(self, topic, data, qos=0): self.sent = json.loads(data)
c = PoseController.__new__(PoseController)
c.mqtt_client, c.status_topic = MQTT(), "/humanoid/status/data"
c.get_end_effector_status = lambda: {"left_ee": {"position": [1,2,3]}, "right_ee": None}
msg = c.publish_status()
assert msg["left_ee"]["position"] == [1,2,3]
assert "right_ee" in c.mqtt_client.sent
print("PASS pose status")

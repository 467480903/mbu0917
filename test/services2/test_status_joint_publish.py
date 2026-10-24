import json, sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
from joint_controller import JointController
class MQTT:
    def publish(self, topic, data, qos=0): self.sent = (topic, json.loads(data), qos)
c = JointController.__new__(JointController)
c.mqtt_client, c.status_topic = MQTT(), "/humanoid/status/data"
c.get_current_angles = lambda: {"idx11_head_joint1": 0.1}
msg = c.publish_status()
assert msg["joints"]["idx11_head_joint1"] == 0.1
assert c.mqtt_client.sent[0] == "/humanoid/status/data"
print("PASS joint status")

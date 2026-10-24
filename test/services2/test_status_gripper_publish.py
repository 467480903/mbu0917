import json, sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
from end_effector_controller import EndEffectorController
class MQTT:
    def publish(self, topic, data, qos=0): self.sent = json.loads(data)
c = EndEffectorController.__new__(EndEffectorController)
c.mqtt_client, c.status_topic = MQTT(), "/humanoid/status/data"
c.get_gripper_status = lambda: {"left":{"opening":1}, "right":{"opening":0}}
msg = c.publish_status()
assert msg["grippers"]["left"]["opening"] == 1
assert c.mqtt_client.sent["grippers"]["right"]["opening"] == 0
print("PASS gripper status")

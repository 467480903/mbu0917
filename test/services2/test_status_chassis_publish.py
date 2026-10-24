import json, sys
sys.path.insert(0, "/data/wxf/mbu0917/serivces2")
from chassis_controller import ChassisController
class MQTT:
    def publish(self, topic, data, qos=0): self.sent = json.loads(data)
c = ChassisController.__new__(ChassisController)
c.mqtt_client, c.status_topic = MQTT(), "/humanoid/status/data"
c.get_current_map_pose = lambda: {"position":[1,2,0], "yaw":.3, "loc_state":2, "loc_confidence":.9}
msg = c.publish_status()
assert msg["chassis"]["x"] == 1 and msg["chassis"]["yaw"] == .3
assert c.mqtt_client.sent["chassis"]["loc_state"] == 2
print("PASS chassis status")

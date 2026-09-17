import data


def test_synch_read_write_and_state_transitions():
    data.synch_add({"type":"modbus","action":"read","name":"sensor","value":0,"state":0})
    data.synch_add({"type":"modbus","action":"write","name":"actuator","value":0,"state":0})
    data.synch_update_read("sensor", 42)
    assert data.synch_read("sensor") == 42
    assert data.synch_write("actuator", 7) is True
    assert data.synch_get_pending_writes("modbus") == [{"type":"modbus","action":"write","name":"actuator","value":7,"state":1}]
    assert data.synch_mark_synced("actuator") is True
    assert data.synch_find("actuator")["state"] == 2


def test_database_crud_and_unified_data_api():
    data.init_db()
    data.save_data("joints", "head", "look", {"j1": 1})
    data.save_data("positions", "left", "pick", {"x": 1})
    data.save_data("map_points", "local", "station", {"position": [1, 2, 3]})
    assert data.get_joints() == [{"type":"head", "name":"look", "value":{"j1": 1}}]
    assert data.get_positions("left", "pick")[0]["value"] == {"x": 1}
    assert data.get_map_points()[0]["orientation"] == [0, 0, 0, 1]
    assert {item["category"] for item in data.get_all_data()} == {"joints", "positions", "map_points"}
    data.delete_data("joints", "head", "look")
    assert data.get_joints() == []

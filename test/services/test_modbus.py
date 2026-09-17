import json
from unittest.mock import Mock
import data
import modbus


def test_group_continuous_deduplicates_and_splits_ranges():
    assert modbus._group_continuous([5, 3, 4, 4, 9]) == [(3, 3), (9, 1)]


def test_load_config_initializes_devices_and_synch(tmp_path, monkeypatch):
    config = tmp_path / "modbus.json"
    config.write_text(json.dumps([{"name":"plc","ip":"127.0.0.1","read":{"holdings":[0],"names":["in"]},"write":{"holdings":[10],"names":["out"]}}]))
    monkeypatch.setattr(modbus, "_CONFIG_PATH", str(config))
    modbus.load_config()
    assert modbus._devices[0]["ip"] == "127.0.0.1"
    assert {item["name"] for item in data.synch_snapshot()} == {"in", "out"}


def test_pending_write_marks_only_successful_registers(monkeypatch):
    data.synch_add({"type":"modbus","action":"write","name":"out","value":9,"state":1})
    client = Mock(write_holding_register=Mock(return_value=True))
    monkeypatch.setattr(modbus, "ModbusTcpClient", Mock(return_value=client))
    modbus._process_pending_writes({"ip":"x","port":502,"write_holdings":[10],"write_names":["out"]})
    client.write_holding_register.assert_called_once_with(10, 9)
    assert data.synch_find("out")["state"] == 2

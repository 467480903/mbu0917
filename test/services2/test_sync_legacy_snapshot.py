#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "serivces2"))
from sync_controller import SyncController

sync = SyncController(None, "", "/tmp")
sync._devices = [{"type": "modbus", "name": "demo", "ip": "127.0.0.1", "port": 502,
                  "read_holdings": [1], "read_names": ["r"],
                  "write_holdings": [2], "write_names": ["w"]}]
sync._data_add("r", "read", 7)
sync._data_add("w", "write", 8)
result = sync.legacy_device_snapshots()[0]
assert result["devices"][0]["read"][0]["value"] == 7
assert sync.set_legacy_value({"ip": "127.0.0.1", "address": 2, "value": 9})
assert sync._get_value("w") == 9
print("PASS legacy sync compatibility")

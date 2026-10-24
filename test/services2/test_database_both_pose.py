#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "serivces2"))
from database_controller import DatabaseController

value = {"left": {"x": 1, "y": 2, "z": 3, "rx": .1, "ry": .2, "rz": .3},
         "right": {"position": [4, 5, 6], "orientation": [0, 0, 0, 1]}}
result = DatabaseController._normalize_position_value(value)
assert list(result) == ["left", "right"]
assert result["left"] == {"x": 1., "y": 2., "z": 3., "rx": .1, "ry": .2, "rz": .3}
assert result["right"] == {"x": 4., "y": 5., "z": 6., "rx": 0., "ry": 0., "rz": 0.}
print("PASS both pose normalization")

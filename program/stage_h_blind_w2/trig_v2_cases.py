"""K-4c v2 blind packet (rulings KR-232, KR-233): the value cases of calib.trigger.check, inputs only.

Reads datasets/golden/stage_k/trig_k.json and keeps case_id, operation and inputs of every value case. Never
returns an expected value."""
import json
from pathlib import Path

ITEM = "K-4c"


def load(root):
    doc = json.loads((Path(root) / "datasets/golden/stage_k/trig_k.json").read_text(encoding="utf-8"))
    return [(c["case_id"], c["operation"], c["inputs"]) for c in doc["cases"] if c["expected"]["status"] == "ok"]

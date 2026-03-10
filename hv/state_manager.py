# hv/state_manager.py
import json
from pathlib import Path
from datetime import datetime
from .state import HVState

class HVStateManager:
    def __init__(self, path="hv_state.json"):
        self.path = Path(path)

    def save(self, channels):
        data = {
            "timestamp": datetime.now().isoformat(),
            "channels": {}
        }

        for ch in channels:
            data["channels"][str(ch.ch)] = {
                "state": ch.state.name,
                "vset": ch.vset,
                "iset": ch.iset,
                "ramp_up": ch.rup,
                "last_vmon": getattr(ch, "last_vmon", None),
                "last_imon": getattr(ch, "last_imon", None),
            }

        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)

        tmp.replace(self.path)

    def load(self):
        if not self.path.exists():
            return None

        with open(self.path) as f:
            return json.load(f)
        
        

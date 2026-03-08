# hv/backend/mock.py
from .base import HVBackend
import time

class MockBackend(HVBackend):
    def __init__(self):
        self.channels = {}

    def configure_channel(self, ch, vset, iset, rup=20, rdown=50):
        self.channels[ch] = {
            "vset": vset,
            "iset": iset,
            "vmon": 0.0,
            "imon": 0.0,
            "rup": rup,
            "rdown": rdown,
            "on": False,
        }
        print(f"[MOCK] CH{ch} configurado: V={vset} I={iset}")

    # Implementa exactamente los nombres de la clase abstracta
    def on(self, ch):
        print(f"[MOCK] CH{ch} ON (rampa subida)")
        self.channels[ch]["on"] = True
        for t in range(0, int(self.channels[ch]["vset"] // 25) + 1):
            self.channels[ch]["vmon"] = min(self.channels[ch]["vset"], t * 25)
            time.sleep(0.01)

    def off(self, ch):
        print(f"[MOCK] CH{ch} OFF (rampa bajada)")
        self.channels[ch]["on"] = False
        while self.channels[ch]["vmon"] > 0:
            self.channels[ch]["vmon"] -= 25
            if self.channels[ch]["vmon"] < 0:
                self.channels[ch]["vmon"] = 0
            time.sleep(0.01)

    def set_voltage(self, ch, value):
        self.channels[ch]["vset"] = value

    def set_current(self, ch, value):
        self.channels[ch]["iset"] = value

    def get_vmon(self, ch):
        return self.channels[ch]["vmon"]

    def get_imon(self, ch):
        return self.channels[ch]["iset"] * 0.8  # simulamos 80% del set

backend.configure_channel(ch, vset, iset)

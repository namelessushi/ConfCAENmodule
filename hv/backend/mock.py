# hv/backend/mock_caen.py

import time
import logging
import threading
from hv.backend.base import HVBackend
from hv.safety import HVSafetyError


class MockCAENBackend(HVBackend):

    V_MAX = 1500.0
    I_MAX = 1e-4
    P_MAX_CH = 5.0
    P_MAX_TOTAL = 20.0

    def __init__(self):
        self.logger = logging.getLogger("HV.Backend.MockCAEN")
        self.logger.info("Iniciando MockCAENBackend (sin hardware)")
        self._lock = threading.Lock()
        self.active_channels = set()

        self._channels = {
            ch: {
                "vset": 0.0,
                "iset": 0.0,
                "vmon": 0.0,
                "imon": 0.0,
                "on": False,
                "ramping": False,
                "ovc": False,
                "maxv": False,
                "kill": False,
                "interlock": False
            } for ch in range(4)
        }

    # ==================================================
    # Comunicación simulada
    # ==================================================
    def send_command(self, cmd):
        self.logger.debug(f"[Mock] send_command: {cmd}")
        # Devuelve un OK genérico para cualquier SET
        if "SET" in cmd:
            return "OK"
        # Devuelve VAL:0 para monitores
        return "VAL:0"

    def _expect_ok(self, resp, context="SET"):
        if "OK" not in resp:
            raise RuntimeError(f"[Mock] Respuesta inesperada ({context}): '{resp}'")

    def _parse_val(self, resp, label):
        if "VAL:" not in resp:
            raise RuntimeError(f"[Mock] No se recibió VAL en {label}: '{resp}'")
        try:
            val_part = resp.split("VAL:")[1].split(";")[0]
            return float(val_part)
        except Exception as e:
            raise RuntimeError(f"[Mock] Parse fallo en {label}: {e} | resp='{resp}'")

    # ==================================================
    # SETTERS
    # ==================================================
    def set_voltage(self, ch, vset):
        if vset > self.V_MAX:
            raise HVSafetyError(f"CH{ch}: VSET {vset}V excede máximo físico")
        self._channels[ch]["vset"] = vset
        self.logger.info(f"CH{ch}: VSET fijado en {vset:.2f} V")

    def set_current(self, ch, iset):
        if iset > self.I_MAX:
            raise HVSafetyError(f"CH{ch}: ISET {iset}A excede máximo físico")
        self._channels[ch]["iset"] = iset
        self.logger.info(f"CH{ch}: ISET fijado en {iset:.2e} A")

    def set_ramp_up(self, ch, ramp_speed):
        self.logger.info(f"CH{ch}: RUP fijado en {ramp_speed}")

    def on(self, ch):
        with self._lock:
            state = self._channels[ch]
            if state["kill"] or state["interlock"]:
                raise HVSafetyError(f"CH{ch}: no se puede encender, interlock/kill activo")
            state["on"] = True
            state["ramping"] = True
            self.active_channels.add(ch)
            self.logger.info(f"CH{ch} -> ON simulado")

    def off(self, ch):
        with self._lock:
            state = self._channels[ch]
            state["on"] = False
            state["ramping"] = False
            self.active_channels.discard(ch)
            self.logger.info(f"CH{ch} -> OFF simulado")

    # ==================================================
    # MONITOREO
    # ==================================================
    def get_vmon(self, ch):
        ch_state = self._channels[ch]
        if ch_state["ramping"]:
            ch_state["vmon"] += 0.1 * (ch_state["vset"] - ch_state["vmon"])
            if abs(ch_state["vmon"] - ch_state["vset"]) < 0.01:
                ch_state["vmon"] = ch_state["vset"]
                ch_state["ramping"] = False
        return ch_state["vmon"]

    def get_imon(self, ch):
        return self._channels[ch]["iset"] + 1e-6

    def get_channel_status(self, ch):
        return self._channels[ch].copy()

    def get_all_vmon(self):
        return {ch: self.get_vmon(ch) for ch in range(4)}

    def get_all_imon(self):
        return {ch: self.get_imon(ch) for ch in range(4)}

    def get_all_status(self):
        return {ch: self.get_channel_status(ch) for ch in range(4)}

    # ==================================================
    # CONTROL DE ERRORES
    # ==================================================
    def trigger_kill(self, ch):
        self._channels[ch]["kill"] = True

    def trigger_interlock(self, ch):
        self._channels[ch]["interlock"] = True

    def trigger_ovc(self, ch):
        self._channels[ch]["ovc"] = True

    # ==================================================
    # CIERRE
    # ==================================================
    def close(self):
        self.logger.info("MockCAENBackend cerrado (sin hardware)")

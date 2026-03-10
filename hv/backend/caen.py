# hv/backend/caen.py

import time
import logging
import threading
import pyvisa

from hv.backend.base import HVBackend
from hv.safety import HVSafetyError


class CAENBackend(HVBackend):

    V_MAX = 1500.0
    I_MAX = 1e-4
    P_MAX_CH = 5.0
    P_MAX_TOTAL = 20.0

    def __init__(self, resource_name,
                 timeout_ms=5000,
                 max_retries=3,
                 retry_delay=0.2):

        self.logger = logging.getLogger("HV.Backend.CAEN")
        self.logger.info(f"Iniciando backend CAEN en {resource_name}")

        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.active_channels = set()

        #Lock global → hace thread-safe todo el backend
        self._lock = threading.Lock()

        try:
            self.rm = pyvisa.ResourceManager()
            self.inst = self.rm.open_resource(resource_name)

            self.inst.timeout = timeout_ms
            self.inst.write_termination = '\n'
            self.inst.read_termination = '\n'

            self.logger.info("Conexión VISA establecida satisfactoriamente")

        except Exception as e:
            self.logger.error(f"No se pudo conectar al módulo CAEN: {e}")
            raise

    # ==================================================
    # Comunicación robusta (THREAD SAFE)
    # ==================================================

    def send_command(self, cmd):
        """
        Envía comando al módulo CAEN de forma protegida.
        Nunca hace clear agresivo.
        Nunca mezcla respuestas entre threads.
        """

        with self._lock:

            for attempt in range(1, self.max_retries + 1):

                try:
                    resp = self.inst.query(cmd)

                    if not resp:
                        raise RuntimeError("Respuesta vacía del HV")

                    resp = resp.strip()

                    return resp

                except Exception as e:
                    self.logger.warning(
                        f"[CAEN] Intento {attempt}/{self.max_retries} falló: {e}"
                    )
                    time.sleep(self.retry_delay)

            raise RuntimeError(f"send_command falló definitivamente: {cmd}")

    # ==================================================
    # Helpers
    # ==================================================

    def _expect_ok(self, resp, context="SET"):
        if "OK" not in resp:
            raise RuntimeError(f"Respuesta inesperada ({context}): '{resp}'")

    def _parse_val(self, resp, label):
        """
        Parser tolerante:
        - Si hay basura antes o después → intenta rescatar VAL:
        - Si no existe → error claro
        """

        if "VAL:" not in resp:
            raise RuntimeError(f"No se recibió VAL en {label}: '{resp}'")

        try:
            val_part = resp.split("VAL:")[1]
            val_part = val_part.split(";")[0]
            return float(val_part)

        except Exception as e:
            raise RuntimeError(f"Parse fallo en {label}: {e} | resp='{resp}'")

    # ==================================================
    # SETTERS
    # ==================================================

    def set_voltage(self, ch, vset):

        if vset > self.V_MAX:
            raise HVSafetyError(f"CH{ch}: VSET {vset}V excede máximo físico")

        cmd = f"$CMD:SET,CH:{ch},PAR:VSET,VAL:{float(vset):.2f}"
        resp = self.send_command(cmd)
        self._expect_ok(resp, "VSET")

        self.logger.info(f"CH{ch}: VSET fijado en {vset:.2f} V")

    def set_current(self, ch, iset):
        # iset está en Amperios
        if iset > self.I_MAX:
            raise HVSafetyError(f"CH{ch}: ISET {iset}A excede máximo físico")
      # **NO multiplicar por 1e6 si la fuente ya espera A**
        iset_to_send = iset * 1e6  # solo si la fuente espera µA

        cmd = f"$CMD:SET,CH:{ch},PAR:ISET,VAL:{iset_to_send:.2f}"
        resp = self.send_command(cmd)
        self._expect_ok(resp, "ISET")

        self.logger.info(f"CH{ch}: ISET fijado en {iset_to_send:.2f} uA")


    def set_ramp_up(self, ch, ramp_speed):

        cmd = f"$CMD:SET,CH:{ch},PAR:RUP,VAL:{int(ramp_speed)}"
        resp = self.send_command(cmd)
        self._expect_ok(resp, "RUP")

    def on(self, ch):

        cmd = f"$CMD:SET,CH:{ch},PAR:ON"
        resp = self.send_command(cmd)
        self._expect_ok(resp, "ON")

        self.active_channels.add(ch)
        self.logger.info(f"CH{ch} -> ON enviado")

    def off(self, ch):

        cmd = f"$CMD:SET,CH:{ch},PAR:OFF"
        resp = self.send_command(cmd)
        self._expect_ok(resp, "OFF")

        self.active_channels.discard(ch)
        self.logger.info(f"CH{ch} -> OFF enviado")

    # ==================================================
    # MONITOREO
    # ==================================================

    def get_vmon(self, ch):

        resp = self.send_command(f"$CMD:MON,CH:{ch},PAR:VMON")
        return self._parse_val(resp, f"VMON CH{ch}")

    def get_imon(self, ch):

        resp = self.send_command(f"$CMD:MON,CH:{ch},PAR:IMON")
        val_ua = self._parse_val(resp, f"IMON CH{ch}")

        return val_ua * 1e-6

    def get_channel_status(self, ch):

        resp = self.send_command(f"$CMD:MON,CH:{ch},PAR:STAT")
        val = self._parse_val(resp, f"STAT CH{ch}")

        stat = int(val)

        return {
            "on":        bool(stat & 1),
            "ramping":   bool(stat & 2) or bool(stat & 4),
            "ovc":       bool(stat & 8),
            "maxv":      bool(stat & 64),
            "kill":      bool(stat & 2048),
            "interlock": bool(stat & 4096),
        }

    # ==================================================
    # CIERRE
    # ==================================================

    def close(self):

        with self._lock:
            try:
                if hasattr(self, "inst"):
                    self.inst.close()
                if hasattr(self, "rm"):
                    self.rm.close()

                self.logger.info("Sesión VISA cerrada correctamente")

            except Exception as e:
                self.logger.warning(f"Error cerrando VISA: {e}")


    def get_all_vmon(self):
        return {ch: self.get_vmon(ch) for ch in range(4)}

    def get_all_imon(self):
        return {ch: self.get_imon(ch) for ch in range(4)}

    def get_all_status(self):
        return {ch: self.get_channel_status(ch) for ch in range(4)}





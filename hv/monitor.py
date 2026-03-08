# hv/monitor.py

import time
from datetime import datetime
from collections import deque
import logging

from .state import HVState


class HVSample:
    """Muestra instantánea del sistema HV."""
    def __init__(self, ts, vmon, imon, ramping, status):
        self.ts = ts
        self.vmon = vmon
        self.imon = imon
        self.ramping = ramping
        self.status = status

    def as_dict(self):
        return {
            "timestamp": self.ts,
            "vmon": self.vmon,
            "imon": self.imon,
            "ramping": self.ramping,
            "status": self.status,
        }


class HVMonitor:
    """
    Monitor pasivo de HV que:

    - Toma muestras periódicas
    - Evalúa alarmas usando AlarmManager externo
    - No toma decisiones de apagado (solo logging)
    """

    def __init__(
        self,
        channel,
        backend,
        alarm_manager=None,
        period=10,
        buffer_size=360,
        logger=None,
    ):
        self.channel = channel
        self.backend = backend
        self.alarm_manager = alarm_manager
        self.period = period
        self.samples = deque(maxlen=buffer_size)
        self._running = False
        self.logger = logger or logging.getLogger(f"HV.Monitor.CH{channel.ch}")

    def sample(self):
        """Toma una muestra y la almacena en el buffer."""
        ts = datetime.now().isoformat()
        vmon = self.channel.vmon()
        imon = self.channel.imon()
        status = self.backend.get_channel_status(self.channel.ch) or {}

        # Ramping directo desde bits 2 y 4
        stat = status.get("stat", 0)
        ramping = bool(stat & 2) or bool(stat & 4)

        # Crear objeto de muestra
        sample = HVSample(ts, vmon, imon, ramping, status)
        self.samples.append(sample)

        # Evaluación de alarmas
        if self.alarm_manager:
            # Preparar dict coherente para todas las alarmas
            sample_dict = sample.as_dict()
            sample_dict["vset"] = self.channel.vset  # necesario para VoltageMismatchAlarm

            results = self.alarm_manager.evaluate(sample_dict)
            for name, result in results:
                if result is None:
                    continue
                if result.is_critical():
                    self.logger.critical(f"Alarma crítica [{name}]: {result.message}")

        return sample

    def run(self, callback=None):
        """Loop principal del monitor."""
        self._running = True
        while self._running:
            try:
                sample = self.sample()
                if callback:
                    callback(sample)
            except Exception as e:
                self.logger.error(f"Error de muestreo: {e}")
            time.sleep(self.period)

    def stop(self):
        self._running = False




# hv/monitor.py

import time
from datetime import datetime
from collections import deque
import logging

from .state import HVState
from .alarm_manager import AlarmManager

class HVMonitor:
    def __init__(self, hv_system, backend, alarm_manager=None, period=1.0, logger=None):
        self.hv_system = hv_system
        self.backend = backend
        self.alarm_manager = alarm_manager
        self.period = period
        self._running = False
        self.logger = logger or logging.getLogger("HV.Monitor")

    def _sample_all(self):
        # Leemos todos los canales en batch
        try:
            vmon_all = self.backend.get_all_vmon()
            imon_all = self.backend.get_all_imon()
            status_all = self.backend.get_all_status()
            


            for ch in self.hv_system.channels:

                v = vmon_all[ch.ch]
                i = imon_all[ch.ch]
                status = status_all[ch.ch]
                
                ch.update_cache(v, i)
                ch._last_status = status

                sample = {"timestamp": datetime.now(), "vmon": v, "imon": i, "vset": ch.vset, "ramping": status_all[ch.ch].get("ramping", False)}


                if self.alarm_manager:
                    self.alarm_manager.evaluate(sample)


        except Exception as e:
            self.logger.error(f"Error leyendo backend: {e}")


    def run(self):
        self._running = True
        next_tick = time.monotonic()

        while self._running:

            self._sample_all()

            next_tick += self.period
            time.sleep(max(0, next_tick - time.monotonic()))


    def stop(self):
        self._running = False
    
    
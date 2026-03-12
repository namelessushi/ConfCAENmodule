# hv/monitor.py
"""
Monitor de muestras batch para sistema HV.

- Lee todos los canales en batch (atómico)
- Evalúa alarmas
- Actualiza timestampspara el watchdog
"""

import time
import threading
from datetime import datetime
from collections import deque
import logging

from .state import HVState
from .alarm_manager import AlarmManager


class HVMonitor:
    """Monitor batch de canales HV con detección de alarmas."""

    def __init__(self, hv_system, backend, alarm_manager=None, period=1.0, logger=None):
        """
        Inicializa el monitor.
        
        Parameters
        ----------
        hv_system : HVSystem
            Sistema de canales a monitorear
        backend : HVBackend
            Backend para leer datos
        alarm_manager : AlarmManager, optional
            Gestor de alarmas
        period : float
            Período de muestreo en segundos
        logger : Logger, optional
            Logger personalizado
        """
        self.hv_system = hv_system
        self.backend = backend
        self.alarm_manager = alarm_manager
        self.period = period
        self._running = False
        self.logger = logger or logging.getLogger("HV.Monitor")
        self.thread = None

    def _sample_all(self):
        """
        Lee todos los canales en batch (operación atómica).
        
        Actualiza:
        - Cache de voltaje/corriente en cada canal
        - Status último conocido (_last_status)
        - Timestamp de actualización (_last_update)
        - Evalúa alarmas
        """
        try:
            now = time.monotonic()
            
            # 1. Lectura batch del backend (atómica)
            vmon_all = self.backend.get_all_vmon()
            imon_all = self.backend.get_all_imon()
            status_all = self.backend.get_all_status()

            # 2. Actualizar cada canal
            for ch in self.hv_system.channels:

                v = vmon_all[ch.ch]
                i = imon_all[ch.ch]
                status = status_all[ch.ch]

                # Actualizar cache
                ch.update_cache(v, i)
                
                # Actualizar status último conocido
                ch._last_status = status
                
                # 🔴 CRÍTICO: Actualizar timestamp para watchdog deadman
                ch._last_update = now

                # 3. Crear sample para alarmas
                sample = {
                    "timestamp": datetime.now(),
                    "vmon": v,
                    "imon": i,
                    "vset": ch.vset,
                    "ramping": status.get("ramping", False)
                }

                # 4. Evaluar alarmas
                if self.alarm_manager:
                    results = self.alarm_manager.evaluate(sample)
                    
                    # Logging de alarmas activas
                    active_alarms = self.alarm_manager.active(results)
                    if active_alarms:
                        for alarm_name, alarm_result in active_alarms:
                            level_str = alarm_result.level.name if hasattr(alarm_result, 'level') else "UNKNOWN"
                            self.logger.warning(f"[CH{ch.ch}] Alarma {alarm_name}: {level_str}")

        except Exception as e:
            self.logger.error(f"❌ Error leyendo backend: {e}", exc_info=True)

    def run(self):
        """Ejecuta el loop de monitoreo."""
        self._running = True
        next_tick = time.monotonic()

        self.logger.info("✓ Monitor iniciado")

        try:
            while self._running:

                self._sample_all()

                # Timing preciso
                next_tick += self.period
                sleep_time = max(0, next_tick - time.monotonic())
                time.sleep(sleep_time)
        
        except Exception as e:
            self.logger.error(f"❌ Error en loop monitor: {e}", exc_info=True)
        
        finally:
            self.logger.info("✓ Monitor detenido")

    def stop(self):
        """Detiene el monitor."""
        self._running = False
# hv_run.py
"""
Sistema de control de alto voltaje para PMT detector con módulos CAEN DT55XXE.

Flujo:
    1. Inicializar sistema (backend, canales, monitor, watchdog)
    2. Encender canales en secuencia
    3. Loop infinito monitoreo + logging
    4. Shutdown graceful en signals
"""

import time
import csv
import signal
import sys
import os
import threading
import logging
from datetime import datetime
from pathlib import Path
from collections import namedtuple

from hv.backend.caen import CAENBackend
from hv.channel import HVChannel
from hv.logger import setup_logger
from hv.watchdog import HVWatchdog
from hv.state_manager import HVStateManager
from hv.system import HVSystem

from hv.alarm_manager import AlarmManager
from hv.alarms.leakage import LeakageAlarm
from hv.alarms.mismatch import VoltageMismatchAlarm
from hv.alarms.voltage_stability import VoltageStabilityAlarm
from hv.monitor import HVMonitor


# ==========================================================
# CONFIGURACIÓN CENTRAL
# ==========================================================

CONFIG = {
    "resource": "ASRL/dev/ttyACM0::INSTR",
    "connection_retry": 30,
    "connection_timeout": 5000,
    "deadman_timeout": 60,
    "channels": [
        {
            "ch": 0,
            "vset": 1350.0,
            "iset": 1e-4,
            "rup": 25,
        }
    ],
    "watchdog": {
        "check_period": 0.5,
        "auto_shutdown": True,
    },
    "monitor": {
        "period": 1.0,  # Período de muestreo del monitor
    },
    "log_interval": 10.0,
    "log_directory": "logs",
}


# ==========================================================
# CSV LOGGER ROTATIVO
# ==========================================================

class DailyCSVLogger:
    """Logger CSV que rota diariamente con headers automáticos."""

    def __init__(self, log_dir):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.current_day = None
        self.file = None
        self.writer = None

    def _open_new_file(self, day):
        """Abre un nuevo archivo CSV y escribe headers."""
        filename = self.log_dir / f"hv_log_{day.strftime('%Y%m%d')}.csv"
        file = open(filename, "a", newline="")
        writer = csv.writer(file)

        if file.tell() == 0:
            writer.writerow([
                "Timestamp",
                "Channel",
                "Voltage_V",
                "Current_A",
                "Status"
            ])
            file.flush()

        self.file = file
        self.writer = writer
        self.current_day = day

    def log(self, channel_id, v, i, status):
        """Log una muestra al archivo CSV rotativo."""
        now = datetime.now()

        if self.current_day != now.date():
            if self.file:
                self.file.close()
            self._open_new_file(now.date())

        self.writer.writerow([
            now.isoformat(),
            channel_id,
            f"{v:.2f}",
            f"{i:.3e}",
            status
        ])
        self.file.flush()

    def close(self):
        """Cierra el archivo CSV."""
        if self.file:
            self.file.close()


# ==========================================================
# CONTROLADOR PRINCIPAL - HVRunner
# ==========================================================

class HVRunner:
    """
    Orquestador principal del sistema HV.
    
    Responsabilidades:
    - Inicializar componentes (backend, sistema, monitor, watchdog)
    - Encender canales
    - Loop principal con logging y persistencia
    - Shutdown graceful
    """

    def __init__(self, config):
        self.config = config
        self.logger = setup_logger()

        # Componentes principales
        self.backend = None
        self.hv_system = HVSystem()
        self.watchdog = None
        self.state_mgr = HVStateManager()
        self.csv_logger = DailyCSVLogger(config["log_directory"])
        self.alarm_manager = None
        self.monitor = None

        # Control de flujo
        self.running = True
        self._monitor_thread = None
        self._watchdog_thread = None

        self.logger.info("HVRunner inicializado")

    # ====================================================
    # INICIALIZACIÓN
    # ====================================================

    def connect_backend(self):
        """Conecta al backend CAEN con reintentos."""
        retry_time = self.config["connection_retry"]

        while True:
            try:
                self.logger.info("Intentando conectar al módulo CAEN...")
                backend = CAENBackend(self.config["resource"])
                self.logger.info("✅ Conexión CAEN establecida")
                return backend

            except Exception as e:
                self.logger.error(f"❌ Error conexión backend: {e}")
                self.logger.warning(f"   Reintentando en {retry_time}s...")
                time.sleep(retry_time)

    def initialize(self):
        """Inicializa todos los componentes del sistema."""
        self.logger.info("=" * 60)
        self.logger.info("INICIALIZANDO SISTEMA HV")
        self.logger.info("=" * 60)

        # 1. Conectar backend
        self.backend = self.connect_backend()
        self.hv_system = HVSystem()

        # 2. Crear canales
        for ch_cfg in self.config["channels"]:
            ch = HVChannel(
                ch=ch_cfg["ch"],
                backend=self.backend,
                vset=ch_cfg["vset"],
                iset=ch_cfg["iset"],
                rup=ch_cfg.get("rup", 20),
            )
            self.hv_system.add_channel(ch)
            self.logger.info(f"   ✓ CH{ch.ch} creado (VSET={ch.vset}V, ISET={ch.iset}A)")

        # 3. Crear alarm manager
        self.alarm_manager = AlarmManager([
            LeakageAlarm(),
            VoltageMismatchAlarm(),
            VoltageStabilityAlarm()
        ])
        self.logger.info("   ✓ Alarmas inicializadas")

        # 4. Crear monitor (pero NO iniciarlo aún)
        self.monitor = HVMonitor(
            hv_system=self.hv_system,
            backend=self.backend,
            alarm_manager=self.alarm_manager,
            period=self.config["monitor"]["period"],
            logger=self.logger
        )
        self.logger.info("   ✓ Monitor creado")

        self.logger.info("✅ Sistema inicializado correctamente\n")

    # ====================================================
    # OPERACIONES DE POTENCIA
    # ====================================================

    def power_up(self):
        """Enciende todos los canales en secuencia."""
        self.logger.info("=" * 60)
        self.logger.info("POWER-UP: Encendiendo canales")
        self.logger.info("=" * 60)

        for ch in self.hv_system.channels:
            try:
                # Lectura inicial forzada
                vmon = ch.vmon(use_cache=False)
                imon = ch.imon(use_cache=False)
                self.logger.info(f"CH{ch.ch}: VMON={vmon:.2f}V, IMON={imon:.3e}A")

                # Encender con timeout
                self.logger.info(f"CH{ch.ch}: Iniciando encendido...")
                success = ch.turn_on(timeout=60)

                if success:
                    self.logger.info(f"✅ CH{ch.ch} encendido correctamente")
                else:
                    self.logger.error(f"❌ CH{ch.ch} NO alcanzó VSET en timeout")
                    raise RuntimeError(f"Fallo power-up CH{ch.ch}")

            except Exception as e:
                self.logger.critical(f"❌ Error encendiendo CH{ch.ch}: {e}")
                self.shutdown()
                raise

        self.logger.info("✅ Todos los canales encendidos\n")

    def power_down(self):
        """Apaga todos los canales."""
        self.logger.warning("POWER-DOWN: Apagando canales")
        for ch in self.hv_system.channels:
            try:
                ch.turn_off()
                self.logger.info(f"✓ CH{ch.ch} apagado")
            except Exception as e:
                self.logger.error(f"Error apagando CH{ch.ch}: {e}")

    # ====================================================
    # THREADS DE FONDO
    # ====================================================

    def start_monitor(self):
        """Inicia el thread del monitor."""
        self.logger.info("Iniciando monitor...")
        self._monitor_thread = threading.Thread(
            target=self.monitor.run,
            name="HV-Monitor",
            daemon=False
        )
        self._monitor_thread.start()
        self.logger.info("✓ Monitor iniciado")

    def start_watchdog(self):
        """Inicia el watchdog."""
        self.logger.info("Iniciando watchdog...")
        wd_cfg = self.config["watchdog"]

        self.watchdog = HVWatchdog(
            hv_system=self.hv_system,
            check_period=wd_cfg["check_period"],
            auto_shutdown=wd_cfg["auto_shutdown"]
        )

        self._watchdog_thread = threading.Thread(
            target=self.watchdog.start,
            name="HV-Watchdog",
            daemon=False
        )
        self._watchdog_thread.start()
        self.logger.info("✓ Watchdog iniciado")

    # ====================================================
    # MANEJO DE SEÑALES
    # ====================================================

    def _signal_handler(self, sig, frame):
        """Handler para SIGINT (Ctrl+C) y SIGTERM."""
        sig_name = {
            signal.SIGINT: "SIGINT (Ctrl+C)",
            signal.SIGTERM: "SIGTERM"
        }.get(sig, f"Signal {sig}")
        
        self.logger.warning(f"\n⚠️ Recibida señal: {sig_name}")
        self.running = False

    def install_signal_handlers(self):
        """Instala handlers para signals de terminación."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        self.logger.info("✓ Signal handlers instalados")

    # ====================================================
    # LOOP PRINCIPAL
    # ====================================================

    def run_loop(self):
        """Loop principal: logging + persistencia."""
        self.logger.info("=" * 60)
        self.logger.info("LOOP PRINCIPAL: Monitoreo activo")
        self.logger.info("=" * 60)

        last_log = 0
        last_save = 0

        try:
            while self.running:
                now = time.time()

                # CSV logging cada log_interval segundos
                if now - last_log > self.config["log_interval"]:
                    for ch in self.hv_system.channels:
                        try:
                            v = ch.vmon(use_cache=True)
                            i = ch.imon(use_cache=True)
                            status = ch.state.name
                            self.csv_logger.log(ch.ch, v, i, status)
                        except Exception as e:
                            self.logger.error(f"Error log CSV CH{ch.ch}: {e}")
                    last_log = now

                # Persistencia de estado cada 30 segundos
                if now - last_save > 30:
                    try:
                        self.state_mgr.save(self.hv_system.channels)
                    except Exception as e:
                        self.logger.error(f"Error guardando estado: {e}")
                    last_save = now

                time.sleep(0.5)

        except KeyboardInterrupt:
            self.logger.warning("Interrupción en loop principal")
        except Exception as e:
            self.logger.critical(f"Error en loop principal: {e}")
            raise

        self.logger.info("✓ Loop principal terminado")

    # ====================================================
    # SHUTDOWN GRACEFUL
    # ====================================================

    def shutdown(self):
        """Shutdown seguro y ordenado."""
        self.logger.warning("=" * 60)
        self.logger.warning("SHUTDOWN: Deteniendo sistema")
        self.logger.warning("=" * 60)

        # 1. Señalar parada
        self.running = False

        # 2. Detener monitor (espera a que termine)
        if self.monitor:
            try:
                self.logger.info("Deteniendo monitor...")
                self.monitor.stop()
                if self._monitor_thread and self._monitor_thread.is_alive():
                    self._monitor_thread.join(timeout=5)
                    self.logger.info("✓ Monitor detenido")
            except Exception as e:
                self.logger.error(f"Error deteniendo monitor: {e}")

        # 3. Detener watchdog (espera a que termine)
        if self.watchdog:
            try:
                self.logger.info("Deteniendo watchdog...")
                self.watchdog.stop()
                if self._watchdog_thread and self._watchdog_thread.is_alive():
                    self._watchdog_thread.join(timeout=5)
                    self.logger.info("✓ Watchdog detenido")
            except Exception as e:
                self.logger.error(f"Error deteniendo watchdog: {e}")

        # 4. Apagar canales con timeout
        self.logger.info("Apagando canales...")
        for ch in self.hv_system.channels:
            try:
                ch.turn_off()

                # Esperar a que ramping termine
                timeout = 30
                start = time.time()
                while ch.is_ramping() and (time.time() - start < timeout):
                    time.sleep(0.2)

                if ch.is_ramping():
                    self.logger.warning(f"CH{ch.ch}: Ramping no terminó después de {timeout}s")
                else:
                    self.logger.info(f"✓ CH{ch.ch} apagado")

            except Exception as e:
                self.logger.error(f"Error apagando CH{ch.ch}: {e}")

        # 5. Cerrar backend
        if self.backend:
            try:
                self.logger.info("Cerrando backend...")
                self.backend.close()
                self.logger.info("✓ Backend cerrado")
            except Exception as e:
                self.logger.error(f"Error cerrando backend: {e}")

        # 6. Cerrar CSV logger
        try:
            self.csv_logger.close()
        except Exception as e:
            self.logger.error(f"Error cerrando CSV logger: {e}")

        self.logger.warning("=" * 60)
        self.logger.warning("✅ SHUTDOWN COMPLETADO")
        self.logger.warning("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():
    """Función principal."""
    runner = HVRunner(CONFIG)

    try:
        # Instalación temprana de handlers (importante)
        runner.install_signal_handlers()

        # Inicializar
        runner.initialize()

        # Iniciar threads de fondo
        runner.start_monitor()
        runner.start_watchdog()

        # Power-up
        runner.power_up()

        # Pequeña pausa después de power-up
        time.sleep(1)

        # Loop infinito
        runner.run_loop()

    except Exception as e:
        runner.logger.critical(f"❌ ERROR CRÍTICO: {e}", exc_info=True)
        sys.exit(1)

    finally:
        runner.shutdown()
        runner.logger.info("Fin de sesión HV")


if __name__ == "__main__":
    main()
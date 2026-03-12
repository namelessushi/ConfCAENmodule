# hv_run_mock.py

import time
import csv
import signal
import sys
import os
import threading
from datetime import datetime
from pathlib import Path

from hv.backend.mock_caen import MockCAENBackend  # 👈 Aquí usamos el mock
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
    "resource": "MOCK",  # No se usa, es solo un placeholder
    "connection_retry": 5,
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
        "check_period": 2.0,
        "auto_shutdown": True,
    },
    "log_interval": 10.0,
    "log_directory": "logs_mock",
}


# ==========================================================
# CSV LOGGER ROTATIVO
# ==========================================================

class DailyCSVLogger:

    def __init__(self, log_dir):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.current_day = None
        self.file = None
        self.writer = None

    def _open_new_file(self, day):
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
        now = datetime.now()

        if self.current_day != now.date():
            if self.file:
                self.file.close()
            self._open_new_file(now.date())

        self.writer.writerow([
            now.isoformat(),
            channel_id,
            v,
            i,
            status
        ])
        self.file.flush()

    def close(self):
        if self.file:
            self.file.close()


# ==========================================================
# CONTROLADOR PRINCIPAL
# ==========================================================

class HVRunner:

    def __init__(self, config):

        self.config = config
        self.logger = setup_logger()

        self.backend = None
        self.hv_system = HVSystem()
        self.watchdog = None
        self.state_mgr = HVStateManager()
        self.csv_logger = DailyCSVLogger(config["log_directory"])

        self.running = True
        self.deadman_thread = None

    # ------------------------------------------------------
    # Conexión backend MOCK
    # ------------------------------------------------------

    def connect_backend(self):
        self.logger.info("Usando MockCAENBackend")
        return MockCAENBackend()

    # ------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------

    def initialize(self):

        self.backend = self.connect_backend()
        self.hv_system = HVSystem()

        for ch_cfg in self.config["channels"]:

            ch = HVChannel(
                ch=ch_cfg["ch"],
                backend=self.backend,
                vset=ch_cfg["vset"],
                iset=ch_cfg["iset"],
                rup=ch_cfg["rup"],
            )

            self.hv_system.add_channel(ch)

        self.alarm_manager = AlarmManager([LeakageAlarm(), VoltageMismatchAlarm(), VoltageStabilityAlarm()])

        self.monitor = HVMonitor(
            hv_system=self.hv_system,
            backend=self.backend,
            alarm_manager=self.alarm_manager,
            period=1.0,
            logger=self.logger
        )

    # ------------------------------------------------------
    # Encendido automático
    # ------------------------------------------------------

    def power_up(self):
        self.logger.info("Encendido automático de canales HV (MOCK)")
        for ch in self.hv_system.channels:
            _ = ch.vmon()
            _ = ch.imon()
            if not ch.turn_on(timeout=60):
                raise RuntimeError(f"Fallo encendiendo CH{ch.ch}")
        self.logger.info("Todos los canales ON (MOCK)")

    # ------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------

    def start_watchdog(self):
        wd_cfg = self.config["watchdog"]

        self.watchdog = HVWatchdog(
            hv_system=self.hv_system,
            check_period=wd_cfg["check_period"],
            auto_shutdown=wd_cfg["auto_shutdown"]
        )

        self.watchdog.start()
        self.logger.info("Watchdog activo (MOCK)")

    # ------------------------------------------------------
    # Señales
    # ------------------------------------------------------

    def _signal_handler(self, sig, frame):
        self.logger.warning(f"Señal {sig} recibida")
        self.running = False

    def install_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    # ------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------

    def run_loop(self):

        t = threading.Thread(target=self.monitor.run, daemon=True)
        t.start()

        last_log = 0
        last_save = 0

        while self.running:

            now = time.time()

            if now - last_log > self.config["log_interval"]:
                for ch in self.hv_system.channels:
                    try:
                        self.csv_logger.log(ch.ch, ch.vmon(), ch.imon(), ch.state.name)
                    except Exception as e:
                        self.logger.error(f"Error log CSV CH{ch.ch}: {e}")
                last_log = now

            if now - last_save > 30:
                self.state_mgr.save(self.hv_system.channels)
                last_save = now

            time.sleep(0.5)

    # ------------------------------------------------------
    # Shutdown completo
    # ------------------------------------------------------

    def shutdown(self):
        self.logger.warning("Shutdown seguro HV iniciado (MOCK)")

        if self.watchdog:
            try:
                self.watchdog.stop()
            except Exception as e:
                self.logger.error(f"Error deteniendo watchdog: {e}")

        for ch in self.hv_system.channels:
            try:
                ch.turn_off()
                timeout = 5  # más corto en mock
                start = time.time()
                while ch.is_ramping() and (time.time() - start < timeout):
                    time.sleep(0.2)
            except Exception as e:
                self.logger.error(f"Error apagando CH{ch.ch}: {e}")

        if hasattr(self, "monitor") and self.monitor:
            self.monitor.stop()
            if hasattr(self.monitor, "thread"):
                self.monitor.thread.join(timeout=5)

        self.csv_logger.close()
        self.logger.info("HV completamente apagado (MOCK)")


# ==========================================================
# MAIN
# ==========================================================

def main():

    runner = HVRunner(CONFIG)

    try:
        runner.initialize()
        runner.power_up()
        runner.start_watchdog()
        runner.install_signal_handlers()
        time.sleep(1)
        runner.run_loop()

    except Exception as e:
        runner.logger.critical(f"Error crítico en main (MOCK): {e}")

    finally:
        runner.shutdown()
        runner.logger.info("Fin de sesión HV (MOCK)")


if __name__ == "__main__":
    main()

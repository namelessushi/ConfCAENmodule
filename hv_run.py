# hv_run.py

import time
import csv
import signal
import sys
import os
import threading
from datetime import datetime
from pathlib import Path

from hv.backend.caen import CAENBackend
from hv.channel import HVChannel
from hv.logger import setup_logger
from hv.watchdog import HVWatchdog
from hv.state_manager import HVStateManager
from hv.system import HVSystem


# ==========================================================
# CONFIGURACIÓN CENTRAL
# ==========================================================

CONFIG = {
    "resource": "ASRL/dev/ttyACM0::INSTR",
    "connection_retry": 30,
    "deadman_timeout": 60,   # segundos sin heartbeat → kill proceso
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
    "log_directory": "logs",
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

        # ============================
        # DEADMAN (protección freeze)
        # ============================

        self.last_heartbeat = time.time()
        self.deadman_timeout = config["deadman_timeout"]
        self.deadman_thread = None


    # ------------------------------------------------------
    # DEADMAN SUPERVISOR
    # ------------------------------------------------------

    def heartbeat(self):
        self.last_heartbeat = time.time()

    def deadman_supervisor(self):

        self.logger.info("Deadman timer activo")

        while self.running:

            elapsed = time.time() - self.last_heartbeat

            if elapsed > self.deadman_timeout:
                self.logger.critical(
                    f"Deadman activado: {elapsed:.1f}s sin actividad"
                )

                # Mata proceso → systemd lo reinicia
                os._exit(1)

            time.sleep(5)

    def start_deadman(self):

        self.deadman_thread = threading.Thread(
            target=self.deadman_supervisor,
            daemon=True
        )

        self.deadman_thread.start()


    # ------------------------------------------------------
    # Conexión robusta
    # ------------------------------------------------------

    def connect_backend(self):

        retry_time = self.config["connection_retry"]

        while True:
            try:
                self.logger.info("Intentando conectar al módulo CAEN...")
                backend = CAENBackend(self.config["resource"])
                self.logger.info("Conexión establecida")
                return backend

            except Exception as e:
                self.logger.error(f"Error conexión backend: {e}")
                self.logger.warning(f"Reintentando en {retry_time}s...")
                time.sleep(retry_time)


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

        for ch in self.hv_system.channels:
            ch.setup()


    # ------------------------------------------------------
    # Encendido automático SIEMPRE
    # ------------------------------------------------------

    def power_up(self):

        self.logger.info("Encendido automático de canales HV")

        for ch in self.hv_system.channels:
            if not ch.turn_on(timeout=60):
                raise RuntimeError(f"Fallo encendiendo CH{ch.ch}")

        self.logger.info("Todos los canales ON")


    # ------------------------------------------------------
    # Watchdog físico
    # ------------------------------------------------------

    def start_watchdog(self):

        wd_cfg = self.config["watchdog"]

        self.watchdog = HVWatchdog(
            hv_system=self.hv_system,
            check_period=wd_cfg["check_period"],
            auto_shutdown=wd_cfg["auto_shutdown"]
        )

        self.watchdog.start()
        self.logger.info("Watchdog activo")


    # ------------------------------------------------------
    # Loop principal robusto
    # ------------------------------------------------------

    def run_loop(self):

        interval = self.config["log_interval"]

        self.logger.info("Sistema HV en operación")

        while self.running:

            try:

                self.heartbeat()

                for ch in self.hv_system.channels:

                    v = ch.vmon()
                    i = ch.imon()
                    status = self.backend.get_channel_status(ch.ch) or {}

                    self.logger.info(
                        f"[CH{ch.ch}] V={v:.2f} V | I={i:.3e} A | {status}"
                    )

                    self.csv_logger.log(ch.ch, v, i, status)

                self.state_mgr.save(self.hv_system.channels)

                time.sleep(interval)

            except Exception as e:

                self.logger.critical(f"Error en run_loop: {e}")
                self.logger.warning("Intentando reconexión completa...")

                try:
                    self.shutdown_channels_only()
                    self.initialize()
                    self.power_up()
                    self.logger.info("Reconexión exitosa")
                except Exception as recon_error:
                    self.logger.critical(f"Reconexión fallida: {recon_error}")
                    time.sleep(10)


    # ------------------------------------------------------
    # Apagar solo canales
    # ------------------------------------------------------

    def shutdown_channels_only(self):

        for ch in self.hv_system.channels:
            try:
                ch.turn_off()
            except:
                pass


    # ------------------------------------------------------
    # Shutdown completo
    # ------------------------------------------------------

    def shutdown(self):

        self.logger.warning("Shutdown seguro HV iniciado")

        if self.watchdog:
            try:
                self.watchdog.stop()
            except:
                pass

        for ch in self.hv_system.channels:
            try:
                ch.turn_off()
                while ch.is_ramping():
                    time.sleep(1)
            except Exception as e:
                self.logger.error(f"Error apagando CH{ch.ch}: {e}")

        self.csv_logger.close()
        self.logger.info("HV completamente apagado")


    # ------------------------------------------------------
    # Señales
    # ------------------------------------------------------

    def _signal_handler(self, sig, frame):
        self.logger.warning(f"Señal {sig} recibida")
        self.running = False

    def install_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)


# ==========================================================
# MAIN
# ==========================================================

def main():

    runner = HVRunner(CONFIG)

    try:
        runner.install_signal_handlers()
        runner.start_deadman()
        runner.initialize()
        runner.power_up()
        runner.start_watchdog()
        runner.run_loop()

    except Exception as e:
        runner.logger.critical(f"Error crítico en main: {e}")

    finally:
        runner.shutdown()
        runner.logger.info("Fin de sesión HV")


if __name__ == "__main__":
    main()

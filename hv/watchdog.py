# hv/watchdog.py

import time
import logging
import os
from multiprocessing import Process, Pipe
from threading import Thread
from collections import deque

from .state import HVState
from .safety import HVLimits


# ==========================================================
# DEADMAN PROCESS (GIL SAFE)
# ==========================================================

def _deadman_process(conn, timeout):
    last_tick = time.monotonic()

    while True:
        if conn.poll(0.5):
            try:
                conn.recv()
                last_tick = time.monotonic()
            except EOFError:
                break

        if time.monotonic() - last_tick > timeout:
            print("DEADMAN TRIGGERED - HARD EXIT")
            os._exit(1)


# ==========================================================
# WATCHDOG INDUSTRIAL
# ==========================================================

class HVWatchdog:

    # ================================
    # PARÁMETROS FÍSICOS
    # ================================

    DV_DT_LIMIT = 200.0       # V/s (ajustable)
    ENERGY_WINDOW = 5.0       # segundos
    ENERGY_MAX = 0.5          # Joules acumulados en ventana

    VMON_ZERO_THRESHOLD = 5.0
    VMON_ZERO_TIME = 2.0

    DRIFT_REL_TOL = 0.15
    DRIFT_TIME = 2.0

    def __init__(
        self,
        hv_system,
        check_period=0.5,
        max_silence=10.0,
        auto_shutdown=True,
        arduino_serial=None,
    ):

        self.hv_system = hv_system
        self.channels = hv_system.channels
        self.check_period = check_period
        self.max_silence = max_silence
        self.auto_shutdown = auto_shutdown

        self.logger = logging.getLogger("HV.Watchdog")

        now = time.monotonic()

        # =========================
        # Estado temporal
        # =========================
        self.last_ok = {ch.ch: now for ch in self.channels}
        self.prev_sample = {ch.ch: None for ch in self.channels}

        self._vmon_zero_start = {ch.ch: None for ch in self.channels}
        self._drift_start = {ch.ch: None for ch in self.channels}

        # Energía acumulada
        self.energy_buffer = {
            ch.ch: deque() for ch in self.channels
        }

        # =========================
        # Arduino supervisor
        # =========================
        self.arduino = arduino_serial

        # =========================
        # Deadman multiproceso
        # =========================
        self._DEADMAN_TIMEOUT = 3 * check_period
        self._deadman_parent_conn = None
        self._deadman_process = None

        self._running = False
        self._thread = None

        self.logger.info("HVWatchdog Industrial inicializado.")


    # ======================================================
    # FSM INVARIANTS
    # ======================================================

    def _verify_fsm_invariants(self, ch, status):

        if ch.state == HVState.ON and not status.get("on", False):
            self._fault(ch, "FSM violation: ON pero hardware no ON")


    # ======================================================
    # PROTECCIÓN DINÁMICA
    # ======================================================

    def _dynamic_protection(self, ch, v, i, now):

        prev = self.prev_sample[ch.ch]

        if prev is not None:

            dt = now - prev["t"]
            if dt > 0:

                dv = v - prev["v"]
                dv_dt = dv / dt

                # dV/dt
                if abs(dv_dt) > self.DV_DT_LIMIT:
                    self._fault(ch, f"dV/dt excesivo {dv_dt:.1f} V/s")
                    return

                # Energía acumulada
                power = v * i
                energy = power * dt

                buf = self.energy_buffer[ch.ch]
                buf.append((now, energy))

                # Limpiar ventana
                while buf and (now - buf[0][0] > self.ENERGY_WINDOW):
                    buf.popleft()

                total_energy = sum(e for _, e in buf)

                if total_energy > self.ENERGY_MAX:
                    self._fault(ch, f"Energía acumulada alta {total_energy:.3f} J")
                    return

        self.prev_sample[ch.ch] = {"v": v, "t": now}


    # ======================================================
    # CHECK CANAL
    # ======================================================

    def _check_channel(self, ch):

        now = time.monotonic()

        if now - self.last_ok[ch.ch] > self.max_silence:
            self._fault(ch, "Backend silencioso")
            return

        try:
            v = ch.vmon()
            i = ch.imon()
            status = ch.backend.get_channel_status(ch.ch)
            self.last_ok[ch.ch] = now
        except Exception as e:
            self.logger.error(f"[CH{ch.ch}] Error lectura: {e}")
            return

        self._verify_fsm_invariants(ch, status)

        if ch.state == HVState.ON:

            # VMON≈0
            if v < self.VMON_ZERO_THRESHOLD:
                if self._vmon_zero_start[ch.ch] is None:
                    self._vmon_zero_start[ch.ch] = now
                elif now - self._vmon_zero_start[ch.ch] > self.VMON_ZERO_TIME:
                    self._fault(ch, "VMON≈0 persistente")
                    return
            else:
                self._vmon_zero_start[ch.ch] = None

            # Drift
            rel_error = abs(v - ch.vset) / abs(ch.vset)
            if rel_error > self.DRIFT_REL_TOL:
                if self._drift_start[ch.ch] is None:
                    self._drift_start[ch.ch] = now
                elif now - self._drift_start[ch.ch] > self.DRIFT_TIME:
                    self._fault(ch, "Drift persistente")
                    return
            else:
                self._drift_start[ch.ch] = None

            # Sobrecorriente
            if i > ch.iset * HVLimits.I_TRIP_FACTOR:
                self._fault(ch, "Sobrecorriente software")
                return

            # Protección dinámica
            self._dynamic_protection(ch, v, i, now)


    # ======================================================
    # FAULT
    # ======================================================

    def _fault(self, ch, reason):

        self.logger.critical(f"[CH{ch.ch}] FAULT: {reason}")

        ch.state = HVState.FAULT

        if self.auto_shutdown:
            try:
                ch.turn_off()
            except:
                pass


    # ======================================================
    # LOOP
    # ======================================================

    def _loop(self):

        while self._running:

            # Heartbeat proceso
            if self._deadman_parent_conn:
                self._deadman_parent_conn.send(1)

            # Heartbeat Arduino
            if self.arduino:
                try:
                    self.arduino.write(b"HEARTBEAT\n")
                except:
                    pass

            for ch in self.channels:
                self._check_channel(ch)

            time.sleep(self.check_period)


    # ======================================================
    # CONTROL
    # ======================================================

    def start(self):

        if self._running:
            return

        self._running = True

        parent, child = Pipe()
        self._deadman_parent_conn = parent

        self._deadman_process = Process(
            target=_deadman_process,
            args=(child, self._DEADMAN_TIMEOUT),
            daemon=True
        )
        self._deadman_process.start()

        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

        self.logger.info("Watchdog Industrial iniciado.")


    def stop(self):

        self._running = False

        if self._deadman_process:
            self._deadman_process.terminate()

        self.logger.info("Watchdog detenido.")

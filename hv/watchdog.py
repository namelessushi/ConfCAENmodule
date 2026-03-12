# hv/watchdog.py
"""
Watchdog industrial multinivel para sistema HV.

Protecciones implementadas:
- FSM invariants (estados software vs hardware)
- dV/dt limit (máxima velocidad de cambio)
- Energía acumulada (en ventana de tiempo)
- VMON ≈ 0 persistente
- Drift VMON vs VSET
- Sobrecorriente software
- Monitor/Backend silencioso (deadman)
- Deadman process (GIL-safe)
"""

import signal
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
    """
    Proceso independiente que mata el programa si no recibe heartbeats.
    
    Es GIL-safe porque usa multiprocessing, no threading.
    """
    import os, time, logging
    logging.basicConfig(level=logging.CRITICAL)
    last_tick = time.monotonic()

    while True:
        if conn.poll(0.5):
            try:
                conn.recv()
                last_tick = time.monotonic()
            except EOFError:
                break

        if time.monotonic() - last_tick > timeout:
            logging.critical("🔴 DEADMAN TRIGGERED: timeout excedido")
            # Notificar al padre con señal
            os.kill(os.getppid(), signal.SIGTERM)
            break


# ==========================================================
# WATCHDOG INDUSTRIAL
# ==========================================================

class HVWatchdog:
    """Vigilancia multinivel del sistema HV en tiempo real."""

    # ================================
    # PARÁMETROS FÍSICOS
    # ================================

    DV_DT_LIMIT = 200.0         # V/s (máxima velocidad de cambio)
    ENERGY_WINDOW = 5.0         # segundos
    ENERGY_MAX = 0.5            # Joules acumulados en ventana

    VMON_ZERO_THRESHOLD = 5.0   # voltios
    VMON_ZERO_TIME = 2.0        # segundos

    DRIFT_REL_TOL = 0.15        # 15% de tolerancia
    DRIFT_TIME = 2.0            # segundos

    def __init__(
        self,
        hv_system,
        check_period=0.5,
        max_silence=10.0,
        auto_shutdown=True,
        arduino_serial=None,
    ):
        """
        Inicializa el watchdog.
        
        Parameters
        ----------
        hv_system : HVSystem
            Sistema de canales a vigilar
        check_period : float
            Período de verificación en segundos
        max_silence : float
            Máximo tiempo sin actualización del monitor antes de fault
        auto_shutdown : bool
            Si True, apaga automáticamente al detectar fault
        arduino_serial : Serial
            Puerto serial Arduino (opcional para heartbeat externo)
        """

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
        # Supervisor externo
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

        self.logger.info("✓ HVWatchdog Industrial inicializado")

    # ======================================================
    # FSM INVARIANTS
    # ======================================================

    def _verify_fsm_invariants(self, ch, status):
        """Verifica que el estado software coincida con el hardware."""
        if ch.state == HVState.ON and not (status.get("on") or status.get("ramping")):
            self._fault(ch, "FSM violation: software ON pero hardware OFF")

    # ======================================================
    # PROTECCIÓN DINÁMICA
    # ======================================================

    def _dynamic_protection(self, ch, v, i, now):
        """
        Protecciones basadas en tendencias temporales.
        
        - dV/dt excesivo
        - Energía acumulada
        """

        prev = self.prev_sample[ch.ch]

        if prev is not None:

            dt = now - prev["t"]
            if dt > 0:

                dv = v - prev["v"]
                dv_dt = dv / dt

                # 🔴 dV/dt LIMIT
                if abs(dv_dt) > self.DV_DT_LIMIT:
                    self._fault(ch, f"dV/dt excesivo {dv_dt:.1f} V/s")
                    return

                # 🔴 ENERGÍA ACUMULADA
                i_filtered = min(i, ch.iset * 2)  # Filtro heurístico
                power = abs(v * i_filtered)
                energy = power * dt

                buf = self.energy_buffer[ch.ch]
                buf.append((now, energy))

                # Limpiar ventana temporal
                while buf and (now - buf[0][0] > self.ENERGY_WINDOW):
                    buf.popleft()

                total_energy = sum(e for _, e in buf)

                if total_energy > self.ENERGY_MAX:
                    self._fault(ch, f"Energía acumulada alta {total_energy:.3f} J")
                    return

        self.prev_sample[ch.ch] = {"v": v, "i": i, "t": now}

    # ======================================================
    # CHECK CANAL
    # ======================================================

    def _check_channel(self, ch):
        """Verifica un canal individual contra todos los límites."""

        now = time.monotonic()

        # 🔴 DEADMAN: Detectar si el monitor dejó de actualizar
        if now - ch._last_update > self.max_silence:
            self._fault(ch, f"Monitor/Backend silencioso por {self.max_silence}s")
            return

        try:

            v = ch.vmon(use_cache=True)
            i = ch.imon(use_cache=True)
            status = getattr(ch, "_last_status", {})

            # FSM check
            self._verify_fsm_invariants(ch, status)

            # Solo si está encendido
            if ch.state == HVState.ON:

                # 🔴 VMON ≈ 0 PERSISTENTE
                if v < self.VMON_ZERO_THRESHOLD:
                    if self._vmon_zero_start[ch.ch] is None:
                        self._vmon_zero_start[ch.ch] = now
                    elif now - self._vmon_zero_start[ch.ch] > self.VMON_ZERO_TIME:
                        self._fault(ch, "VMON≈0 persistente")
                        return
                else:
                    self._vmon_zero_start[ch.ch] = None

                # 🔴 DRIFT VMON vs VSET
                if ch.vset != 0:
                    rel_error = abs(v - ch.vset) / abs(ch.vset)

                    if rel_error > self.DRIFT_REL_TOL:
                        if self._drift_start[ch.ch] is None:
                            self._drift_start[ch.ch] = now
                        elif now - self._drift_start[ch.ch] > self.DRIFT_TIME:
                            self._fault(ch, f"Drift persistente {rel_error:.1%}")
                            return
                    else:
                        self._drift_start[ch.ch] = None

                # 🔴 SOBRECORRIENTE SOFTWARE
                if i > ch.iset * HVLimits.I_TRIP_FACTOR:
                    self._fault(ch, f"Sobrecorriente {i:.3e}A")
                    return

                # 🔴 PROTECCIONES DINÁMICAS
                self._dynamic_protection(ch, v, i, now)

        except Exception as e:
            self.logger.error(f"[CH{ch.ch}] Error en watchdog: {e}", exc_info=True)

    # ======================================================
    # FAULT HANDLER
    # ======================================================

    def _fault(self, ch, reason):
        """Maneja un evento de fault."""

        self.logger.critical(f"🔴 [CH{ch.ch}] FAULT: {reason}")

        if ch.state != HVState.FAULT:
            ch.state = HVState.FAULT

        if self.auto_shutdown:
            try:
                ch.turn_off()
            except Exception as e:
                self.logger.error(f"Error apagando CH{ch.ch} en fault: {e}")

    # ======================================================
    # LOOP PRINCIPAL
    # ======================================================

    def _loop(self):
        """Loop principal del watchdog."""
        next_tick = time.monotonic()

        while self._running:

            # 💓 HEARTBEAT: Deadman process
            if self._deadman_parent_conn:
                try:
                    self._deadman_parent_conn.send(1)
                except Exception as e:
                    self.logger.error(f"Error heartbeat deadman: {e}")

            # 💓 HEARTBEAT: Arduino (opcional)
            if self.arduino:
                try:
                    self.arduino.write(b"HEARTBEAT\n")
                except Exception as e:
                    self.logger.error(f"Error heartbeat Arduino: {e}")

            # ✅ Verificar cada canal
            for ch in self.channels:
                self._check_channel(ch)

            # ⏱️ Timing preciso
            next_tick += self.check_period
            sleep_time = max(0, next_tick - time.monotonic())
            time.sleep(sleep_time)

    # ======================================================
    # CONTROL
    # ======================================================

    def start(self):
        """Inicia el watchdog."""

        if self._running:
            self.logger.warning("Watchdog ya está ejecutándose")
            return

        self._running = True

        # Crear deadman process
        parent, child = Pipe()
        self._deadman_parent_conn = parent

        self._deadman_process = Process(
            target=_deadman_process,
            args=(child, self._DEADMAN_TIMEOUT),
            daemon=True
        )
        self._deadman_process.start()

        # Crear watchdog thread
        self._thread = Thread(target=self._loop, name="HV-Watchdog", daemon=False)
        self._thread.start()

        self.logger.info("✓ Watchdog Industrial iniciado")

    def stop(self):
        """Detiene el watchdog de forma ordenada."""
        self._running = False

        if self._deadman_process:
            try:
                self._deadman_process.terminate()
                self._deadman_process.join(timeout=2)
            except Exception as e:
                self.logger.error(f"Error terminando deadman process: {e}")

        if self._thread:
            try:
                self._thread.join(timeout=2)
            except Exception as e:
                self.logger.error(f"Error esperando watchdog thread: {e}")

        self.logger.info("✓ Watchdog detenido")
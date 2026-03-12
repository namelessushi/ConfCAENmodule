# hv/system.py
"""
Sistema de control de múltiples canales HV.

Proporciona operaciones de grupo para todos los canales:
- Encender/apagar en secuencia
- Actualización de estados
- Restauración desde persistencia
"""

from .channel import HVChannel
from .safety import HVSafetyError
from .logger import setup_logger
from .state import HVState

logger = setup_logger()


class HVSystem:
    """Administrador de múltiples canales HV."""

    def __init__(self):
        self.channels = []

    def add_channel(self, channel: HVChannel):
        """Agrega un canal al sistema."""
        self.channels.append(channel)

    # ============================
    # OPERACIONES BÁSICAS
    # ============================

    def arm_all(self):
        """Arma todos los canales para encendido."""
        logger.info("Armando todos los canales...")
        for ch in self.channels:
            try:
                ch.arm()
                logger.info(f"CH{ch.ch} -> ARMED")
            except HVSafetyError as e:
                logger.warning(f"CH{ch.ch} error al armar: {e}")

    def turn_on_all(self):
        """Enciende todos los canales en secuencia."""
        logger.info("Encendiendo todos los canales...")
        for ch in self.channels:
            try:
                ch.turn_on()
                logger.info(f"CH{ch.ch} -> {ch.state.name}")
            except HVSafetyError as e:
                logger.warning(f"Error en CH{ch.ch} al encender: {e}")
                self.turn_off_all()
                raise

    def turn_off_all(self):
        """Apaga todos los canales."""
        logger.info("Apagando todos los canales...")
        for ch in self.channels:
            try:
                ch.turn_off()
                logger.info(f"CH{ch.ch} -> {ch.state.name}")
            except HVSafetyError as e:
                logger.warning(f"Error en CH{ch.ch} al apagar: {e}")

    # ============================
    # ESPERA DE ESTABILIZACIÓN
    # ============================

    def wait_all_until_on(self, timeout_per_channel=30, stop_on_fail=False):
        """
        Enciende todos los canales y espera a que alcancen VSET.
        
        Parameters
        ----------
        timeout_per_channel : float
            Timeout máximo por canal en segundos
        stop_on_fail : bool
            Si True, detiene al primer fallo
        """
        logger.info("Esperando que todos los canales alcancen VSET...")
        for ch in self.channels:
            logger.info(f"[CH{ch.ch}] Iniciando encendido y espera hasta VSET...")
            try:
                success = ch.turn_on(timeout=timeout_per_channel)
                if success:
                    logger.info(f"[CH{ch.ch}] Canal ENCENDIDO y VSET alcanzado ({ch.vset}V)")
                else:
                    logger.error(f"[CH{ch.ch}] No se pudo alcanzar VSET")
                    if stop_on_fail:
                        break
            except Exception as e:
                logger.error(f"[CH{ch.ch}] Excepción durante turn_on: {e}")
                ch.state = HVState.ERROR
                if stop_on_fail:
                    break

    # ============================
    # SINCRONIZACIÓN DE ESTADOS
    # ============================

    def update_all_states(self):
        """Actualiza el estado de todos los canales desde el hardware."""
        for ch in self.channels:
            try:
                ch.update_state()
            except Exception as e:
                logger.warning(f"[CH{ch.ch}] Error actualizando estado: {e}")

    # ============================
    # EMERGENCIA
    # ============================

    def kill_all(self):
        """Apagado de emergencia de todos los canales."""
        logger.critical("POWERDOWN KILL activado: apagando todos los canales")
        for ch in self.channels:
            try:
                ch.kill()
            except Exception as e:
                logger.critical(f"[CH{ch.ch}] Fallo al ejecutar KILL: {e}")

    # ============================
    # PERSISTENCIA
    # ============================

    def restore_all(self, state_data):
        """
        Restaura todos los canales desde datos persistidos.
        
        Parameters
        ----------
        state_data : dict
            Datos cargados con HVStateManager.load()
            Debe contener clave 'channels'
        """
        if not state_data or "channels" not in state_data:
            logger.warning("No hay información de canales para restaurar")
            return

        for ch in self.channels:
            ch_id = str(ch.ch)
            if ch_id in state_data["channels"]:
                logger.info(f"Restaurando CH{ch.ch}...")
                ch.restore(state_data["channels"][ch_id])
            else:
                logger.warning(f"[CH{ch.ch}] No se encontró estado previo")
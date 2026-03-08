# hv/system.py
from .channel import HVChannel
from .safety import HVSafetyError
from .logger import setup_logger
from .state import HVState

logger = setup_logger()


class HVSystem:

    def __init__(self):
        self.channels = []

    def add_channel(self, channel: HVChannel):
        self.channels.append(channel)

    # -----------------------------
    # Operaciones básicas
    # -----------------------------
    def arm_all(self):
        logger.info("Armando todos los canales...")
        for ch in self.channels:
            try:
                ch.arm()
                logger.info(f"CH{ch.ch} -> ARMED")
            except HVSafetyError as e:
                logger.warning(f"CH{ch.ch} error al armar: {e}")

    def turn_on_all(self):
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
        logger.info("Apagando todos los canales...")
        for ch in self.channels:
            try:
                ch.turn_off()
                logger.info(f"CH{ch.ch} -> {ch.state.name}")
            except HVSafetyError as e:
                logger.warning(f"Error en CH{ch.ch} al apagar: {e}")

    # -----------------------------
    # Wait all until VSET
    # -----------------------------
    def wait_all_until_on(self, timeout_per_channel=30, stop_on_fail=False):
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

    # -----------------------------
    # Actualización de estados
    # -----------------------------
    def update_all_states(self):
        for ch in self.channels:
            try:
                ch.update_state()
            except Exception as e:
                logger.warning(f"[CH{ch.ch}] Error actualizando estado: {e}")

    # -----------------------------
    # Powerdown KILL
    # -----------------------------
    def kill_all(self):
        logger.critical("POWERDOWN KILL activado: apagando todos los canales")
        for ch in self.channels:
            try:
                ch.kill()
            except Exception as e:
                logger.critical(f"[CH{ch.ch}] Fallo al ejecutar KILL: {e}")
    
    def restore_all(self, state_data):
        """
        Restaura todos los canales desde un dict cargado con HVStateManager.load().
        state_data debe tener la clave 'channels'.
        """
        if not state_data or "channels" not in state_data:
            logger.warning("No hay información de canales para restaurar")
            return

        for ch in self.channels:
            ch_id = str(ch.ch)
            if ch_id in state_data["channels"]:
                ch.restore(state_data["channels"][ch_id])
            else:
                logger.warning(f"[CH{ch.ch}] No se encontró estado previo")
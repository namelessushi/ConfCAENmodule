# hv/channel.py
import time
import logging
from .safety import check_user_params, HVSafetyError, HVLimits
from .state import HVState
from hv.backend.base import HVBackend

logger = logging.getLogger("HV.Channel")


class HVChannel:

    def __init__(self, ch, backend: HVBackend, vset, iset, rup=20, rdown=20, powerdown="KILL"):
        check_user_params(vset, iset)
        self.ch = ch
        self.backend = backend
        self.vset = vset
        self.iset = iset
        self.rup = rup
        self.rdown = rdown
        self.powerdown = powerdown
        self.state = HVState.OFF
        self.last_vmon = 0.0
        self.last_imon = 0.0
        self._vmon_cache = 0.0
        self._imon_cache = 0.0
        self._last_update = 0.0

        try:
            self.update_cache(
                self.backend.get_vmon(self.ch),
                self.backend.get_imon(self.ch)
            )
        except Exception as e:
            logger.warning(f"[CH{self.ch}] No se pudo inicializar cache: {e}")

    def update_cache(self,v,i):
        self._vmon_cache = v
        self._imon_cache = i
        self._last_update = time.monotonic()


    def vmon(self, use_cache=True):
        """
        Retorna VMON. 
        Si use_cache=False, fuerza lectura directa del backend (ignora cache).
        """
        if not use_cache or self._last_update == 0:
            v = self.backend.get_vmon(self.ch)
            i = self.backend.get_imon(self.ch)
            self.update_cache(v, i)
            self.last_vmon = v
            self.last_imon = i
            return v
        return self._vmon_cache

    def imon(self, use_cache=True):
        if not use_cache or self._last_update == 0:
            v = self.backend.get_vmon(self.ch)
            i = self.backend.get_imon(self.ch)
            self.update_cache(v, i)
            self.last_vmon = v
            self.last_imon = i
            return i
        return self._imon_cache




    # -----------------------------
    # Configuración y Encendido
    # -----------------------------
    def setup(self):
        """Configura parámetros en hardware."""
        logger.info(f"[CH{self.ch}] Configurando: VSET={self.vset}V, ISET={self.iset}A")
        self.backend.set_voltage(self.ch, self.vset)
        self.backend.set_current(self.ch, self.iset)
        self.backend.set_ramp_up(self.ch, self.rup)
        # self.backend.set_ramp_down(self.ch, self.rdown) # opcional

    def validate_before_on(self, max_off_voltage=10.0):
        """
        Validación de seguridad antes de encender.
        El canal debe estar cercano a 0V (no a VSET).
        """

        vmon = self.backend.get_vmon(self.ch)
        imon = self.backend.get_imon(self.ch)
        status = self.backend.get_channel_status(self.ch)
        print(f"[DEBUG] CH{self.ch} status: {status}, I_actual={imon:.6f}")



        # ---- Voltaje residual antes de encender ----
        if vmon > max_off_voltage:
            raise HVSafetyError(
                f"CH{self.ch}: VMON={vmon:.2f} V no es cercano a 0 antes de encender"
            )

        # ---- Corriente anómala antes de encender ----
        if imon > min(self.iset * 1.1, HVLimits.I_MAX):
            raise HVSafetyError(
                f"CH{self.ch}: IMON={imon:.3e} A excede límite antes de encender"
            )

        # ---- Interlock / Kill ----
        if status and (status.get("kill") or status.get("interlock")):
            raise HVSafetyError(
                f"CH{self.ch}: Canal en estado KILL o INTERLOCK"
            )


    def turn_on(self, timeout=60):
        """
        Enciende el canal HV de forma segura.
        Flujo correcto:
        OFF → ARMED → RAMPING_UP → ON
        """

        logger.info(f"[CH{self.ch}] Solicitud de encendido")

        # --------- Estados inválidos ---------
        if self.state in (HVState.FAULT, HVState.ERROR):
            logger.error(f"[CH{self.ch}] No se puede encender: estado {self.state.name}")
            return False

        if self.state in (HVState.ON, HVState.RAMPING_UP):
            logger.warning(f"[CH{self.ch}] Ya está encendido o ramping")
            return True

        # --------- Si está OFF, armar primero ---------
        if self.state == HVState.OFF:
            try:
                self.arm()
            except Exception as e:
                logger.error(f"[CH{self.ch}] Falló arm(): {e}")
                return False

        # --------- Verificar que quedó ARMED ---------
        if self.state != HVState.ARMED:
            logger.error(f"[CH{self.ch}] No está ARMED, no se puede encender")
            return False

        # --------- Encendido real ---------
        try:
            self.state = HVState.RAMPING_UP

            self.backend.on(self.ch)
            logger.info(f"[CH{self.ch}] Comando ON enviado")

            # Uso de timeout configurable
            if not self.wait_until_vset(timeout=timeout):
                logger.error(f"[CH{self.ch}] No alcanzó VSET en {timeout}s")
                self.state = HVState.ERROR
                return False

            self.state = HVState.ON
            logger.info(f"[CH{self.ch}] Canal ON estable")

            return True

        except Exception as e:
            logger.error(f"[CH{self.ch}] Error durante encendido: {e}")
            self.state = HVState.ERROR
            return False


    def wait_until_vset(self, timeout=30, tolerance=1.5):
        start_time = time.time()

        while time.time() - start_time < timeout:

            v_actual = self.vmon()
            i_actual = self.imon()
            status = self.backend.get_channel_status(self.ch)
            print(f"[DEBUG] CH{self.ch} status: {status}, I_actual={i_actual:.6f}")



            if status is None:
                logger.warning(f"[CH{self.ch}] No se pudo leer estado, reintentando...")
                time.sleep(0.5)
                continue

            # --------- Checks críticos ---------
            if status.get("kill") or status.get("interlock"):
                logger.critical(f"[CH{self.ch}] Canal en KILL/INTERLOCK! Apagando...")
                self.turn_off()
                return False

            #if status.get("ovc") or i_actual > HVLimits.I_MAX:
            #    logger.critical(
            #        f"[CH{self.ch}] Sobrecorriente detectada ({i_actual:.3e}A)! Apagando..."
            #    )
            #    self.turn_off()
            #    return False
            
            if status.get("ramping"):
                time.sleep(0.5)
                continue


            if v_actual > HVLimits.V_MAX:
                logger.critical(
                    f"[CH{self.ch}] VMON {v_actual:.2f} V excede V_MAX {HVLimits.V_MAX} V"
                )
                self.turn_off()
                return False

            # --------- Chequeo de VSET ---------
            if v_actual >= (self.vset - tolerance):
                return True

            time.sleep(0.5)

        # --------- Timeout ---------
        logger.error(f"[CH{self.ch}] Timeout al alcanzar VSET (VMON={v_actual:.2f}V)")
        return False


    def turn_off(self):
        """Apagado seguro."""
        logger.warning(f"[CH{self.ch}] Apagando canal...")
        try:
            self.backend.off(self.ch)
        except Exception as e:
            logger.error(f"[CH{self.ch}] Fallo al apagar: {e}")
        self.state = HVState.OFF

 
    # -----------------------------
    # Powerdown / KILL
    # -----------------------------
    def kill(self):
        """Apagado de emergencia"""
        logger.critical(f"[CH{self.ch}] POWERDOWN KILL activado")
        self.turn_off()
        self.state = HVState.FAULT

    def restore(self, state_dict):
        """
        Restaura parámetros del canal desde un dict (por ejemplo, cargado desde HVStateManager).

        state_dict debe contener:
        - 'vset', 'iset', 'ramp_up', 'last_vmon', 'last_imon', 'state'
        """
        logger.info(f"[CH{self.ch}] Restaurando estado previo...")

        self.vset = state_dict.get("vset", self.vset)
        self.iset = state_dict.get("iset", self.iset)
        self.rup = state_dict.get("ramp_up", self.rup)
        self.last_vmon = state_dict.get("last_vmon", 0.0)
        self.last_imon = state_dict.get("last_imon", 0.0)

        state_name = state_dict.get("state", "OFF")
        self.state = HVState[state_name] if state_name in HVState.__members__ else HVState.OFF

        # Configurar hardware si no estaba apagado
        if self.state != HVState.OFF:
            try:
                self.setup()  # Re-aplica vset, iset, ramp
                logger.info(f"[CH{self.ch}] Hardware restaurado a VSET={self.vset}, ISET={self.iset}")
            except Exception as e:
                logger.error(f"[CH{self.ch}] Fallo al restaurar hardware: {e}")
                self.state = HVState.ERROR
    def arm(self):
        """
        Prepara el canal sin encenderlo.
        - Valida parámetros
        - Aplica configuración al hardware
        """
        logger.info(f"[CH{self.ch}] Armando canal...")

        if self.state in (HVState.ON, HVState.RAMPING_UP):
            logger.warning(f"[CH{self.ch}] No se puede armar: canal activo")
            return

        if self.state == HVState.FAULT:
            logger.error(f"[CH{self.ch}] No se puede armar: estado FAULT")
            return

        try:
            self.validate_before_on()
            self.setup()
            self.state = HVState.ARMED
            logger.info(f"[CH{self.ch}] Canal ARMED correctamente")
        except HVSafetyError as e:
            logger.critical(f"[CH{self.ch}] Error de seguridad al armar: {e}")
            self.state = HVState.FAULT
            raise
        except Exception as e:
            logger.error(f"[CH{self.ch}] Error al armar: {e}")
            self.state = HVState.ERROR
            raise
    
    def is_ramping(self):
        try:
            status = self.backend.get_channel_status(self.ch)
            return status.get("ramping", False) if status else False
        except Exception as e:
            logger.error(f"[CH{self.ch}] Error is_ramping(): {e}")
            return False
        
    def update_state(self):
        """
        Actualiza el estado del canal sincronizándolo con el backend.
        Lee el estado actual del hardware y actualiza self.state.
        """
        try:
            status = self.backend.get_channel_status(self.ch)
            if status is None:
                logger.warning(f"[CH{self.ch}] No se pudo leer estado del backend")
                return
            
            if status.get("kill") or status.get("interlock"):
                self.state = HVState.FAULT
            elif status.get("on"):
                # Verificar si está ramping
                if status.get("ramping"):
                    self.state = HVState.RAMPING_UP
                else:
                    self.state = HVState.ON
            else:
                self.state = HVState.OFF
                
            logger.debug(f"[CH{self.ch}] Estado actualizado: {self.state.name}")
            
        except Exception as e:
            logger.error(f"[CH{self.ch}] Error actualizando estado: {e}")
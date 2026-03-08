# hv/safety.py

class HVSafetyError(RuntimeError):
    pass


class HVLimits:
    """
    Límites duros del sistema (NO del usuario).
    """

    V_MAX = 2000.0      # Volt
    I_MAX = 3e-3        # Ampere (3 mA)
    I_TRIP_FACTOR = 1.2  # 20% sobre ISET


def check_user_params(vset, iset):
    if vset <= 0 or vset > HVLimits.V_MAX:
        raise HVSafetyError(f"VSET inválido: {vset} V")

    if iset <= 0 or iset > HVLimits.I_MAX:
        raise HVSafetyError(f"ISET inválido: {iset} A")

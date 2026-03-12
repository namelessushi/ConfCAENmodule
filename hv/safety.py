# hv/safety.py
"""
Límites de seguridad para sistema HV con PMT Hamamatsu R14374 y módulo CAEN DT5533EN.
"""

class HVSafetyError(RuntimeError):
    pass


class HVLimits:
    """
    Límites duros del sistema basados en:
    - Hamamatsu PMT R14374: MAX 1500V @ 100μA
    - CAEN DT5533EN: 4W por canal (4kV @ 3mA)
    
    Aplicamos derating (85% del máximo) para seguridad.
    """

    # ========== LÍMITES PARA PMT (Hamamatsu R14374) ==========
    V_MAX = 1500.0              # Voltaje máximo del PMT (V)
    V_SAFE = 1475.0             # 85% derating del máximo
    
    I_MAX = 100e-6              # Corriente máxima del PMT (100 μA)
    I_SAFE = 100e-6              # 85% derating (85 μA)
    I_TRIP_FACTOR = 1.2         # Trigger sobrecorriente a 120% de ISET

    # ========== LÍMITES PARA CAEN DT5533EN ==========
    P_MAX_CH = 4.0              # Potencia máxima por canal (W)
    P_SAFE_CH = 3.4             # 85% derating (3.4W)
    
    P_MAX_TOTAL = 16.0          # Potencia total teórica 4 canales × 4W
    P_SAFE_TOTAL = 13.6         # 85% derating (13.6W)

    # ========== ENERGÍA ACUMULADA ==========
    ENERGY_WINDOW = 5.0         # Ventana temporal (segundos)
    # Energía máxima en 5s @ V=1275V, I=85μA
    # P = 1275 * 85e-6 = 0.108 W
    # E_5s = 0.108 * 5 = 0.54 J
    ENERGY_MAX = 0.6            # Threshold energía acumulada (Joules)


def check_user_params(vset, iset):
    """
    Valida parámetros del usuario contra límites de seguridad.
    """
    # Voltaje
    if vset <= 0 or vset > HVLimits.V_MAX:
        raise HVSafetyError(f"VSET inválido: {vset}V (máximo: {HVLimits.V_MAX}V)")
    
    if vset > HVLimits.V_SAFE:
        raise HVSafetyError(
            f"VSET {vset}V excede límite de seguridad {HVLimits.V_SAFE}V "
            f"(máximo recomendado para Hamamatsu R14374)"
        )

    # Corriente
    if iset <= 0 or iset > HVLimits.I_MAX:
        raise HVSafetyError(f"ISET inválido: {iset}A (máximo: {HVLimits.I_MAX}A)")
    
    if iset > HVLimits.I_SAFE:
        raise HVSafetyError(
            f"ISET {iset}A excede límite de seguridad {HVLimits.I_SAFE}A "
            f"(máximo recomendado para Hamamatsu R14374)"
        )
    
    # Potencia
    power = vset * iset
    if power > HVLimits.P_MAX_CH:
        raise HVSafetyError(
            f"Potencia {power:.3f}W excede límite {HVLimits.P_MAX_CH}W "
            f"(CAEN DT5533EN por canal)"
        )
    
    if power > HVLimits.P_SAFE_CH:
        raise HVSafetyError(
            f"Potencia {power:.3f}W excede límite de seguridad {HVLimits.P_SAFE_CH}W"
        )
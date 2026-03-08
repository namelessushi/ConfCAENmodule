# hv/alarms/leakage.py

from collections import deque
from .base import BaseAlarm, AlarmResult, AlarmLevel


class LeakageAlarm(BaseAlarm):
    """
    Detecta aumento lento y sostenido de corriente (fuga).
    """

    name = "LEAKAGE"

    def __init__(
        self,
        window_size=30,
        slope_threshold=1e-9
    ):
        """
        window_size: número de muestras para evaluar tendencia
        slope_threshold: aumento promedio permitido [A/muestra]
        """
        self.window_size = window_size
        self.slope_threshold = slope_threshold
        self._imon_buffer = deque(maxlen=window_size)

    def evaluate(self, sample: dict) -> AlarmResult:
        """
        sample:
        {
            "imon": float,
            "ramping": bool,
        }
        """

        # No evaluamos durante ramping
        if sample.get("ramping", False):
            self._imon_buffer.clear()
            return AlarmResult(AlarmLevel.OK)

        imon = sample.get("imon")
        if imon is None:
            return AlarmResult(AlarmLevel.OK)

        self._imon_buffer.append(imon)

        # Aún no hay suficientes datos
        if len(self._imon_buffer) < self.window_size:
            return AlarmResult(AlarmLevel.OK)

        # Pendiente promedio simple
        delta_i = self._imon_buffer[-1] - self._imon_buffer[0]
        slope = delta_i / len(self._imon_buffer)

        if slope > self.slope_threshold:
            return AlarmResult(
                AlarmLevel.WARNING,
                f"Corriente en aumento lento (ΔI ≈ {delta_i:.2e} A)"
            )

        return AlarmResult(AlarmLevel.OK)

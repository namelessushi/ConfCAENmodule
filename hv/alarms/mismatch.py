# hv/alarms/mismatch.py

from .base import BaseAlarm, AlarmResult, AlarmLevel


class VoltageMismatchAlarm(BaseAlarm):
    name = "VSET_MISMATCH"

    def __init__(self, tolerance=5.0, max_samples=6):
        """
        tolerance: diferencia permitida |VMON - VSET| [V]
        max_samples: número de muestras consecutivas fuera de tolerancia
        """
        self.tolerance = tolerance
        self.max_samples = max_samples
        self.counter = 0

    def evaluate(self, sample: dict) -> AlarmResult:
        if sample.get("ramping", False):
            self.counter = 0
            return AlarmResult(AlarmLevel.OK)

        vmon = sample.get("vmon")
        vset = sample.get("vset")

        if vmon is None or vset is None:
            return AlarmResult(AlarmLevel.OK)

        if vmon is None or vset is None:
            return AlarmResult(AlarmLevel.OK)

        if abs(vmon - vset) > self.tolerance:
            self.counter += 1
        else:
            self.counter = 0

        if self.counter >= self.max_samples:
            return AlarmResult(AlarmLevel.CRITICAL, f"VMON mismatch persistente ({vmon:.1f} vs {vset:.1f})")

        return AlarmResult(AlarmLevel.OK)




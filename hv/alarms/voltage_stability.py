# hv/alarms/voltage_stability.py

from collections import deque
from statistics import stdev
from .base import BaseAlarm, AlarmResult, AlarmLevel


class VoltageStabilityAlarm(BaseAlarm):
    name = "VOLTAGE_STABILITY"

    def __init__(self, window=20, std_threshold=10.0):
        """
        window: número de muestras
        std_threshold: σ máximo permitido [V]
        """
        self.values = deque(maxlen=window)
        self.std_threshold = std_threshold

    def evaluate(self, sample: dict) -> AlarmResult:
        if sample.get("ramping", False):
            self.values.clear()
            return AlarmResult(AlarmLevel.OK)

        vmon = sample.get("vmon")
        if vmon is None:
            return AlarmResult(AlarmLevel.OK)

        self.values.append(vmon)

        if len(self.values) < self.values.maxlen:
            return AlarmResult(AlarmLevel.OK)

        sigma = stdev(self.values)

        if sigma > self.std_threshold:
            return AlarmResult(
                AlarmLevel.WARNING,
                f"VMON inestable (σ={sigma:.1f} V)"
            )

        return AlarmResult(AlarmLevel.OK)

# hv/alarms/base.py

from enum import Enum, auto
from abc import ABC, abstractmethod


class AlarmLevel(Enum):
    OK = auto()
    WARNING = auto()
    CRITICAL = auto()


class AlarmResult:
    def __init__(self, level: AlarmLevel, message: str = ""):
        self.level = level
        self.message = message

    def is_ok(self):
        return self.level == AlarmLevel.OK

    def is_warning(self):
        return self.level == AlarmLevel.WARNING

    def is_critical(self):
        return self.level == AlarmLevel.CRITICAL


class BaseAlarm(ABC):
    """
    Clase base para TODAS las alarmas.
    NO tiene efectos secundarios.
    """

    name = "BASE"

    @abstractmethod
    def evaluate(self, sample: dict) -> AlarmResult:
        """
        sample contiene mediciones ya tomadas:
        {
            "timestamp": datetime,
            "vmon": float,
            "imon": float,
            "vset": float,
        }
        """
        pass

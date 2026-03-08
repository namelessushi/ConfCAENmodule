#/hv/state.py
from enum import Enum, auto

class HVState(Enum):
    OFF = auto()
    ARMED = auto()
    RAMPING_UP = auto()
    ON = auto()
    RAMPING_DOWN = auto()
    TRIPPED = auto()
    ERROR = auto()
    FAULT = auto()
#ConfCAENmodule/hv/backend/base.py
from abc import ABC, abstractmethod

class HVBackend(ABC):

    @abstractmethod
    def set_voltage(self, ch, voltage):
        pass

    @abstractmethod
    def set_current(self, ch, current):
        pass

    @abstractmethod
    def on(self, ch):
        pass

    @abstractmethod
    def off(self, ch):
        pass

    @abstractmethod
    def get_vmon(self, ch):
        pass

    @abstractmethod
    def get_imon(self, ch):
        pass

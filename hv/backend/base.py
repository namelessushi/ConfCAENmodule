 url=https://github.com/namelessushi/ConfCAENmodule/blob/main/hv/backend/base.py
from abc import ABC, abstractmethod

class HVBackend(ABC):

    @abstractmethod
    def set_voltage(self, ch, voltage):
        pass

    @abstractmethod
    def set_current(self, ch, current):
        pass

    @abstractmethod
    def set_ramp_up(self, ch, ramp_speed):
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

    @abstractmethod
    def get_channel_status(self, ch):
        pass

    @abstractmethod
    def close(self):
        pass

    #implementado 12/03/2026
    @abstractmethod
    def get_all_vmon(self):
        pass

    @abstractmethod
    def get_all_imon(self):
        pass

    @abstractmethod
    def get_all_status(self):
        pass
# hv/alarm_manager.py

from hv.alarms.base import AlarmLevel


class AlarmManager:
    """
    Ejecuta un conjunto de alarmas sobre cada muestra (dict).

    - No toma decisiones de apagado
    - Devuelve resultados para logging o integración con watchdog
    """

    def __init__(self, alarms: list):
        self.alarms = alarms

    def evaluate(self, sample: dict):
        """
        Evalúa todas las alarmas sobre la muestra `sample`.

        Returns
        -------
        list[(str, AlarmResult|None)]
        """
        results = []

        for alarm in self.alarms:

            try:
                result = alarm.evaluate(sample)

            except Exception as exc:
                # Nunca permitir que una alarma rompa el sistema
                result = None

            results.append((alarm.name, result))

        return results


    @staticmethod
    def summarize(results):

        level = AlarmLevel.OK

        for _, result in results:
 
            if result is None:
                continue

            try:

                if result.is_critical():
                    return AlarmLevel.CRITICAL

                if result.is_warning():
                    level = AlarmLevel.WARNING

            except Exception:
                continue

        return level

    @staticmethod
    def active(results):

        active = []

        for name, result in results:

            if result is None:
                continue

            if result.level != AlarmLevel.OK:
                active.append((name, result))
    
        return active


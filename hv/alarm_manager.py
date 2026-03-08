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
        Evalúa todas las alarmas sobre la muestra `sample` (dict)
        Devuelve lista de tuplas (alarm_name, AlarmResult)
        """
        results = []
        for alarm in self.alarms:
            try:
                result = alarm.evaluate(sample)
                results.append((alarm.name, result))
            except Exception:
                # Nunca permitir que una alarma rompa el sistema
                results.append((alarm.name, None))
        return results

    @staticmethod
    def summarize(results):
        """
        Devuelve el nivel más alto detectado de una lista de resultados
        """
        level = AlarmLevel.OK
        for _, result in results:
            if result is None:
                continue
            if result.is_critical():
                return AlarmLevel.CRITICAL
            if result.is_warning():
                level = AlarmLevel.WARNING
        return level

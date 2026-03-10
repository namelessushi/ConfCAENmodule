Protecciones implementadas:

- Drift Vmon vs Vset
- Corriente excesiva
- Energía acumulada
- dV/dt excesivo
- Vmon ~ 0 persistente
- Deadman multiproceso

En caso de fallo:

Watchdog → backend.shutdown_all()

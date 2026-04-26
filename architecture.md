         # Arquitectura del Sistema ConfCAENmodule

## Resumen Ejecutivo

ConfCAENmodule es un sistema de control y monitoreo de alto voltaje (HV) diseñado para operar fotomultiplicadores (PMT) Hamamatsu en entornos de física de partículas. El sistema implementa un modelo de capas con separación estricta de responsabilidades: adquisición de datos (Backend), lógica de canal (Channel/System), monitoreo en tiempo real (Monitor), vigilancia multinivel (Watchdog) y orquestación (Runner).

### Motivación física

La ganancia de un PMT varía como G ∝ V^n (n ≈ 7 para el R14374), lo que impone requerimientos estrictos sobre la estabilidad del voltaje de polarización. El diseño en capas de este sistema no es una elección estética: cada capa existe porque hay una consecuencia física si falla:

| Capa | Componente | Consecuencia física si falla |
|------|-----------|------------------------------|
| Backend | CAENBackend | Sin comunicación con el módulo HV → detector sin polarización |
| Canal/Sistema | HVChannel, HVSystem | Sin control de ramping → transitorios que pueden dañar el PMT |
| Control | HVMonitor, HVWatchdog | Sin detección de anomalías → deriva de ganancia no detectada |
| Operación | HVRunner | Sin persistencia de estado → pérdida de configuración calibrada |

Consulta [THEORY.md](THEORY.md) para la física del PMT y la justificación cuantitativa de los umbrales de protección.

---

## Diagrama de Arquitectura de Capas

```
╔══════════════════════════════════════════════════════════════╗
║                      CAPA DE OPERACIÓN                       ║
║  ┌──────────────────────────────────────────────────────┐   ║
║  │               HVRunner / hv_run.py                   │   ║
║  │   Orquestación · Logging CSV · Persistencia          │   ║
║  └───────────────────────┬──────────────────────────────┘   ║
╚══════════════════════════╪═════════════════════════════════════╝
                           │ coordina
╔══════════════════════════╪═════════════════════════════════════╗
║                   CAPA DE CONTROL                             ║
║  ┌────────────────┐      │      ┌─────────────────────────┐  ║
║  │   HVMonitor    │◄─────┤─────►│      HVWatchdog          │  ║
║  │  (thread)      │      │      │  (thread + process)      │  ║
║  │                │      │      │                          │  ║
║  │  Muestreo      │      │      │  FSM · dV/dt · Energía   │  ║
║  │  batch 1 Hz    │      │      │  Corriente · Drift        │  ║
║  │  + Alarmas     │      │      │  Deadman · VMON≈0        │  ║
║  └────────┬───────┘      │      └───────────┬─────────────┘  ║
║           │              │                  │                 ║
║  ┌────────▼──────────────▼──────────────────▼─────────────┐  ║
║  │                     HVSystem                            │  ║
║  │   turn_on_all · turn_off_all · kill_all · restore_all  │  ║
║  │                                                         │  ║
║  │        ┌─────────────┐    ┌─────────────┐              │  ║
║  │        │  HVChannel  │    │  HVChannel  │  …           │  ║
║  │        │  CH:0       │    │  CH:1       │              │  ║
║  │        │  FSM + cache│    │  FSM + cache│              │  ║
║  └────────┴──────┬──────┴────┴──────┬──────┴──────────────┘  ║
╚═══════════════════╪══════════════════╪═════════════════════════╝
                    │ abstracción      │
╔═══════════════════╪══════════════════╪═════════════════════════╗
║                   CAPA DE HARDWARE                            ║
║  ┌────────────────▼──────────────────▼──────────────────┐    ║
║  │                  HVBackend (ABC)                       │    ║
║  │            ┌─────────────┐  ┌──────────────┐          │    ║
║  │            │ CAENBackend │  │ MockBackend  │           │    ║
║  │            │ VISA/USB    │  │ (simulación) │           │    ║
║  │            └──────┬──────┘  └──────────────┘          │    ║
║  └─────────────────  │  ──────────────────────────────────┘    ║
║                      │ ASRL/dev/ttyACM0::INSTR                  ║
║              ┌───────▼──────────┐                              ║
║              │  CAEN DT5533EN   │  ← Hardware físico           ║
║              │  (USB–UART)      │                              ║
║              └───────┬──────────┘                              ║
║                      │  SHV cable HV                           ║
║              ┌───────▼──────────┐                              ║
║              │  PMT Hamamatsu   │                              ║
║              │  R14374          │                              ║
║              └──────────────────┘                              ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Descripción de Componentes

### 1. HVRunner (`hv_run.py`)

Orquestador principal del sistema. Es el punto de entrada que coordina el ciclo de vida completo.

**Responsabilidades:**
- Conexión al backend con reintentos automáticos
- Instanciación secuencial de todos los subsistemas
- Gestión de señales POSIX (`SIGINT`, `SIGTERM`) para shutdown graceful
- Loop principal de logging CSV rotativo diario
- Persistencia de estado en disco cada 30 s

**Flujo de inicialización:**
```
connect_backend() → crear HVChannel(es) → crear AlarmManager
    → crear HVMonitor → start_monitor() → start_watchdog()
    → power_up() → run_loop()
```

---

### 2. HVSystem (`hv/system.py`)

Administrador de múltiples canales HV. Abstrae operaciones de grupo y evita que el Runner interactúe directamente con canales individuales.

**Operaciones principales:**

| Método              | Descripción                                        |
|---------------------|----------------------------------------------------|
| `arm_all()`         | Valida y configura todos los canales en hardware   |
| `turn_on_all()`     | Enciende canales en secuencia (para si alguno falla)|
| `turn_off_all()`    | Apagado ordenado de todos los canales              |
| `kill_all()`        | Apagado de emergencia (POWERDOWN KILL)             |
| `wait_all_until_on()` | Espera a que todos alcancen VSET               |
| `update_all_states()` | Sincroniza FSM software con estado hardware     |
| `restore_all()`     | Restaura canales desde datos persistidos           |

---

### 3. HVChannel (`hv/channel.py`)

Representa y controla un canal HV individual. Encapsula la FSM de estados, la validación de seguridad y el acceso al backend a través de una caché.

**Atributos clave:**

| Atributo        | Tipo    | Descripción                              |
|-----------------|---------|------------------------------------------|
| `ch`            | `int`   | Número de canal (0–3)                    |
| `vset`          | `float` | Voltaje objetivo (V)                     |
| `iset`          | `float` | Límite de corriente (A)                  |
| `rup`           | `int`   | Velocidad de rampa ascendente (V/s)      |
| `state`         | `HVState` | Estado actual (FSM)                   |
| `_vmon_cache`   | `float` | Último VMON leído (V)                    |
| `_imon_cache`   | `float` | Último IMON leído (A)                    |
| `_last_update`  | `float` | Timestamp monotónico de última lectura   |

---

### 4. HVMonitor (`hv/monitor.py`)

Thread dedicado a la adquisición periódica (1 Hz por defecto) de todos los canales en modo batch. Alimenta la caché de canales y dispara la evaluación de alarmas.

**Operación por ciclo (`_sample_all`):**
1. Lectura batch atómica: `get_all_vmon()`, `get_all_imon()`, `get_all_status()`
2. Actualización de caché en cada `HVChannel`
3. Actualización de `_last_update` (heartbeat para el Watchdog)
4. Evaluación de las tres alarmas de software mediante `AlarmManager`
5. Logging de alarmas activas

---

### 5. HVWatchdog (`hv/watchdog.py`)

Sistema de vigilancia multinivel que opera en un thread dedicado con un proceso hijo para la función de deadman (GIL-safe). Se ejecuta cada 0.5 s.

**Protecciones implementadas (en orden de prioridad):**

| Prioridad | Protección              | Parámetro clave                   | Acción        |
|-----------|-------------------------|-----------------------------------|---------------|
| 1         | Monitor silencioso      | `max_silence = 10 s`              | FAULT + apagado |
| 2         | FSM invariant           | Estado SW ≠ Estado HW             | FAULT + apagado |
| 3         | VMON ≈ 0 persistente    | `< 10 V` durante `> 2 s`         | FAULT + apagado |
| 4         | Drift VMON vs VSET      | `> 10 %` durante `> 3 s`         | FAULT + apagado |
| 5         | Sobrecorriente SW       | `I > ISET × 1.2`                 | FAULT + apagado |
| 6         | dV/dt excesivo          | `> 200 V/s`                      | FAULT + apagado |
| 7         | Energía acumulada       | `> 0.6 J` en ventana de `5 s`    | FAULT + apagado |
| 8         | Deadman (proceso hijo)  | Sin heartbeat por `1.5 s`        | `SIGTERM` al padre |

---

### 6. AlarmManager y Alarmas (`hv/alarm_manager.py`, `hv/alarms/`)

Evaluador no intervencionista: evalúa alarmas de tendencia y genera reportes. **No apaga canales por sí solo**; es responsabilidad del Watchdog o del operador.

**Alarmas disponibles:**

| Clase                  | Nombre           | Tipo      | Descripción                                         |
|------------------------|------------------|-----------|-----------------------------------------------------|
| `LeakageAlarm`         | `LEAKAGE`        | WARNING   | Detección de pendiente positiva sostenida en IMON   |
| `VoltageMismatchAlarm` | `VSET_MISMATCH`  | CRITICAL  | \|VMON − VSET\| > 5 V durante ≥ 6 muestras         |
| `VoltageStabilityAlarm`| `VOLTAGE_STABILITY`| WARNING | σ(VMON) > 10 V en ventana de 20 muestras           |

---

### 7. HVBackend (`hv/backend/`)

Interfaz abstracta (`HVBackend`) que desacopla la lógica de negocio del hardware físico.

| Implementación   | Uso                   | Comunicación        |
|------------------|-----------------------|---------------------|
| `CAENBackend`    | Hardware real         | VISA / USB–UART     |
| `MockBackend`    | Pruebas / simulación  | Simulación en RAM   |

**Protocolo CAEN (ASCII):**
```
SET: $CMD:SET,CH:<n>,PAR:<param>,VAL:<valor>  → OK
GET: $CMD:MON,CH:<n>,PAR:<param>              → VAL:<valor>;...
```

---

### 8. HVStateManager (`hv/state_manager.py`)

Persiste el estado de los canales en disco (`hv_state.json`) cada 30 s para recuperación ante reinicios inesperados. Permite restaurar VSET, ISET, ramp y último VMON/IMON conocidos.

---

## Máquina de Estados del Canal HV

```
                   arm()
    ┌──────┐    ──────────►  ┌────────┐
    │ OFF  │                 │ ARMED  │
    └──────┘    ◄──────────  └───┬────┘
         ▲       HVSafetyError   │ backend.on()
         │                       ▼
         │              ┌─────────────┐
         │  turn_off()  │ RAMPING_UP  │
         │  ◄───────────│  (ramping)  │
         │              └──────┬──────┘
         │                     │ VSET alcanzado
         │                     ▼
         │  turn_off()  ┌─────────┐
         │  ◄───────────│   ON    │◄─────────────────┐
         │              └─────────┘                   │
         │                                            │
         │  ┌──────────────────────────────────────┐  │
         │  │              FAULT                   │  │
         │  │  (kill, interlock, watchdog trigger) │──┘
         │  └──────────────────────────────────────┘
         │
    ┌───────┐
    │ ERROR │  (timeout de rampa, excepción no manejada)
    └───────┘
```

**Transiciones válidas:**

| Desde        | Evento                           | Hacia        |
|--------------|----------------------------------|--------------|
| `OFF`        | `arm()` exitoso                  | `ARMED`      |
| `OFF`        | `arm()` → `HVSafetyError`        | `FAULT`      |
| `ARMED`      | `backend.on()` enviado           | `RAMPING_UP` |
| `RAMPING_UP` | VSET alcanzado                   | `ON`         |
| `RAMPING_UP` | Timeout de rampa                 | `ERROR`      |
| `ON`         | `turn_off()`                     | `OFF`        |
| `ON`         | Watchdog fault                   | `FAULT`      |
| `ON`         | Kill/Interlock hardware          | `FAULT`      |
| `FAULT`      | —                                | (terminal)   |
| `ERROR`      | —                                | (terminal)   |

---

## Flujo de Datos entre Componentes

```
Hardware CAEN
     │  (VISA/USB-UART, 1 Hz)
     ▼
CAENBackend
  get_all_vmon() ──────────────────────────────────────►  HVMonitor
  get_all_imon()                                              │
  get_all_status()                                           │ update_cache(v,i)
     │                                                        │ _last_status
     │                                                        │ _last_update (heartbeat)
     │                                                        ▼
     │                                                  HVChannel._vmon_cache
     │                                                  HVChannel._imon_cache
     │                                                        │
     │                                              (cada 0.5 s)
     │                                                        │
     │                                                        ▼
     │                                                  HVWatchdog
     │                                                  _check_channel()
     │                                                        │
     │                                             ┌──────────┴───────────┐
     │                                             │                      │
     │                                             ▼                      ▼
     │                                      ch.turn_off()           logger.critical()
     │                                      (auto_shutdown)
     │
     ▼
HVRunner (loop principal, cada 10 s)
  csv_logger.log(ch, v, i, state)   → logs/hv_log_YYYYMMDD.csv
  state_mgr.save(channels)          → hv_state.json
```

---

## Modelo de Capas de Seguridad

```
┌──────────────────────────────────────────────────────────┐
│                   CAPA OPERACIONAL                        │
│  Formación del operador · Procedimientos documentados     │
│  Revisión visual de logs · Alarmas en consola            │
├──────────────────────────────────────────────────────────┤
│               CAPA DE MONITORIZACIÓN (SW)                │
│  AlarmManager: LEAKAGE · VSET_MISMATCH · VOLT_STABILITY  │
│  HVMonitor: lecturas batch 1 Hz · heartbeat watchdog     │
├──────────────────────────────────────────────────────────┤
│               CAPA DE CONTROL (SW)                        │
│  HVWatchdog: 8 protecciones · deadman multiproceso       │
│  HVChannel FSM: transiciones válidas · validación previa  │
│  HVLimits: V_MAX, V_SAFE, I_MAX, P_MAX (check_user_params)|
├──────────────────────────────────────────────────────────┤
│               CAPA DE FIRMWARE / HARDWARE                 │
│  CAEN DT5533EN: OVC hardware · MAXV · KILL · INTERLOCK   │
│  PMT Hamamatsu R14374: límites físicos intrínseos         │
└──────────────────────────────────────────────────────────┘
```

---

## Decisiones Arquitectónicas

### 1. Separación Backend / Lógica

El `HVBackend` (ABC) desacopla completamente la comunicación hardware de la lógica de control. Esto permite:
- Intercambiar `CAENBackend` por `MockBackend` sin modificar ningún otro módulo.
- Escribir tests unitarios sin hardware físico.
- Migrar a otro protocolo o fabricante cambiando únicamente la implementación del backend.

### 2. Monitor y Watchdog en Threads Separados

El `HVMonitor` (lectura de datos) y el `HVWatchdog` (verificación de seguridad) operan en threads independientes con períodos distintos (1 Hz y 2 Hz respectivamente). Esto garantiza:
- El watchdog no se bloquea si el monitor está procesando una muestra.
- El monitor no se bloquea si el watchdog ejecuta un shutdown.
- Ambos pueden ser detenidos independientemente en el shutdown graceful.

### 3. Deadman como Proceso Independiente (GIL-safe)

La función de deadman usa `multiprocessing.Process` en lugar de un thread para garantizar que el GIL de Python no pueda bloquear la detección de fallos. Si el proceso principal queda bloqueado en operaciones síncronas (E/S, espera de hardware), el proceso hijo envía `SIGTERM` después del timeout configurado.

### 4. AlarmManager no Intervencionista

Las alarmas (`LeakageAlarm`, `VoltageMismatchAlarm`, `VoltageStabilityAlarm`) reportan condiciones anómalas pero **no ejecutan apagados**. Esta decisión evita que una falsa alarma provoque un shutdown innecesario. El operador o el Watchdog deciden la acción correctiva, manteniendo el principio de separación de responsabilidades.

### 5. Caché de Lecturas con Timestamp

Cada canal mantiene un caché de la última lectura (`_vmon_cache`, `_imon_cache`) junto con el timestamp monotónico `_last_update`. El Watchdog usa este timestamp para detectar si el Monitor ha dejado de funcionar (detección de silencio). El caché también evita saturar el bus USB/UART con lecturas simultáneas desde múltiples threads.

### 6. Persistencia de Estado

El `HVStateManager` guarda el estado operativo en `hv_state.json` cada 30 s. Ante un reinicio inesperado (corte de corriente, crash), el sistema puede restaurar los parámetros previos sin intervención manual y sin requerir que el operador recuerde los valores configurados.

---

## Estructura de Archivos

```
ConfCAENmodule/
├── hv_run.py               # Punto de entrada (hardware real)
├── hv_run_mock.py          # Punto de entrada (simulación)
├── hv/
│   ├── __init__.py
│   ├── safety.py           # HVLimits, check_user_params
│   ├── state.py            # Enum HVState
│   ├── channel.py          # HVChannel (FSM + cache)
│   ├── system.py           # HVSystem (operaciones de grupo)
│   ├── monitor.py          # HVMonitor (thread de muestreo)
│   ├── watchdog.py         # HVWatchdog (vigilancia multinivel)
│   ├── alarm_manager.py    # AlarmManager
│   ├── logger.py           # setup_logger()
│   ├── state_manager.py    # HVStateManager (persistencia)
│   ├── alarms/
│   │   ├── base.py         # BaseAlarm, AlarmResult, AlarmLevel
│   │   ├── leakage.py      # LeakageAlarm
│   │   ├── mismatch.py     # VoltageMismatchAlarm
│   │   └── voltage_stability.py  # VoltageStabilityAlarm
│   └── backend/
│       ├── base.py         # HVBackend (ABC)
│       ├── caen.py         # CAENBackend (VISA/USB)
│       └── mock.py         # MockBackend (simulación)
├── architecture.md         # Este documento
├── SAFETY.md               # Documentación de seguridad
├── HARDWARE.md             # Documentación de hardware
└── README.md               # Guía de inicio rápido
```

---

## Referencias Cruzadas

- Para la física del PMT y justificación de umbrales → [THEORY.md](THEORY.md)
- Para el sistema de detección completo (CAEN → PMT → Red Pitaya) → [INTEGRATION.md](INTEGRATION.md)
- Para detalles de cada protección de seguridad → [SAFETY.md](SAFETY.md)
- Para especificaciones del hardware controlado → [HARDWARE.md](HARDWARE.md)
- Para instalación y uso rápido → [README.md](README.md)

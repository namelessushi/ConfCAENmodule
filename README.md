# ConfCAENmodule — High-Voltage Control for PMT-Based Particle Detectors

Sistema de control de alto voltaje (HV) para fotomultiplicadores (PMT) **Hamamatsu R14374** operados en experimentos de física de partículas. Implementa el control preciso del voltaje de polarización del PMT mediante un módulo **CAEN DT5533EN**, garantizando la ganancia estable y reproducible que todo experimento basado en centelleo requiere.

> **Contexto físico**: El rendimiento de un PMT —su ganancia, linealidad y ruido— depende directamente del voltaje de alimentación aplicado entre fotocátodo y ánodo. Este módulo software proporciona el control de esa variable física con la precisión, seguridad y trazabilidad necesarias para experimentos de laboratorio.

---

## 🔬 Rol en el pipeline de detección

```
Partícula / fotón
        │
        ▼
┌───────────────┐
│  Centelleador  │  (conversión energía → fotones ópticos)
└───────┬───────┘
        │ fotones UV-Vis
        ▼
┌───────────────┐
│  PMT R14374   │  ← voltaje de polarización controlado por este módulo
│  Hamamatsu    │     (fotoefecto + multiplicación en dinodos)
└───────┬───────┘
        │ pulso de carga
        ▼
┌───────────────────┐
│  Red Pitaya DAQ   │  (adquisición y digitalización — proyecto externo)
└───────┬───────────┘
        │ datos digitales
        ▼
     Análisis
```

La adquisición y digitalización de las señales del PMT es responsabilidad del sistema **Red Pitaya**, desarrollado de forma independiente por un colega de laboratorio. Este repositorio se centra exclusivamente en el control del HV de polarización del detector. Consulta [INTEGRATION.md](INTEGRATION.md) para más detalles sobre la arquitectura completa.

---

## ✨ Características principales

| Feature | Descripción |
|---|---|
| **Control seguro de HV** | Ramping controlado con límites de corriente y voltaje por canal |
| **Monitor batch con caché** | Lectura periódica de `Vmon`/`Imon` compartida entre componentes |
| **Sistema de alarmas** | Detección de fuga de corriente, desviación de voltaje e inestabilidad |
| **Watchdog de seguridad** | Apagado automático ante fallos detectados por el monitor |
| **Deadman multiproceso** | Timeout de seguridad por inactividad del proceso de control |
| **Logging CSV diario rotativo** | Registro automático por día en `logs/` con headers automáticos |
| **Persistencia de estado** | Guarda y restaura el estado del sistema en `hv_state.json` |
| **Modo mock** | Backend simulado para desarrollo y pruebas sin hardware |

---

## ⚡ Por qué importa el control preciso del HV

La ganancia de un PMT sigue una ley potencial respecto al voltaje de alimentación:

```
G ∝ V^n
```

donde `n` es típicamente 6–8 para el Hamamatsu R14374. Esto significa que una variación de solo **1 % en el voltaje** produce una variación de **6–8 % en la ganancia**, afectando directamente la calibración y resolución energética del detector. Por ello este módulo:

- Implementa ramping controlado (25 V/s) para evitar sobretensiones transitorias.
- Monitorea en tiempo real la desviación entre voltaje solicitado (VSET) y medido (VMON).
- Detecta inestabilidades que degradarían la resolución energética del experimento.

Consulta [THEORY.md](THEORY.md) para la física del PMT y la justificación de los parámetros operativos.

---

## 🖥️ Requisitos del sistema

- **Python** 3.8 o superior
- **Sistema operativo**: Linux (recomendado), macOS o Windows
- **Hardware** (modo real): Módulo CAEN DT55XXE conectado por USB/Serial (`/dev/ttyACM0`)
- **Dependencias Python**:
  - [`pyvisa`](https://pyvisa.readthedocs.io/) — comunicación con el módulo CAEN
  - Biblioteca estándar de Python (`csv`, `threading`, `signal`, `logging`, `pathlib`)

---

## 📦 Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/namelessushi/ConfCAENmodule.git
cd ConfCAENmodule

# 2. (Opcional) Crear y activar entorno virtual
python -m venv venv
source venv/bin/activate      # Linux / macOS
# venv\Scripts\activate       # Windows

# 3. Instalar dependencias
pip install pyvisa
```

Para el modo real también se requiere el driver VISA compatible con CAEN (NI-VISA o similar).

---

## 🗂️ Estructura del proyecto

```
ConfCAENmodule/
│
├── hv_run.py             # Entrypoint — modo real (hardware CAEN)
├── hv_run_mock.py        # Entrypoint — modo mock (sin hardware)
│
├── hv/                   # Paquete principal del sistema HV
│   ├── __init__.py
│   ├── channel.py        # Abstracción de canal HV (vset, iset, turn_on/off)
│   ├── system.py         # Gestión del conjunto de canales (HVSystem)
│   ├── monitor.py        # Monitor batch con caché (HVMonitor)
│   ├── watchdog.py       # Watchdog de seguridad (HVWatchdog)
│   ├── state.py          # Definición de estados de canal
│   ├── state_manager.py  # Persistencia de estado en JSON
│   ├── safety.py         # Límites físicos del PMT y lógica de seguridad
│   ├── logger.py         # Configuración del logger estándar
│   ├── alarm_manager.py  # Orquestador de alarmas
│   │
│   ├── alarms/           # Módulos de alarma individuales
│   │   ├── __init__.py
│   │   ├── base.py               # Clase base Alarm
│   │   ├── leakage.py            # Alarma de fuga de corriente
│   │   ├── mismatch.py           # Alarma de desviación Vmon vs Vset
│   │   └── voltage_stability.py  # Alarma de inestabilidad de voltaje
│   │
│   └── backend/          # Interfaces de hardware
│       ├── __init__.py
│       ├── base.py       # Clase base abstracta del backend
│       ├── caen.py       # Backend real (comunicación CAEN via pyvisa)
│       └── mock.py       # Backend simulado para pruebas
│
├── THEORY.md             # Física del PMT: ganancia, ruido y rol del HV
├── INTEGRATION.md        # Sistema completo: CAEN → PMT → Red Pitaya DAQ
├── architecture.md       # Diagrama de arquitectura del software
├── HARDWARE.md           # Especificaciones del PMT y del módulo CAEN
├── SAFETY.md             # Protecciones de seguridad del detector
└── .gitignore
```

---

## 🚀 Guía de uso

### Modo real (hardware CAEN)

Asegúrate de que el módulo CAEN esté conectado y el recurso VISA esté correctamente configurado en `CONFIG` dentro de `hv_run.py`:

```python
CONFIG = {
    "resource": "ASRL/dev/ttyACM0::INSTR",   # ← Ajustar al puerto real
    "channels": [
        {"ch": 0, "vset": 1350.0, "iset": 1e-4, "rup": 25}
    ],
    ...
}
```

Luego ejecutar:

```bash
python hv_run.py
```

### Modo mock (sin hardware)

Para desarrollo, pruebas o verificación del software sin conectar el módulo CAEN:

```bash
python hv_run_mock.py
```

El modo mock utiliza `MockCAENBackend` que simula respuestas del hardware. Los logs se guardan en `logs_mock/`.

Para detener el sistema en cualquier modo: **`Ctrl+C`** (SIGINT) o `kill <PID>` (SIGTERM). El sistema ejecuta un shutdown graceful automático.

---

## ⚙️ Configuración del sistema

Los parámetros de operación se configuran en el diccionario `CONFIG` en `hv_run.py` (real) o `hv_run_mock.py` (mock):

| Parámetro | Descripción | Ejemplo |
|---|---|---|
| `resource` | Recurso VISA del módulo CAEN | `"ASRL/dev/ttyACM0::INSTR"` |
| `connection_retry` | Tiempo (s) entre reintentos de conexión | `30` |
| `connection_timeout` | Timeout de conexión VISA (ms) | `5000` |
| `deadman_timeout` | Timeout del deadman (s) | `60` |
| `channels[].ch` | Número de canal del módulo | `0` |
| `channels[].vset` | Voltaje objetivo (V) | `1350.0` |
| `channels[].iset` | Límite de corriente (A) | `1e-4` |
| `channels[].rup` | Velocidad de ramping (V/s) | `25` |
| `watchdog.check_period` | Período del watchdog (s) | `0.5` |
| `watchdog.auto_shutdown` | Apagado automático en fallo | `True` |
| `monitor.period` | Período de muestreo del monitor (s) | `1.0` |
| `log_interval` | Intervalo de escritura CSV (s) | `10.0` |
| `log_directory` | Directorio de logs CSV | `"logs"` |

---

## 🔒 Notas de seguridad del detector

> ⚠️ **Este sistema controla alto voltaje (HV). Leer `SAFETY.md` y `HARDWARE.md` antes de operar.**

El control seguro del HV no es solo una cuestión de protección del personal, sino de **integridad del detector**. Un transitorio de voltaje o una sobrecorriente pueden dañar irreversiblemente la cadena de dinodos del PMT:

- El **watchdog** monitorea continuamente el estado del sistema; ante cualquier fallo crítico ejecuta `backend.shutdown_all()` para apagar todos los canales.
- El **deadman** detecta inactividad del proceso principal y también dispara el apagado.
- Las **alarmas** cubren: fuga de corriente, desviación Vmon vs Vset, e inestabilidad de voltaje.
- El **shutdown graceful** (Ctrl+C / SIGTERM) detiene el monitor, el watchdog y apaga los canales en orden correcto antes de cerrar la conexión.
- Nunca modificar `iset` por encima del límite especificado para el PMT conectado.

---

## 📊 Ejemplo de salida esperada

```
[INFO ] HVRunner inicializado
[INFO ] ============================================================
[INFO ] INICIALIZANDO SISTEMA HV
[INFO ] ============================================================
[INFO ] Intentando conectar al módulo CAEN...
[INFO ] ✅ Conexión CAEN establecida
[INFO ]    ✓ CH0 creado (VSET=1350.0V, ISET=0.0001A)
[INFO ]    ✓ Alarmas inicializadas
[INFO ]    ✓ Monitor creado
[INFO ] ✅ Sistema inicializado correctamente

[INFO ] ============================================================
[INFO ] POWER-UP: Encendiendo canales
[INFO ] ============================================================
[INFO ] CH0: VMON=0.00V, IMON=0.000e+00A
[INFO ] CH0: Iniciando encendido...
[INFO ] ✅ CH0 encendido correctamente
[INFO ] ✅ Todos los canales encendidos

[INFO ] ============================================================
[INFO ] LOOP PRINCIPAL: Monitoreo activo
[INFO ] ============================================================
```

Los registros CSV se almacenan en `logs/hv_log_YYYYMMDD.csv` con el formato:

```
Timestamp,Channel,Voltage_V,Current_A,Status
2024-01-15T10:30:00.123456,0,1350.12,8.500e-08,ON
```

---

## 📄 Licencia

Este proyecto es de uso interno para experimentos con detectores de partículas. Consultar con el autor para condiciones de uso y redistribución.

---

## 📚 Documentación adicional

| Documento | Contenido |
|---|---|
| [THEORY.md](THEORY.md) | Física del PMT: fotoefecto, multiplicación en dinodos, curva de ganancia G(V) |
| [INTEGRATION.md](INTEGRATION.md) | Arquitectura del sistema completo y relación con Red Pitaya DAQ |
| [HARDWARE.md](HARDWARE.md) | Especificaciones del PMT Hamamatsu R14374 y del módulo CAEN DT5533EN |
| [SAFETY.md](SAFETY.md) | Protecciones software y hardware para la integridad del detector |
| [architecture.md](architecture.md) | Diagrama de capas y descripción de componentes del software |

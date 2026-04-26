# Documentación de Hardware — ConfCAENmodule

## Resumen

Este documento describe el sistema de detección desde el punto de vista físico-instrumental: primero el detector principal (PMT Hamamatsu R14374) y su base divisora de tensión, y a continuación el instrumento de control (CAEN DT5533EN) que suministra el alto voltaje de polarización. Se incluyen el esquema de conexión físico, el protocolo de comunicación y las consideraciones de integración con Raspberry Pi.

---

## Detector Principal: Fotomultiplicador (PMT) Hamamatsu R14374

El PMT es el componente central del sistema de detección. Convierte fotones en señales eléctricas amplificadas mediante el efecto fotoeléctrico y la multiplicación secundaria en su cadena de dinodos. Su rendimiento depende directamente del voltaje de polarización aplicado (ver [THEORY.md](THEORY.md) para los fundamentos físicos).

### Especificación Eléctrica

| Parámetro                  | Valor                    |
|----------------------------|--------------------------|
| Fabricante                 | Hamamatsu Photonics      |
| Modelo                     | R14374                   |
| Tipo                       | PMT de ventana lateral   |
| Tensión de alimentación    | 700 – 1500 V (positiva)  |
| Tensión máxima absoluta    | 1500 V                   |
| Corriente de oscuridad     | < 1 nA (típica)          |
| Corriente de señal máxima  | 100 μA                   |
| Sensibilidad espectral     | 185 – 650 nm             |
| Pico de sensibilidad       | ~420 nm                  |
| Ganancia típica            | 1×10⁶ a 1000 V          |

### Parámetros Operativos Nominales (en ConfCAENmodule)

| Parámetro | Valor configurado | Justificación                     |
|-----------|-------------------|-----------------------------------|
| VSET      | 1350 V            | Ganancia óptima para la aplicación|
| ISET      | 100 μA            | Límite máximo del PMT             |
| RUP       | 25 V/s            | Rampa conservadora para el PMT    |

> **ADVERTENCIA**: No superar 1475 V (V_SAFE). El software lo impide mediante `check_user_params()`, pero un fallo de software no protege contra configuraciones manuales directas en el hardware.

---

## Instrumento de Control HV: CAEN DT5533EN

El módulo CAEN DT5533EN es la fuente de alto voltaje que polariza el PMT. Actúa como **instrumento de control**: no es el detector en sí, sino el elemento que establece las condiciones eléctricas bajo las cuales opera el detector. Su precisión (< 0.1 V en voltaje, < 5 nA en corriente) y su bajo ripple (< 5 mV) son requisitos del experimento, no meras especificaciones de hardware.

### Especificación General

| Parámetro              | Valor                              |
|------------------------|------------------------------------|
| Fabricante             | CAEN S.p.A. (Italia)               |
| Modelo                 | DT5533EN                           |
| Tipo                   | Desktop HV Power Supply, 4 canales |
| Tensión de salida      | 0 – 4000 V (positiva)              |
| Corriente máxima       | 3 mA por canal                     |
| Potencia máxima/canal  | 4 W                                |
| Resolución voltaje     | < 0.1 V                            |
| Resolución corriente   | < 5 nA                             |
| Ripple de salida       | < 5 mV pico a pico                 |
| Interfaz               | USB (CDC/UART virtual)             |
| Alimentación           | 100–240 V AC, 50/60 Hz             |
| Dimensiones            | 320 × 235 × 50 mm (unidad desktop) |

### Canales

El módulo dispone de **4 canales HV independientes** numerados del 0 al 3, cada uno con:
- Conector de salida: **SHV** (Safe High Voltage, coaxial)
- Rampa configurable de subida (`RUP`) y bajada (`RDOWN`) en V/s
- Límite de corriente por canal (`ISET`) configurable
- Protecciones de hardware: OVC (overcurrent), MAXV, KILL, INTERLOCK

### Parámetros de Status por Canal (registro `STAT`)

El módulo expone el estado de cada canal mediante un valor entero donde cada bit tiene un significado:

| Bit | Máscara | Nombre     | Descripción                                  |
|-----|---------|------------|----------------------------------------------|
| 0   | 0x0001  | `on`       | Canal encendido y regulando                  |
| 1   | 0x0002  | `ramping`  | Rampa de subida activa                       |
| 2   | 0x0004  | `ramping`  | Rampa de bajada activa                       |
| 3   | 0x0008  | `ovc`      | Overcurrent: corriente > ISET hardware       |
| 6   | 0x0040  | `maxv`     | Voltaje supera el límite máximo configurado  |
| 11  | 0x0800  | `kill`     | Canal apagado por señal KILL externa         |
| 12  | 0x1000  | `interlock`| Interlock externo activado                   |

---

## Protocolo de Comunicación

### Interfaz Física

El DT5533EN se comunica mediante **USB CDC** (Communications Device Class), que emula un puerto serie virtual. En Linux/Raspberry Pi aparece como `/dev/ttyACM0` (o `/dev/ttyACM1` si hay otros dispositivos).

| Parámetro         | Valor               |
|-------------------|---------------------|
| Velocidad         | 115200 baud (virtual USB CDC, no relevante) |
| Paridad           | Ninguna             |
| Bits de datos     | 8                   |
| Bits de parada    | 1                   |
| Control de flujo  | Ninguno             |
| Terminador TX     | `\n` (LF)           |
| Terminador RX     | `\n` (LF)           |
| Timeout           | 5000 ms (configurable) |
| Resource VISA     | `ASRL/dev/ttyACM0::INSTR` |

### Protocolo ASCII de Comandos

El módulo acepta comandos en formato ASCII con la estructura:

**Escritura (SET):**
```
$CMD:SET,CH:<canal>,PAR:<parámetro>,VAL:<valor>
```

**Lectura (MON):**
```
$CMD:MON,CH:<canal>,PAR:<parámetro>
```

**Respuesta exitosa SET:**
```
OK
```

**Respuesta exitosa MON:**
```
VAL:<valor>;[campos adicionales]
```

### Comandos Implementados

| Operación          | Comando                                    | Respuesta              |
|--------------------|--------------------------------------------|------------------------|
| Fijar voltaje      | `$CMD:SET,CH:0,PAR:VSET,VAL:1350.00`      | `OK`                   |
| Fijar corriente    | `$CMD:SET,CH:0,PAR:ISET,VAL:100.00`       | `OK` (valor en μA)     |
| Fijar rampa subida | `$CMD:SET,CH:0,PAR:RUP,VAL:25`            | `OK` (valor en V/s)    |
| Encender canal     | `$CMD:SET,CH:0,PAR:ON`                    | `OK`                   |
| Apagar canal       | `$CMD:SET,CH:0,PAR:OFF`                   | `OK`                   |
| Leer voltaje       | `$CMD:MON,CH:0,PAR:VMON`                  | `VAL:1350.12;...`      |
| Leer corriente     | `$CMD:MON,CH:0,PAR:IMON`                  | `VAL:85.43;...` (μA)   |
| Leer estado        | `$CMD:MON,CH:0,PAR:STAT`                  | `VAL:1;...` (bitmask)  |

> **Nota sobre unidades de corriente**: El módulo CAEN envía y recibe la corriente en **microamperios (μA)**. El `CAENBackend` convierte automáticamente a amperios internamente (`iset * 1e6` en escritura, `val * 1e-6` en lectura).

### Robustez de Comunicación

El `CAENBackend` implementa:
- **Reintentos automáticos**: hasta 3 intentos por comando, con pausa de 0.2 s entre reintentos.
- **Lock global (threading.Lock)**: todos los accesos al puerto son thread-safe.
- **Parser tolerante**: `_parse_val()` recupera el campo `VAL:` incluso si la respuesta contiene basura adicional.

---

## Esquema de Conexión Físico

```
┌─────────────────────────────────────────────────────────────────┐
│                      RASPBERRY PI 4 (o 3B+)                     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Software: hv_run.py + pyvisa + python3                  │   │
│  └───────────────────────────┬──────────────────────────────┘   │
│                              │ USB 2.0 (CDC)                    │
└──────────────────────────────┼──────────────────────────────────┘
                               │ Cable USB-A ↔ USB-B (o mini-USB)
                               │ /dev/ttyACM0
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│               CAEN DT5533EN  (4 canales HV)                      │
│                                                                   │
│  CH0 [SHV] ──────────────────────────────────────────────────┐  │
│  CH1 [SHV]  (no utilizado en configuración nominal)          │  │
│  CH2 [SHV]  (no utilizado en configuración nominal)          │  │
│  CH3 [SHV]  (no utilizado en configuración nominal)          │  │
│                                                               │  │
│  Alimentación: 220 V AC → fuente interna                     │  │
└───────────────────────────────────────────────────────────────┘  │
                               │ Cable SHV (HV)                    │
                               │ 50 Ω, blindado                    │
                               ▼
┌────────────────────────────────────────────────────────────────┐
│  Base del PMT / Divisor de tensión                             │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ SHV IN ─→ Red divisora de tensión (dinodos)          │      │
│  │                              │                        │      │
│  │                          [100 Ω]  ← resistencia de   │      │
│  │                              │     desacoplamiento    │      │
│  │                    Señal de ánodo                     │      │
│  └──────────────────────────────┬─────────────────────  ┘      │
│                                 │ Cable BNC (señal)             │
│                                 ▼                               │
│                    Sistema de adquisición de datos (DAQ)        │
└────────────────────────────────────────────────────────────────┘
```

### Notas sobre el Esquema de Conexión

- El cable HV (SHV) y el cable de señal (BNC) deben ser **físicamente separados** para minimizar el acoplamiento capacitivo.
- La resistencia de 100 Ω en serie con la señal del ánodo actúa como terminador y reduce el ruido inducido por HV.
- El blindaje del cable SHV debe conectarse a tierra en el lado del módulo CAEN, **no** en el lado del PMT, para evitar bucles de tierra.

---

## Conectores y Cables

### Conector SHV (Safe High Voltage)

El conector SHV es el estándar industrial para HV en detectores de física de partículas:

| Característica         | Valor                         |
|------------------------|-------------------------------|
| Tipo                   | SHV (IEC 61169-17)            |
| Impedancia             | 50 Ω                          |
| Tensión máxima         | 5000 V                        |
| Corriente máxima       | 2 A                           |
| Frecuencia             | DC – 500 MHz                  |
| Compatibilidad         | No compatible con BNC estándar|

> **ADVERTENCIA**: Los conectores SHV y BNC tienen geometría similar pero son eléctricamente incompatibles a alto voltaje. Nunca utilice adaptadores SHV→BNC en circuitos de HV.

### Cable SHV Recomendado

| Parámetro         | Especificación mínima          |
|-------------------|-------------------------------|
| Impedancia        | 50 Ω (RG-58 o equivalente)    |
| Blindaje          | Doble malla trenzada           |
| Aislamiento       | Polietileno o PTFE (Teflón)   |
| Tensión máxima    | ≥ 5 kV                        |
| Longitud máxima   | < 5 m (para minimizar capacidad parásita) |

---

## Parámetros Eléctricos Nominales del Sistema

| Parámetro              | Valor nominal   | Límite software  | Límite hardware  |
|------------------------|-----------------|------------------|------------------|
| Voltaje de operación   | 1350 V          | 1475 V (V_SAFE)  | 1500 V (V_MAX)   |
| Corriente PMT          | ~85 μA (típica) | 100 μA (I_SAFE)  | OVC hardware CAEN |
| Potencia por canal     | ~0.115 W        | 3.4 W (P_SAFE_CH)| 4.0 W (P_MAX_CH) |
| Velocidad de rampa     | 25 V/s          | —                | —                |
| Tiempo de rampa 0→1350 V | ~54 s         | 60 s (timeout)   | —                |
| Ripple de HV           | < 5 mV p-p      | —                | < 5 mV p-p       |

> **Nota**: El disparo software de sobrecorriente se produce cuando `IMON > ISET × 1.2` (120 % del valor configurado), implementado en el `HVWatchdog`. La protección OVC del hardware CAEN actúa directamente sobre el límite `ISET` configurado en el módulo. Ambas protecciones son independientes y complementarias.

---

## Integración con Raspberry Pi

### Requisitos del Sistema Operativo

| Componente      | Versión mínima                         |
|-----------------|----------------------------------------|
| SO              | Raspberry Pi OS (Bullseye o superior)  |
| Python          | 3.8+                                   |
| pyvisa          | 1.13+                                  |
| pyvisa-py       | 0.6+ (backend puro Python)             |
| Permisos        | Usuario en grupo `dialout`             |

### Configuración de Acceso al Puerto

```bash
# Añadir usuario al grupo dialout (necesario para /dev/ttyACM0)
sudo usermod -a -G dialout $USER

# Verificar que el dispositivo CAEN aparece
ls -la /dev/ttyACM*

# Verificar con pyvisa
python3 -c "import pyvisa; rm = pyvisa.ResourceManager('@py'); print(rm.list_resources())"
```

### Resource String VISA

El `CAENBackend` usa el siguiente resource string para conectar al módulo:

```python
resource = "ASRL/dev/ttyACM0::INSTR"
```

Si el módulo aparece en un puerto diferente (e.g., `/dev/ttyACM1`), actualice la clave `"resource"` en `CONFIG` dentro de `hv_run.py`.

### Consumo de CPU en Raspberry Pi

| Componente        | CPU típica (Pi 4)   |
|-------------------|---------------------|
| HVMonitor (1 Hz)  | < 1 %               |
| HVWatchdog (2 Hz) | < 1 %               |
| HVRunner loop     | < 0.5 %             |
| Total sistema     | < 3 %               |

El sistema es compatible con Raspberry Pi 3B+ y superiores. Se recomienda Pi 4 para mayor estabilidad en operaciones de larga duración.

---

## Consideraciones de Ruido y Apantallamiento

### Fuentes de Ruido

| Fuente                  | Impacto                                  | Mitigación                              |
|-------------------------|------------------------------------------|-----------------------------------------|
| Ripple de la fuente HV  | Fluctuaciones de VMON (< 5 mV)           | Inherente al módulo CAEN; aceptable     |
| EMI del cable USB       | Interferencia en señal de ánodo del PMT  | Separación física de cables            |
| Bucles de tierra        | Ruido de baja frecuencia en señal        | Tierra en un solo punto (lado CAEN)    |
| Vibraciones mecánicas   | Microfónicos en el PMT                   | Montaje rígido de la base del PMT      |
| Luz ambiental           | Aumento de corriente de oscuridad        | Encapsulado opaco del PMT              |

### Buenas Prácticas de Instalación

1. **Separación de cables**: mantener el cable SHV (HV) y los cables de señal a una distancia mínima de 5 cm.
2. **Blindaje en un solo punto**: conectar el blindaje del cable SHV a tierra **únicamente** en el conector del módulo CAEN.
3. **Cable corto**: minimizar la longitud del cable SHV para reducir la capacidad parásita (< 5 m).
4. **Ventilación del módulo CAEN**: mantener al menos 5 cm de espacio alrededor del módulo para convección natural.
5. **Estabilización térmica**: esperar al menos 15 minutos después de encender el módulo CAEN antes de iniciar mediciones de precisión.

---

## Capacidades y Limitaciones del Hardware

### Capacidades

| Característica                   | Detalle                                      |
|----------------------------------|----------------------------------------------|
| Número de canales simultáneos    | Hasta 4 (DT5533EN)                           |
| Rango de voltaje ajustable       | 0 – 4000 V (limitado a 1500 V por software) |
| Resolución de voltaje            | < 0.1 V                                      |
| Resolución de corriente          | < 5 nA                                       |
| Comunicación multi-plataforma    | Linux, Windows, macOS (vía pyvisa)           |
| Operación no supervisada         | Sí, con watchdog y deadman activos           |

### Limitaciones

| Limitación                            | Descripción                                                     |
|---------------------------------------|-----------------------------------------------------------------|
| Sin aislamiento galvánico USB–HV      | El módulo no aísla eléctricamente el bus USB de los canales HV |
| Lectura no simultánea de canales      | Las lecturas batch se realizan en secuencia, no en paralelo     |
| Sin buffer de datos en el módulo      | No hay memoria de histórico en el CAEN; todo el logging es en software |
| IMON en μA con redondeo              | La resolución efectiva de corriente depende del ADC interno del CAEN |
| Sin salida de trigger externo         | El módulo no genera señales de trigger sincronizadas con los canales |
| Un dispositivo por USB               | Cada módulo requiere su propio puerto USB; no admite hubs en cadena |

---

## Referencias Cruzadas

- Física del PMT y justificación de parámetros operativos → [THEORY.md](THEORY.md)
- Sistema de detección completo e integración con Red Pitaya → [INTEGRATION.md](INTEGRATION.md)
- Límites de seguridad aplicados sobre este hardware → [SAFETY.md](SAFETY.md)
- Arquitectura del software de control → [architecture.md](architecture.md)
- Instalación y configuración inicial → [README.md](README.md)

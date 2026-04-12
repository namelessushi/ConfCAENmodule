# Documentación de Seguridad — ConfCAENmodule

## Resumen Ejecutivo

ConfCAENmodule implementa un sistema de seguridad de **cuatro capas independientes** para el control de alto voltaje (HV) sobre fotomultiplicadores (PMT) Hamamatsu R14374 mediante módulos CAEN DT5533EN. El diseño garantiza que un fallo en cualquier capa individual no comprometa la integridad del detector ni del personal.

Las protecciones cubren:
- Límites físicos absolutos definidos en software (`HVLimits`)
- Máquina de estados finita (FSM) con transiciones validadas
- Ocho protecciones dinámicas en el Watchdog industrial
- Tres alarmas de tendencia en el AlarmManager
- Proceso deadman GIL-safe independiente del intérprete Python
- Protecciones hardware intrínsecas del módulo CAEN

> **NOTA**: Este documento describe las protecciones implementadas en software. Consulte [HARDWARE.md](HARDWARE.md) para las protecciones hardware del módulo CAEN DT5533EN.

---

## Tabla de Niveles de Severidad

| Nivel      | Color | Acción automática              | Ejemplo                          |
|------------|-------|--------------------------------|----------------------------------|
| `OK`       | Verde | Ninguna                        | Operación nominal                |
| `WARNING`  | Amarillo | Registro en log             | Fuga de corriente detectada      |
| `CRITICAL` | Naranja | Registro en log + notificación | Mismatch de voltaje persistente |
| `FAULT`    | Rojo  | Apagado inmediato del canal    | Sobrecorriente · Deadman         |

---

## Capas de Seguridad

### Capa 1 — Hardware (CAEN DT5533EN)

Protecciones implementadas en el firmware del módulo CAEN, independientes del software de control:

| Protección    | Bit de estado | Descripción                                               |
|---------------|---------------|-----------------------------------------------------------|
| OVC (overcurrent) | Bit 3   | Desconexión por corriente > ISET configurado en hardware  |
| MAXV          | Bit 6         | Voltaje supera límite máximo configurado en el módulo     |
| KILL          | Bit 11        | Señal de apagado externo forzado                          |
| INTERLOCK     | Bit 12        | Interlock externo activado (señal física)                 |

Cuando cualquiera de estos bits está activo, `get_channel_status()` retorna el flag correspondiente en `True` y la FSM del canal transiciona a `FAULT`.

---

### Capa 2 — Software: Límites Físicos (`hv/safety.py`)

La clase `HVLimits` define constantes que se aplican **antes** de enviar cualquier comando al hardware. La función `check_user_params(vset, iset)` se llama en el constructor de `HVChannel` y lanza `HVSafetyError` si algún parámetro es inválido.

#### Parámetros del PMT Hamamatsu R14374

| Constante      | Valor    | Descripción                                       |
|----------------|----------|---------------------------------------------------|
| `V_MAX`        | 1500 V   | Voltaje máximo absoluto del PMT                   |
| `V_SAFE`       | 1475 V   | Límite operativo (derating 85 %)                  |
| `I_MAX`        | 100 μA   | Corriente máxima absoluta del PMT                 |
| `I_SAFE`       | 100 μA   | Límite operativo (sin margen adicional: el fabricante ya garantiza operación continua a este valor) |
| `I_TRIP_FACTOR`| 1.2      | Factor de disparo software (120 % de ISET)        |

#### Parámetros del módulo CAEN DT5533EN

| Constante       | Valor   | Descripción                                      |
|-----------------|---------|--------------------------------------------------|
| `P_MAX_CH`      | 4.0 W   | Potencia máxima por canal                        |
| `P_SAFE_CH`     | 3.4 W   | Límite operativo por canal (derating 85 %)       |
| `P_MAX_TOTAL`   | 16.0 W  | Potencia total teórica (4 canales × 4 W)         |
| `P_SAFE_TOTAL`  | 13.6 W  | Límite operativo total (derating 85 %)           |

#### Validaciones en `check_user_params(vset, iset)`

```
1. vset ∈ (0, V_MAX]       → HVSafetyError si excede
2. vset ≤ V_SAFE            → HVSafetyError si supera derating
3. iset ∈ (0, I_MAX]       → HVSafetyError si excede
4. iset ≤ I_SAFE            → HVSafetyError si supera derating
5. vset × iset ≤ P_MAX_CH  → HVSafetyError si excede potencia
6. vset × iset ≤ P_SAFE_CH → HVSafetyError si supera derating de potencia
```

---

### Capa 3 — Software: FSM con Transiciones Validadas (`hv/channel.py`)

El canal HV implementa una máquina de estados que previene operaciones en estados inválidos:

```
OFF ──arm()──► ARMED ──backend.on()──► RAMPING_UP ──VSET alcanzado──► ON
 ▲                                                                      │
 └──────────────────── turn_off() ◄────────────────────────────────────┘
                            │
                        (cualquier estado)
                            ▼
                          FAULT  (terminal)
                          ERROR  (terminal por timeout/excepción)
```

**Protecciones por estado:**

- **Desde `FAULT` o `ERROR`**: `turn_on()` retorna `False` inmediatamente sin enviar comandos.
- **Desde `ON` o `RAMPING_UP`**: `arm()` es ignorado con advertencia.
- **Antes de `arm()`**: `validate_before_on()` comprueba:
  - VMON < 10 V (canal realmente apagado)
  - IMON < min(ISET × 1.1, I_MAX) (sin corriente anómala)
  - Estado hardware sin KILL ni INTERLOCK activos
- **Durante `wait_until_vset()`**: vigilancia continua de KILL/INTERLOCK y V_MAX durante el ramping.

---

### Capa 4 — Software: Watchdog Industrial (`hv/watchdog.py`)

El `HVWatchdog` ejecuta un ciclo de verificación cada 0.5 s (configurable) en un thread dedicado. Cada protección que detecta una condición anómala llama a `_fault(ch, reason)`, que:

1. Registra el evento como `CRITICAL` en el log.
2. Establece `ch.state = HVState.FAULT`.
3. Ejecuta `ch.turn_off()` si `auto_shutdown=True`.

#### Protección 1 — Monitor silencioso (Deadman de canal)

```
Condición: time.monotonic() - ch._last_update > max_silence (10 s)
Acción:    FAULT + apagado del canal
Propósito: Detectar si el HVMonitor dejó de actualizar la caché
           (fallo del thread de monitoreo, bloqueo de E/S)
```

#### Protección 2 — FSM Invariant

```
Condición: ch.state == ON  AND  NOT (status["on"] OR status["ramping"])
Acción:    FAULT + apagado del canal
Propósito: Detectar discrepancia entre estado software y hardware
           (e.g., canal apagado por hardware sin que el software lo sepa)
```

#### Protección 3 — VMON ≈ 0 persistente

```
Parámetros: VMON_ZERO_THRESHOLD = 10 V,  VMON_ZERO_TIME = 2 s
Condición:  vmon < 10 V  durante  > 2 s  cuando estado == ON
Acción:     FAULT + apagado del canal
Propósito:  Detectar desconexión del HV o fallo del suministro
            mientras el software cree que el canal está activo
```

#### Protección 4 — Drift VMON vs VSET

```
Parámetros: DRIFT_REL_TOL = 10 %,  DRIFT_TIME = 3 s
Condición:  |vmon - vset| / vset > 0.10  durante  > 3 s  cuando estado == ON
Acción:     FAULT + apagado del canal
Propósito:  Detectar deriva sostenida de voltaje (no errores transitorios)
            sin confundir con ruido de corta duración
```

#### Protección 5 — Sobrecorriente Software

```
Parámetros: I_TRIP_FACTOR = 1.2
Condición:  imon > iset × 1.2  (en cualquier muestra)
Acción:     FAULT inmediato + apagado del canal
Propósito:  Capa software adicional al OVC hardware del CAEN,
            con mayor sensibilidad (120 % vs límite hardware)
```

#### Protección 6 — dV/dt excesivo

```
Parámetros: DV_DT_LIMIT = 200 V/s
Condición:  |Δvmon / Δt| > 200 V/s  entre dos muestras consecutivas
Acción:     FAULT + apagado del canal
Propósito:  Detectar cambios de voltaje anormalmente rápidos
            (fallo de regulación, ruido severo, cortocircuito transitorio)
```

#### Protección 7 — Energía acumulada

```
Parámetros: ENERGY_WINDOW = 5 s,  ENERGY_MAX = 0.6 J
Condición:  Σ(|v × i| × Δt) > 0.6 J  en ventana deslizante de 5 s
Acción:     FAULT + apagado del canal
Propósito:  Detectar disipación de energía excesiva sostenida
            incluso si corriente y voltaje individuales no superan límites
            (protección térmica indirecta del PMT y el módulo CAEN)
Nota:       La corriente se filtra a min(i, iset × 2) para evitar
            disparos espurios por picos de medición
```

#### Protección 8 — Deadman Multiproceso (GIL-safe)

```
Parámetros: DEADMAN_TIMEOUT = 3 × check_period (1.5 s por defecto)
Mecanismo:  Proceso hijo independiente (multiprocessing.Process)
            recibe heartbeats desde el thread del watchdog cada 0.5 s
Condición:  Sin heartbeat durante > 1.5 s
Acción:     os.kill(os.getppid(), SIGTERM)
Propósito:  Garantizar que el proceso principal sea terminado incluso
            si el GIL está bloqueado o el thread del watchdog no responde.
            Al ser un proceso separado, es inmune a deadlocks del GIL.
```

---

### Capa 5 — Software: Alarmas de Tendencia (`hv/alarm_manager.py`)

Las alarmas evalúan condiciones de degradación gradual que no justifican un apagado inmediato pero requieren atención del operador. **No ejecutan apagados**.

#### LeakageAlarm — Fuga de corriente

```
Nombre:     LEAKAGE
Nivel:      WARNING
Parámetros: window_size = 30 muestras,  slope_threshold = 1 nA/muestra
Condición:  Pendiente media de IMON > 1 nA por muestra en ventana de 30
Propósito:  Detección temprana de fuga en el PMT o en el cable HV
            antes de que dispare el OVC o la protección de sobrecorriente
Nota:       Se resetea durante ramping para evitar falsos positivos
```

#### VoltageMismatchAlarm — Discrepancia VMON/VSET

```
Nombre:     VSET_MISMATCH
Nivel:      CRITICAL
Parámetros: tolerance = 5 V,  max_samples = 6 muestras consecutivas
Condición:  |vmon - vset| > 5 V  durante ≥ 6 muestras consecutivas
Propósito:  Alertar de problemas de regulación de voltaje persistentes
            con mayor sensibilidad que el drift del watchdog (5 V vs 10 %)
Nota:       Complementa la Protección 4 del watchdog
```

#### VoltageStabilityAlarm — Inestabilidad de voltaje

```
Nombre:     VOLTAGE_STABILITY
Nivel:      WARNING
Parámetros: window = 20 muestras,  std_threshold = 10 V
Condición:  σ(vmon) > 10 V en ventana de 20 muestras
Propósito:  Detectar ruido o inestabilidad de la fuente antes de que
            produzca errores de medición en el detector
Nota:       Se resetea durante ramping
```

---

## Procedimiento ante Fallo Crítico

Cuando el Watchdog detecta un fault en un canal (Protecciones 1–8):

```
1. logger.critical("🔴 [CH<n>] FAULT: <razón>")
2. ch.state = HVState.FAULT
3. ch.turn_off()          ← backend.off(ch) vía VISA/USB
4. El canal queda en estado FAULT (terminal)
5. HVRunner detecta running=False o recibe SIGTERM (deadman)
6. Shutdown graceful:
   a. monitor.stop()
   b. watchdog.stop()
   c. ch.turn_off() para todos los canales restantes
   d. backend.close()
   e. csv_logger.close()
```

**El operador debe:**
1. Revisar el log de sistema (`logs/hv_log_YYYYMMDD.csv`) para identificar la causa.
2. Verificar físicamente el estado del PMT y del cable HV.
3. Comprobar el estado del módulo CAEN (LEDs de estado).
4. Resolver la causa raíz antes de reiniciar el sistema.
5. Al reiniciar, el `HVStateManager` restaura los parámetros previos automáticamente.

---

## Limitaciones Conocidas

| Limitación                          | Descripción                                                                 |
|-------------------------------------|-----------------------------------------------------------------------------|
| Sin redundancia de hardware         | Un único módulo CAEN controla todos los canales; su fallo afecta al sistema |
| Deadman no detecta fallo de red HW  | Si el USB se desconecta físicamente, el backend falla pero el deadman puede no disparar si el thread sigue activo |
| Alarmas sin acción autónoma         | `LeakageAlarm` y `VoltageStabilityAlarm` requieren intervención manual      |
| Estado FAULT es terminal            | No existe mecanismo automático de recuperación desde FAULT; requiere reinicio manual |
| Caché de 1 Hz                       | El watchdog usa datos con hasta 1 s de antigüedad en escenarios de alta carga |
| Sin interlock físico externo        | El pin de INTERLOCK del CAEN no está conectado en la instalación actual     |

---

## Recomendaciones Operacionales

1. **No modificar `HVLimits`** sin revisar las especificaciones del PMT. Los valores actuales incluyen derating de 85 % sobre los límites absolutos del fabricante.

2. **Revisar logs diariamente**. Los archivos CSV en `logs/` contienen el historial completo de voltajes, corrientes y estados. Una tendencia ascendente en IMON puede indicar contaminación o envejecimiento del PMT.

3. **No ignorar alarmas `WARNING`**. Aunque no producen apagados, indican degradación que puede derivar en fallos críticos si no se atiende.

4. **Verificar conectividad USB** antes de iniciar. Un `CAENBackend` que no puede conectar reintentará cada 30 s indefinidamente; esto es normal pero debe investigarse si persiste más de 2 minutos.

5. **Operar en entornos controlados**. La protección de `dV/dt` (200 V/s) puede dispararse por interferencias electromagnéticas en entornos ruidosos. Asegure el apantallamiento del cable HV.

6. **Documentar cualquier FAULT**. Registre la causa, la hora y las lecturas de VMON/IMON previas al fallo para mejorar la configuración de umbrales.

---

## Referencias Cruzadas

- Arquitectura del sistema y descripción de componentes → [architecture.md](architecture.md)
- Especificaciones del hardware controlado → [HARDWARE.md](HARDWARE.md)
- Configuración de parámetros operativos → [README.md](README.md)

# Estrategia de Layout PCB — Base de PMT Circular 80 mm (PMTx10Dyn, Divisor HV)

**Fecha:** 2026-03-29  
**Proyecto:** Base para tubo fotomultiplicador (PMT) — divisor HV con socket de 10 dynodos  
**Placa:** 1 capa (F.Cu), sin jumpers, sin capa B.Cu, geometría circular Ø 80 mm  
**Contexto de uso:** Detección de luz Cherenkov producida por muones en agua (pulsos rápidos, tr < 10 ns)

---

## 1. Antecedentes y motivación

### 1.1 Historial de iteraciones

| Iteración | Observación |
|-----------|-------------|
| v1 (placa grande) | Errores en el esquemático; descartada |
| v2 (placa reducida) | Esquemático corregido; se detectó pérdida de potencial ≈ 0.1 · VSET durante pruebas de voltaje |
| v3 (actual) | Reducción a Ø 80 mm; optimización de loop area para capacitores C1–C4 |

### 1.2 Problema observado: caída de ~0.1 · VSET

Durante las pruebas de la placa v2 se midió una tensión en el PMT aproximadamente **10 % menor** que el valor de referencia configurado (VSET). Las causas posibles (no excluyentes) se discuten en la [Sección 5](#5-análisis-de-la-caída-de-tensión-01-vset).

### 1.3 Requisito crítico: loop area ≤ 1 cm² por capacitor

El detector opera con pulsos de luz Cherenkov originados por muones en agua. Estos generan pulsos de corriente con **tiempos de subida típicos < 10 ns** en los últimos dynodos (Dy8–Dy10). A esas frecuencias (~30–100 MHz de ancho de banda efectivo):

- Un loop de área **A** con corriente de pulso **I** genera un campo magnético proporcional a **A · dI/dt**.
- Para que el efecto antena sea despreciable frente a otros factores de ruido del sistema, se establece el objetivo:

  > **A_loop(C1–C4) ≤ 1 cm² por capacitor**

  Esto equivale, por ejemplo, a un lazo de 10 mm × 10 mm, o a pistas de 2 mm de separación con un recorrido de 50 mm.

---

## 2. Geometría de la placa

```
  ┌─────────────────────────────────────┐
  │  PCB circular, Ø = 80 mm           │
  │                                     │
  │  ╔═══════════════════╗              │
  │  ║  Socket PMT       ║              │
  │  ║  r_min = 26.46 mm ║              │
  │  ║  (keepout de      ║              │
  │  ║   componentes)    ║              │
  │  ╚═══════════════════╝              │
  │                                     │
  │  Anillo disponible:                 │
  │  26.46 mm < r < 40 mm              │
  │  (componentes y pistas aquí)        │
  └─────────────────────────────────────┘
```

- **Radio del socket:** 26.46 mm (mínimo, nada entra en este círculo excepto el socket y pistas de paso).
- **Anillo útil para componentes:** entre r = 26.46 mm y r = 40 mm (borde de la placa).
- Las pistas pueden pasar por el centro (bajo el socket), pero **no se permiten jumpers ni uso de B.Cu**.

---

## 3. Estrategia de colocación por sectores

### 3.1 Principio general

El divisor HV (cadena de resistores R1…R11 + capacitores C1–C4 de bypas) se distribuye **alrededor del socket**, en el anillo exterior. La clave es colocar cada capacitor **lo más cerca posible de los dos pines del socket que alimenta**, minimizando la longitud de las pistas que forman el lazo.

### 3.2 Asignación de sectores (reloj)

La placa se divide en 4 cuadrantes/sectores angulares de ≈ 90° cada uno. La asignación sugerida es:

| Sector (reloj) | Ángulo aprox. | Componentes |
|----------------|---------------|-------------|
| A — Superior (12–3h) | 0°–90°   | HV_IN, R1, R2, C1 (Dy10–Dy9) |
| B — Derecho (3–6h)   | 90°–180° | R3, R4, C2 (Dy9–Dy8), R5 |
| C — Inferior (6–9h)  | 180°–270°| R6, R7, C3 (Dy8–Dy7), R8 |
| D — Izquierdo (9–12h)| 270°–360°| R9, R10, C4 (Dy7–Dy6), R11, salida de ánodo / coax |

> **Nota:** La salida de ánodo/señal (coax) se coloca en el sector opuesto a HV_IN para maximizar la separación entre HV y señal.

### 3.3 Regla de colocación para C1–C4

Para cada capacitor:
1. Identificar los dos pines del socket que conecta (dynodo superior e inferior de la etapa).
2. Colocar el cuerpo del capacitor **a menos de 5 mm** de ambos pines, en el anillo exterior.
3. Las pistas de conexión deben ser las más cortas posibles y correr **en paralelo y cercanas** (ida/vuelta juntas).

```
  Pin Dy(n) ──┬── pista_ida (≤ 5 mm) ──┤ Cx ├── pista_retorno (≤ 5 mm) ──┬── Pin Dy(n-1)
              │                                                             │
              └──────────────── retorno local (bus corto) ─────────────────┘
```

El lazo efectivo queda entonces como el rectángulo pequeño formado por las dos pistas cortas y el cuerpo del capacitor.

### 3.4 Bus de retorno de capacitores (HV_GND local)

- El bus de retorno común de C1–C4 **no debe formar un aro completo** alrededor del socket.
- Se implementa como **segmento corto** que solo une los capacitores de la zona, con **un único punto de conexión** al bus principal del divisor (conexión estrella).
- Esto impide que el pulso recorra todo el anillo antes de cerrarse.

```
  HV_GND_main ──── nodo_estrella ──┬── retorno C1
                                   ├── retorno C2
                                   ├── retorno C3
                                   └── retorno C4
```

---

## 4. Estrategia de ruteo

### 4.1 Ruteo radial + retorno local

El ruteo sigue un patrón **radial** (pistas que van del centro hacia el borde o viceversa) combinado con **segmentos circumferenciales cortos** en el anillo, solo donde sea necesario para alcanzar el pin correcto del socket.

Reglas de ruteo:
1. **Nunca** cerrar el retorno de un capacitor "por el lado largo" del anillo.
2. Cada par (pista_ida, pista_retorno) de un capacitor debe formar un rectángulo o L corta, no un semicírculo.
3. Las pistas de señal (anodo, primer dynode, trigger) van por el centro de la placa si es necesario cruzarlas, pero separadas físicamente de las zonas HV y de los loops C1–C4.

### 4.2 Estimación de área de lazo actual vs objetivo

| Capacitor | Nodos | Loop actual (estimado) | Objetivo | Acción |
|-----------|-------|------------------------|----------|--------|
| C1        | Dy10–Dy9 | por definir | ≤ 1 cm² | Mover C1 al sector A, pistas cortas |
| C2        | Dy9–Dy8  | por definir | ≤ 1 cm² | Mover C2 al sector B, pistas cortas |
| C3        | Dy8–Dy7  | por definir | ≤ 1 cm² | Mover C3 al sector C, pistas cortas |
| C4        | Dy7–Dy6  | por definir | ≤ 1 cm² | Mover C4 al sector C/D, pistas cortas |

> Para calcular el área del lazo: **A ≈ d × L**, donde **d** = separación entre pista ida y retorno, **L** = longitud del tramo.
> Ejemplo: d = 1 mm, L = 10 mm → A = 0.1 cm² (excelente). d = 5 mm, L = 20 mm → A = 1 cm² (límite).

### 4.3 Separación señal vs HV

- La ruta de salida del ánodo/coax debe correr en el sector **opuesto** a donde se concentran C1–C4 y la entrada HV.
- Evitar paralelismo entre la pista de señal y cualquier tramo del bus de retorno de capacitores por más de 5 mm.
- Si la pista de señal debe cruzar el área HV, hacerlo perpendicularmente (90°), nunca en paralelo.

### 4.4 Pistas que pasan por el centro

Para rutas que necesitan cruzar al otro lado del socket:
- Pasar por el centro de la placa (r < 26.46 mm, bajo el socket), donde no hay componentes.
- Usar segmentos rectos (no curvas) para simplificar el ruteo DRC.
- Mantener clearance HV entre pistas que pasan por el centro (ver Sección 4.5).

### 4.5 Reglas de diseño recomendadas (HV 1250–1300 V)

#### Anchos de pista

| Tipo de señal | Ancho mínimo recomendado |
|---------------|--------------------------|
| HV principal (cadena divisor) | 0.5 mm |
| Bus HV_GND | 0.5 mm |
| Ramas a capacitores (retorno local) | 0.3 mm |
| Señal ánodo (baja corriente) | 0.25 mm |

#### Clearance y creepage (IPC-2221 / IEC 60950-1, condiciones de altitud ≤ 2000 m, contaminación grado 2)

| Par de nodos | Voltaje diferencial típico | Clearance mínimo | Creepage mínimo |
|--------------|---------------------------|------------------|-----------------|
| HV_IN ↔ GND señal | 1300 V | ≥ 2.0 mm | ≥ 3.0 mm |
| Etapas adyacentes del divisor | ~130 V/etapa | ≥ 0.3 mm | ≥ 0.5 mm |
| Ánodo ↔ HV_GND | ~100 V | ≥ 0.3 mm | ≥ 0.5 mm |
| Borde de placa ↔ cualquier pista HV | — | ≥ 3.0 mm | ≥ 4.0 mm |

> Para instalaciones sumergidas (agua) o en ambientes húmedos, **multiplicar clearance y creepage × 1.5** y aplicar conformal coating.

#### Keepout zones

- **Keepout de componentes bajo el socket:** r < 26.46 mm — solo pistas permitidas.
- **Keepout de pistas señal cerca de HV_IN:** zona de 3 mm alrededor del conector SHV/HV.
- **Keepout en borde de placa:** banda de 3 mm sin cobre alrededor del perímetro circular.

---

## 5. Análisis de la caída de tensión (~0.1 · VSET)

### 5.1 Causas posibles

#### 5.1.1 Resistencia serie en el cableado/conectores (probable)

La caída en conectores SHV, cable coaxial HV y resistencias de protección puede ser significativa:
- Cable HV de 1 m con resistencia de 10 Ω/m + corriente del divisor de 100 µA → caída = 1 mV (despreciable).
- **Pero:** si hay una resistencia de protección en serie de 1 MΩ y la corriente total (divisor + PMT) es de 100 µA → caída = 100 V; sobre VSET = 1000 V esto representa caída / VSET = 100 V / 1000 V = **10 % ✓** (coincide con lo observado).

**Acción:** Verificar valor e intención de cada resistencia de protección en serie. Si la resistencia es muy alta respecto a la carga, reducirla o eliminarla.

#### 5.1.2 Método de medición (muy probable)

Un multímetro estándar tiene impedancia de entrada de **10 MΩ**. Si se mide el nodo HV_IN con el multímetro, este carga el nodo:
- VSET = 1000 V, R_divisor = 10 MΩ, R_multímetro = 10 MΩ → V_medido = VSET / 2 = **500 V (error del 50%)**.
- Incluso con R_divisor = 1 MΩ y R_multímetro = 10 MΩ: V_medido = VSET × 10/11 ≈ **0.91 VSET (error del 9 %)**.

**Acción:** Usar sonda HV de alta impedancia (≥ 100 MΩ) o leer el voltaje directamente desde el módulo CAEN. Nunca medir HV con multímetro convencional conectado directamente al nodo.

#### 5.1.3 Corriente de fuga superficial

En PCBs contaminadas (flux residual, humedad, polvo), la resistencia superficial entre pistas HV puede ser de unos pocos MΩ en lugar de GΩ, creando una carga adicional que drena el divisor.

**Acción:** Limpiar la placa con isopropanol, secar en horno a 60 °C durante 30 minutos antes de la prueba. Aplicar conformal coating (barniz) en zona HV si el entorno es húmedo.

#### 5.1.4 Carga dinámica del PMT (si está conectado durante la medición)

Si el PMT está expuesto a luz ambiente o a la fuente Cherenkov durante la medición, las corrientes de pulso cargan el divisor y pueden reducir la tensión promedio observable.

**Acción:** Medir VSET en oscuridad total o con el PMT desconectado mecánicamente del socket.

### 5.2 Protocolo de diagnóstico recomendado

```
Paso 1: Medir VSET directamente en el módulo CAEN (readback del módulo)
        ↓
Paso 2: Medir tensión en el conector SHV de entrada a la placa
        (con sonda HV ≥ 100 MΩ, en oscuridad, PMT conectado)
        ↓
Paso 3: Repetir sin PMT en el socket
        ↓
Paso 4: Comparar Paso 1 vs Paso 2 → diferencia = caída en cable + protecciones
        Comparar Paso 2 vs Paso 3 → diferencia = carga del PMT
        ↓
Paso 5: Si Paso 1 ≠ Paso 2 en > 1%: revisar resistencias de protección y cable HV
        Si Paso 2 ≠ Paso 3 en > 1%: revisar corriente divisor vs I_max_PMT
```

---

## 6. Checklist de verificación del layout

### 6.1 Colocación de componentes

- [ ] C1 está colocado a ≤ 5 mm de sus dos pines de dynodo en el socket.
- [ ] C2 está colocado a ≤ 5 mm de sus dos pines de dynodo en el socket.
- [ ] C3 está colocado a ≤ 5 mm de sus dos pines de dynodo en el socket.
- [ ] C4 está colocado a ≤ 5 mm de sus dos pines de dynodo en el socket.
- [ ] Ningún componente se encuentra dentro del radio de 26.46 mm del socket.
- [ ] El conector HV_IN y la salida de ánodo/coax están en sectores opuestos (separación ≥ 120°).

### 6.2 Ruteo y áreas de lazo

- [ ] Para cada capacitor C1–C4: A_loop estimado ≤ 1 cm².
- [ ] El bus de retorno de capacitores NO forma un aro completo alrededor del socket.
- [ ] El bus de retorno tiene un único punto de conexión al bus principal (topología estrella).
- [ ] No hay tramos de pista de señal (ánodo) paralelos a pistas HV por más de 5 mm.
- [ ] Las pistas que pasan por el centro lo hacen de forma recta y con clearance HV respetado.
- [ ] No se usan jumpers (0 Ω, puentes, cables) en ninguna parte del diseño.

### 6.3 HV — Clearance y creepage

- [ ] Clearance HV_IN ↔ GND señal ≥ 2.0 mm en toda la placa.
- [ ] Clearance borde de placa ↔ cobre HV ≥ 3.0 mm.
- [ ] Creepage HV_IN ↔ GND señal ≥ 3.0 mm (distancia superficial sin cortes de creepage).
- [ ] Zona keepout de 3 mm libre de cobre en el perímetro circular.
- [ ] DRC ejecutado sin errores de clearance.

### 6.4 Validación eléctrica post-fabricación

- [ ] Inspección visual: limpieza de flux, sin puentes de soldadura.
- [ ] Medición de resistencia del divisor total (multímetro, sin HV).
- [ ] Comparación I_divisor calculado vs medido a VSET nominal.
- [ ] Medición de voltaje en cada dynodo con sonda HV de alta impedancia.
- [ ] Prueba de fuga superficial (megóhmetro entre HV_IN y señal GND).
- [ ] Prueba funcional: pulso de señal con fuente de luz LED conocida.

---

## 7. Recomendaciones de prueba para la próxima fabricación

### 7.1 Instrumentación mínima recomendada

| Instrumento | Especificación mínima |
|-------------|----------------------|
| Sonda HV | ≥ 100 MΩ, rango ≥ 2 kV |
| Osciloscopio | BW ≥ 100 MHz, sonda × 10 |
| Fuente HV (módulo CAEN) | Lectura de corriente con resolución ≤ 1 µA |
| Megóhmetro | Rango ≥ 1 GΩ, tensión de prueba ≥ 500 V |

### 7.2 Secuencia de encendido recomendada

1. Verificar limpieza y conformal coating seco.
2. Conectar la placa al módulo CAEN con el PMT desconectado.
3. Subir HV lentamente (ramp 5 V/s) hasta VSET.
4. Verificar corriente del módulo CAEN: debe coincidir con I_divisor_calculado ± 10 %.
5. Medir voltaje en HV_IN con sonda HV → debe ser ≥ 0.99 · VSET.
6. Conectar el PMT (en oscuridad); repetir mediciones.
7. Si la caída > 1 %: seguir el protocolo de diagnóstico de la Sección 5.2.

---

## 8. Instrucciones para reproducir/verificar el ruteo en KiCad

> Esta sección aplica cuando se disponga del archivo `.kicad_pcb`. Los archivos KiCad no están incluidos en el repositorio en la versión actual.

### 8.1 Configuración del Design Rules Check (DRC)

En KiCad PCB Editor → File → Board Setup → Design Rules:

```
Minimum track width:    0.25 mm
Minimum clearance:      2.0 mm  (net class HV vs SIGNAL)
Minimum clearance:      0.3 mm  (net class HV vs HV etapas adyacentes)
Edge clearance:         3.0 mm
Courtyard clearance:    0.1 mm
```

Crear dos net classes:
- `HV`: nodos HV_IN, Dy1–Dy10, HV_GND → clearance 2.0 mm.
- `SIGNAL`: ánodo, trigger → clearance 0.5 mm entre sí.

### 8.2 Cómo medir el área de lazo en KiCad

1. Herramienta Inspector de diseño o usar "Length Tuner" para medir longitud de pistas.
2. Para cada capacitor Cx: anotar la longitud total del path (pista ida + pista retorno) y la separación máxima.
3. Calcular A_loop ≈ (separación_max_mm × longitud_total_mm) / 100  [cm²]  — donde `separación_max_mm` es la distancia entre la pista de ida y la de retorno y `longitud_total_mm` es la longitud de **un solo** tramo (ida o retorno), no la suma de ambos.
4. Si A_loop > 1 cm²: reroutear acercando el capacitor a sus pines.

### 8.3 Pasos sugeridos para reroutear C1–C4

1. En KiCad, colocar cada Cx en el anillo exterior, en el sector correspondiente a sus dynodos (ver Sección 3.2).
2. Rutear la pista de "dynodo superior" del capacitor directamente al pin del socket (< 5 mm).
3. Rutear la pista de "dynodo inferior / retorno" del capacitor al nodo adyacente del divisor (< 5 mm).
4. Verificar que ninguna de las dos pistas se "aleje" por el anillo antes de volver; si esto ocurre, relocalizar el capacitor.
5. Conectar el bus de retorno local al bus principal del divisor con un único via/pad de conexión.
6. Ejecutar DRC y verificar checklist de la Sección 6.

---

## 9. Referencias y normas aplicables

- IPC-2221B: *Generic Standard on Printed Board Design* — tablas de clearance/creepage por voltaje.
- IEC 60950-1 / IEC 62368-1: reglas de creepage y clearance para equipos electrónicos con HV.
- H. Johnson & M. Graham, *High-Speed Signal Propagation* — cap. de loop area y radiación EMI.
- PMT Handbook (Hamamatsu): diseño de divisores de voltaje para PMTs, recomendaciones de layout.
- CAEN DT55XXE User Manual: especificaciones de rampa, límite de corriente y lectura de voltaje.

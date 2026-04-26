# Física del Fotomultiplicador (PMT) — Fundamentos Teóricos

Este documento presenta los principios físicos que justifican el diseño y los parámetros operativos del sistema de control HV implementado en ConfCAENmodule. Comprender la física subyacente es esencial para interpretar las alarmas, ajustar umbrales y entender por qué la estabilidad del voltaje es crítica para la calidad de los datos experimentales.

---

## 1. Efecto Fotoeléctrico y Generación del Fotoelectrón

El proceso de detección comienza cuando un fotón incide sobre el **fotocátodo** del PMT (ventana de vidrio UV + capa semiconductora de CsSb o CsBiSb). Si la energía del fotón supera la función de trabajo del material:

```
E_fotón = hν > φ_cátodo
```

se emite un fotoelectrón con energía cinética:

```
E_k = hν − φ_cátodo
```

### Eficiencia cuántica (QE)

La probabilidad de que un fotón incidente produzca un fotoelectrón se expresa como la **eficiencia cuántica** (QE), que depende fuertemente de la longitud de onda:

```
QE(λ) = N_fotoelectrones / N_fotones_incidentes
```

Para el Hamamatsu R14374, la QE tiene su pico en ~420 nm (UV cercano), con una ventana de sensibilidad entre 185 y 650 nm. Esta sensibilidad espectral determina qué centelleadores son compatibles con el detector.

> **Implicación operativa**: El fotoelectrón generado tiene energía cinética del orden de 1 eV. Para producir una señal detectable, este único electrón debe ser amplificado varios millones de veces. Esa amplificación la realiza la cadena de dinodos polarizada por el alto voltaje.

---

## 2. Multiplicación de Electrones en la Cadena de Dinodos

El fotoelectrón es acelerado hacia el primer dinodo por el campo eléctrico creado por el voltaje de polarización. Al impactar, produce **emisión secundaria**: cada electrón incidente genera δ electrones secundarios (δ ≈ 3–10, dependiente del material y del voltaje entre dinodos).

### Proceso en cascada

Con `n` dinodos y una multiplicación por etapa δ:

```
G_total = δ^n
```

Para el R14374 con 8–10 dinodos y δ ≈ 4–6 por etapa, la ganancia total puede alcanzar 10⁶ – 10⁷.

### Dependencia con el voltaje aplicado

La emisión secundaria por dinodo depende de la energía de los electrones impactantes, que a su vez depende de la diferencia de potencial entre dinodos. Si el voltaje total aplicado es V:

```
G ∝ V^n
```

donde el exponente `n` es empíricamente 6–8 para el R14374 en el rango operativo nominal (700–1500 V). Esta relación potencial es la razón por la que una pequeña variación en el voltaje produce una variación grande en la ganancia:

```
ΔG/G ≈ n · (ΔV/V)
```

**Ejemplo numérico**: Con n = 7 y una fluctuación de voltaje de 1 V sobre 1350 V (≈ 0.07 %):

```
ΔG/G ≈ 7 × 0.0007 ≈ 0.5 %
```

Fluctuaciones mayores (p. ej., ripple de la fuente o inestabilidad térmica) producen directamente degradación en la resolución energética del experimento.

---

## 3. Parámetros Operativos Nominales y la Curva G(V)

La configuración nominal del sistema (VSET = 1350 V) se elige para operar en la zona lineal de la curva G(V), donde:

- La ganancia es suficientemente alta para distinguir pulsos individuales del ruido electrónico.
- El PMT no opera en saturación (respuesta no lineal).
- El envejecimiento del fotocátodo y los dinodos se minimiza (corriente promedio < 100 μA).

| Parámetro | Valor | Justificación física |
|-----------|-------|----------------------|
| VSET      | 1350 V | Ganancia óptima ~10⁶; zona lineal de G(V) |
| ISET      | 100 μA | Límite de corriente continua del R14374 |
| RUP       | 25 V/s | Rampa conservadora: evita sobretensiones transitorias y estrés en la cadena de dinodos |

### Por qué importa el ramping controlado

Un cambio brusco de voltaje (HV en escalón) produce corrientes de desplazamiento en las capacidades parásitas de la base del PMT. Estas corrientes transitorias pueden:

1. Saturar temporalmente la cadena de dinodos.
2. Generar pulsos espurios detectables por el sistema de adquisición.
3. En casos extremos, dañar la interfaz fotocátodo-primer dinodo.

La rampa de 25 V/s garantiza que el sistema alcance el estado estacionario sin perturbaciones detectables.

---

## 4. Fuentes de Ruido Intrínseco del PMT

### 4.1 Corriente de oscuridad (Dark Current)

Incluso sin luz incidente, el PMT genera una pequeña corriente de oscuridad debida a:

- **Emisión termoiónica del fotocátodo**: electrones emitidos por agitación térmica (dominante a temperatura ambiente).
- **Emisión termoiónica de los dinodos**: contribución menor pero no despreciable.
- **Corrientes de fuga**: corriente residual entre electrodos a través del vidrio o la estructura mecánica.

Para el R14374: corriente de oscuridad típica < 1 nA (a temperatura ambiente, voltaje nominal).

> **Implicación para las alarmas**: La `LeakageAlarm` monitorea una tendencia creciente en IMON que puede indicar contaminación del fotocátodo, envejecimiento del PMT, o fuga en el cable HV antes de que se produzca un fallo catastrófico.

### 4.2 Ruido de disparo (Shot Noise)

La corriente del PMT exhibe fluctuaciones estadísticas de naturaleza cuántica. La corriente de oscuridad media `I_d` tiene asociada una fluctuación:

```
σ_I = √(2 · e · I_d · B)
```

donde `e` es la carga del electrón y `B` el ancho de banda del sistema de detección.

### 4.3 Ruido de la fuente HV (Ripple)

El ripple del módulo CAEN DT5533EN es < 5 mV pico a pico. Trasladado a ganancia:

```
ΔG/G ≈ n · (ΔV_ripple / V) ≈ 7 × (5×10⁻³ / 1350) ≈ 2.6×10⁻⁵
```

Este nivel es despreciable frente al shot noise y al jitter de los pulsos individuales del PMT. No obstante, la `VoltageStabilityAlarm` detecta fluctuaciones de σ(VMON) > 10 V, indicativas de problemas en la fuente o en el cable HV.

---

## 5. Señal Esperada en Función del HV Aplicado

En condiciones nominales, el PMT convierte cada fotón detectado en un pulso de carga:

```
Q = G · e
```

Con G ≈ 10⁶ y e = 1.6×10⁻¹⁹ C:

```
Q ≈ 1.6×10⁻¹³ C = 160 fC
```

Este pulso de carga se descarga a través de la resistencia de terminación (~50 Ω), produciendo un pulso de voltaje con:

- **Amplitud**: Q / C_parásita (típicamente decenas de mV)
- **Duración**: ~5–20 ns (determinada por la constante de tiempo RC de la base del PMT)

### Variación de la amplitud con el voltaje

Dado que G ∝ V^n, la amplitud del pulso varía con el voltaje aplicado. Durante la puesta en marcha del sistema o en procedimientos de calibración conjunta con la Red Pitaya DAQ, se puede construir la curva de calibración empírica barriendo VSET entre, por ejemplo, 900 V y 1400 V y midiendo la amplitud media de los pulsos.

---

## 6. Por qué la Estabilidad del HV es Crítica

La resolución energética de un detector de partículas basado en PMT se puede expresar aproximadamente como:

```
R = ΔE/E ∝ 1/√(N_fotoelectrones × G)
```

Cualquier fluctuación en G (causada por inestabilidad en V) contribuye cuadráticamente a la degradación de R:

```
(σ_R / R)^2 ≈ (σ_intrinseca)^2 + (n · σ_V / V)^2
```

El control preciso del voltaje —y la detección temprana de derivas y ruidos en el HV— es por tanto una condición necesaria para obtener datos experimentales de calidad. Este es el propósito físico fundamental de ConfCAENmodule.

---

## Referencias

- Knoll, G. F. (2000). *Radiation Detection and Measurement* (3rd ed.). Wiley.
- Hamamatsu Photonics. *Photomultiplier Tubes: Basics and Applications* (4th ed.). Hamamatsu Photonics K.K.
- Hamamatsu Photonics. *R14374 datasheet*.
- Leo, W. R. (1994). *Techniques for Nuclear and Particle Physics Experiments*. Springer.

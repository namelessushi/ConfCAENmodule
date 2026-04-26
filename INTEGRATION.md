# Integración del Sistema Detector Completo

Este documento describe la arquitectura del sistema experimental completo en el que opera ConfCAENmodule, identificando los límites de responsabilidad entre los distintos componentes y equipos de trabajo.

---

## Visión General

El sistema de detección de partículas del laboratorio está compuesto por tres subsistemas principales que colaboran en cadena:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE DETECCIÓN COMPLETO                     │
│                                                                       │
│   ┌──────────────────────┐                                           │
│   │  CAEN DT5533EN       │  ← Control de HV (este repositorio)      │
│   │  Módulo HV           │                                           │
│   └──────────┬───────────┘                                           │
│              │ Cable SHV (Alto Voltaje)                              │
│              ▼                                                        │
│   ┌──────────────────────┐                                           │
│   │  PMT Hamamatsu       │  ← Detector (componente físico central)  │
│   │  R14374              │                                           │
│   │  Fotocátodo + dinodos│                                           │
│   └──────────┬───────────┘                                           │
│              │ Cable BNC (Señal de ánodo, pulsos ns)                 │
│              ▼                                                        │
│   ┌──────────────────────┐                                           │
│   │  Red Pitaya          │  ← Adquisición de datos (proyecto externo)│
│   │  (ADC / DAQ)         │                                           │
│   └──────────┬───────────┘                                           │
│              │ Datos digitales                                        │
│              ▼                                                        │
│         Análisis y física                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Responsabilidades por Subsistema

### 1. Control de HV — ConfCAENmodule (este repositorio)

**Responsable**: Este proyecto.

Controla el voltaje de polarización del PMT mediante el módulo CAEN DT5533EN. Sus responsabilidades son:

- Aplicar y mantener el voltaje VSET con ramping controlado.
- Monitorear en tiempo real VMON e IMON.
- Disparar protecciones ante condiciones anómalas (sobrecorriente, deriva de voltaje, inestabilidad).
- Registrar en CSV el historial de operación para trazabilidad experimental.

No realiza adquisición, digitalización, ni análisis de las señales del PMT.

### 2. Detector — PMT Hamamatsu R14374

**Componente físico compartido** entre los dos sistemas de control.

El PMT convierte fotones (o partículas cargadas en detectores de centelleo) en pulsos eléctricos de nanosegundos. Su respuesta (ganancia, linealidad, ruido) depende directamente del voltaje de polarización suministrado por el subsistema anterior.

### 3. Adquisición de Datos — Red Pitaya DAQ

**Responsable**: Colega de laboratorio (proyecto independiente).

La Red Pitaya actúa como digitalizador de los pulsos de ánodo del PMT. Este subsistema es responsabilidad de un colega de laboratorio y se desarrolla como un proyecto separado. En el contexto de este repositorio, la Red Pitaya se trata como una **caja negra externa**: recibe la señal del PMT y genera datos digitales que alimentarán el análisis posterior.

> **Nota**: La interfaz exacta, el protocolo de comunicación y el software de la Red Pitaya no están documentados aquí. Para información sobre ese subsistema, consultar directamente con el responsable del proyecto DAQ.

---

## Estado Actual del Proyecto

| Subsistema | Estado | Responsable |
|---|---|---|
| Control HV (CAEN) | ✅ Operativo | Este repositorio |
| PMT R14374 | ✅ Instalado | — |
| Adquisición Red Pitaya | 🔄 Desarrollo separado | Colega de lab |
| Análisis conjunto | 🔲 Pendiente | — |

El foco actual de este repositorio es garantizar un control HV robusto y seguro. La integración con el sistema de adquisición es un paso posterior que requerirá coordinación con el responsable del proyecto Red Pitaya.

---

## Procedimiento de Calibración Conjunta (Futuro)

Cuando ambos subsistemas estén operativos simultáneamente, el procedimiento de calibración típico consistirá en:

1. **Fijar voltaje HV** en ConfCAENmodule (p. ej., V₁ = 1000 V).
2. **Adquirir datos** con Red Pitaya durante un intervalo definido.
3. **Extraer la amplitud media** de los pulsos del PMT.
4. **Repetir** para una serie de voltajes (p. ej., 1000, 1050, 1100, ..., 1400 V).
5. **Construir la curva G(V)** y ajustar el modelo `G ∝ V^n` para obtener el exponente empírico.
6. **Determinar el punto de operación óptimo** según los requisitos de ganancia y ruido del experimento.

Este procedimiento permitirá verificar que el PMT opera en la zona lineal y que los parámetros del sistema de control (VSET, umbrales de alarma) están bien calibrados para el experimento específico.

---

## Referencias Cruzadas

- Física del PMT y justificación de parámetros operativos → [THEORY.md](THEORY.md)
- Especificaciones del PMT y del módulo CAEN → [HARDWARE.md](HARDWARE.md)
- Protecciones de seguridad del detector → [SAFETY.md](SAFETY.md)
- Arquitectura del software de control → [architecture.md](architecture.md)

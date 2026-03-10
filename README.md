# HV Control System for PMT Detector

Software de control de alto voltaje para módulos CAEN DT55XXE.

## Features
- Control seguro de HV
- Monitor batch con cache
- Watchdog de seguridad
- Deadman multiproceso
- Logging CSV diario

## Arquitectura

backend → hardware interface
channel → control por canal
monitor → adquisición batch
watchdog → seguridad física
runner → orquestación

## Uso

python hv_run.py

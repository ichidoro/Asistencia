# REGLAS MAESTRAS DE ASISTENCIA Y CONTROL HORARIO (AGUACOL)

Este documento define la especificación técnica canónica y las reglas de negocio inmutables para el motor de cálculo de asistencia matricial cuántico (`QuantumMatrixEngine` / `asistencia_service.py`).
**TODA LA APLICACIÓN OPERA CON ESTOS 2 TIPOS DE HORARIOS Y BAJO ARQUITECTURA CUÁNTICA MATRICIAL PURA.**

---

## 1. Tipos de Programación Horaria y Reglas de Negocio

### Tipo 1: `CICLO_INTELIGENTE` (Ciclo Inteligente)
- **Ámbito**: Operarios de planta, supervisores, personal de bodega, mantenimiento y oficinas (turnos fijos o rotativos multi-semana de 1 a 4 semanas).
- **Resolución de Horas y Semanas**: `QuantumShiftWeekMatcher` resuelve la semana activa por minimización de distancia de fase circular entre las marcas reales y los bloques configurados en la interfaz para cada día.
- **Cálculos**: Atrasos diarios y salidas adelantadas según tolerancias de UI, colaciones automáticas o reales según umbral de UI, anclajes de entrada y salida de UI, y horas extras diarias.
- **Cruce de Medianoche Universal**: Soportado tanto por configuración teórica (`hora_salida < hora_entrada` o `cruza_medianoche = 1`) como por marcas físicas continuadas en la madrugada de $D+1$.

---

### Tipo 2: `BOLSA_FLEXIBLE` (Bolsa Flexible)
- **Ámbito**: Choferes de distribución y logística.
- **Naturaleza**: Horario de bolsa de horas semanal o mensual (sin horas rígidas diarias, `horas_teoricas: 0.0` diario, sin atrasos punitivos diarios). Las horas efectivas se acumulan a la meta de la bolsa.
- **Cruce de Medianoche Universal**: **ACTIVADO EN TODOS LOS CASOS.** Cualquier jornada que inicie en la noche y termine en la madrugada del día siguiente ($D \rightarrow D+1$) se empareja de forma continua como un único vector de trabajo.
- **Diferenciador Único (`permite_viajes_largos`)**:
  - **`permite_viajes_largos = 0` (Bolsa Flexible Estándar)**: Choferes de reparto local / distribución urbana diaria.
  - **`permite_viajes_largos = 1` (Bolsa Flexible con Viajes Largos)**: Choferes de ruta interurbana con pernoctación fuera de planta, acreditación de bitácora de viaje (conducción + descanso) y protección contra falsas inasistencias en días de ruta.
- **Cero menciones de "Art. 25 BIS"**: En la interfaz, reportes y tablas se denomina única y limpiamente como **Bolsa Flexible**.

---

## 2. Protocolo Obligatorio Anti-Regresión

Antes de cualquier despliegue a producción:
1. Validar compilación de sintaxis de todos los archivos `.py` (`py_compile`).
2. Validar sintaxis y referencias en archivos `.js`.
3. Validar consistencia con datos reales de la base de datos (choferes de viajes largos, choferes de reparto local y operarios nocturnos).

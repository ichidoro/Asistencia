# REGLAS MAESTRAS DE ASISTENCIA Y CONTROL HORARIO (AGUACOL)

Este documento define la especificación técnica canónica y las reglas de negocio inmutables para el motor de cálculo de asistencia (`asistencia_service.py`).
**CUALQUIER MODIFICACIÓN DEBE RESPETAR ESTOS 4 MODOS Y NO ALTERAR REGLAS ENTRE ELLOS.**

---

## 1. Modos de Programación y Reglas de Negocio

### Modo 1: `DINAMICO_FLEXIBLE` (Producción)
- **Ámbito**: Operarios de planta, supervisores y personal con turnos rotativos semanales (Semanas 1 a 4).
- **Extracción de Marcas**: `block_inteligente` basado en arrastre de la semana activa (`rotativo_last_sem_dict`) y evaluación de jornada normal vs jornada especial.
- **Cálculos**: Atrasos diarios, salidas adelantadas, colaciones reales descontadas y horas extras diarias.

---

### Modo 2: `FLEXIBLE_BOLSA` Tradicional (`permite_viajes_largos = 0`) (Turno 9: Tradicional Transporte)
- **Ámbito**: Choferes de reparto local urbano/diurno.
- **Límite Calendario**: Estricto dentro del día calendario ($00:00$ a $23:59$).
- **Cruce de Medianoche**: **DESACTIVADO** (`permite_viajes_largos = 0`). Las jornadas inician y terminan en el mismo día.
- **Cálculos**: Acumula horas trabajadas hacia la meta mensual de la bolsa flexible (180h). No genera atrasos fijos por minuto de reloj.

---

### Modo 3: `FLEXIBLE_BOLSA` con Viajes Largos (`permite_viajes_largos = 1`) (Turno 25: Logística Transporte)
- **Ámbito**: Choferes de rutas largas, viajes interurbanos y transporte nocturno.
- **Cruce de Medianoche Continuo**: 
  - Si un conductor inicia turno o viaje en la noche ($\ge 20:00$), la marca de Entrada se mantiene en su día de inicio y busca su Salida en la madrugada del día siguiente ($D+1$ antes de las 14:00h).
- **Doble Jornada en el Mismo Día**:
  - Si en un día hay una jornada diurna (ej. `05:59` a `13:13`) y un viaje nocturno (ej. `21:57` a `05:04` $D+1$):
    * Se empareja de forma secuencial cronológica (FIFO).
    * `05:59` cierra con `13:13` (Jornada 1).
    * `21:57` cierra con `05:04` (Jornada 2).
    * Ambas jornadas se suman a las horas efectivas del colaborador sin saltarse marcas ni generar inasistencias en cascada.
- **Retorno de Ruta Aislado (Madrugada)**:
  - Salidas de madrugada ($02:00$ a $07:00$) sin entrada previa en esa madrugada generan la alerta `[Retorno de Ruta Detectado]` con Split Badge (`OK + ANO`) para permitir su unión con el viaje de origen mediante el botón `Registrar Viaje Largo`.

---

### Modo 4: `FIJO_ORDINARIO` (Administración / Portería)
- **Ámbito**: Personal de oficina, porteros y guardias con horarios fijos diarios.
- **Cálculos**: Comparación contra hora teórica de entrada y salida, con cálculo de atrasos y compensaciones.

---

## 2. Protocolo Obligatorio Anti-Regresión

Antes de cualquier despliegue a producción:
1. Ejecutar `tests/test_attendance_regressions.py`.
2. Validar que la corrida de prueba para Bastian Adams (ID 156) resulte en **0 anomalías falsas** y **0 inasistencias falsas**.
3. Validar que los 18 choferes del Turno 9 y los 45 operarios de Producción arrojen **0 diferencias** contra el estado previo.
4. Validar sintaxis completa de todos los archivos `.js` y compilación de `.py`.

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

---

## 3. Marcaciones repetidas o impares (solo Ciclo Inteligente)

Regla de oro: **manda el horario/turno asignado al empleado**, también en los turnos que cruzan la noche. El motor **no crea horas ni ventanas fijas** y no inventa marcas: usa las marcas reales y deja anotado en `observaciones` lo que descartó. **Bolsa Flexible no se rige por esta sección.**

| Marcas del día | Qué hace el motor | Observación que deja |
|---|---|---|
| Entrada, Entrada, Salida | La jornada va de la 1ª Entrada a la Salida. La Entrada del medio se descarta (falta una marca de la colación: la salida o el regreso). Una Entrada nunca cierra la jornada si después viene una Salida. | `Dos Entradas seguidas (HH:MM:SS y HH:MM:SS): falta una marca de colación; …` |
| Entrada, Salida, Salida (o más Salidas seguidas) | La jornada termina en la **última** Salida; las de en medio se descartan. Ya no se elige "la Salida más cercana a la salida teórica". | `Salidas seguidas: se tomó la última y se descartó la de las HH:MM:SS.` |
| Entrada, Entrada (y nada después) | Sin Salida posterior, la 2ª sigue valiendo como Salida mal rotulada (como siempre). | — |
| Dos marcas del mismo tipo a menos de 3 min | Rebote del lector: vale la primera (anti-rebote existente; usa `redondeo_minutos` del turno si está configurado). | — |

- **La pausa de las marcas descartadas la cubre la colación automática del turno asignado** (`descuento_colacion_auto`, `minutos_colacion_auto`, `umbral_horas_colacion`). Si entre otras marcas hay una pausa real medida, se descuenta la mayor (pactada o real), como siempre.
- **Límite de seguridad**: una Salida de más muy tardía no paga horas extra sola. Si el trabajo pasa de `asistencia_max_extras_ordinarias_dia_habil` (240 min por defecto) sobre el turno, el bloque queda como *Jornada Especial* pendiente de autorización y el turno base mantiene sus horas teóricas. Las horas extra normales quedan `PENDIENTE` hasta que alguien las autorice.
- **Dónde está en el código**: `MultiBlockTensorSolver.collapse_consecutive_same_type` (Salidas seguidas) y el paso 7 de `QuantumMatrixEngine.solve_attendance_day` (Entrada, Entrada, Salida), ambos en `backend/services/quantum_matrix_engine.py`.
- **Casos reales que originaron estas reglas** (sin datos de personas): martes 29-09-2026, turno JJV Producción, Entrada 06:40 · Entrada 13:17 · Salida 16:29 (el día cerraba a las 13:17 con 192 min de deuda); jueves 01-10-2026, turno Planta Mantención 2, Entrada 07:52 · Salida 13:24 · Salida 17:16 (el día cerraba a las 13:24 con 148 min de deuda).

## 4. Panel «Marcaciones del día» (modal «Ingreso Manual») y turnos que cruzan la medianoche

Cada jornada muestra **las marcas que usó su cálculo**, no las que caen en su fecha del calendario. Un turno que cruza la medianoche cierra con una marca del día siguiente, y esa marca es de ese turno.

| Marca | Aparece en el panel de… |
|---|---|
| La usó el cálculo de ese día (`asistencias.marcas_consumidas_ids`), aunque caiga al día siguiente | ese día, con la etiqueta «DD-MM · día siguiente» |
| La usó el cálculo del día anterior o del siguiente | solo en el día que la usó |
| Nadie la usó y cae en esa fecha del calendario | ese día |

- **Caso real que originó la regla** (sin datos de personas): turno Tarde 15:00-23:00, Planta Mantención 2. 13-10: Entrada 14:59:59 · Salida 00:08:17 (ya del 14 en el calendario). 14-10: Entrada 15:05:11 · Salida 23:04:45. El cálculo estaba bien, pero el panel del 13 mostraba solo la Entrada («hay una sola: confirme cuál falta») y el del 14 mostraba la Salida de las 00:08 como su primera marca («La primera marca del día está como Salida»).
- **Guardar la clasificación** acepta las marcas de la jornada (también las del día siguiente) y rechaza con 400 las que son de otro turno. Después recalcula el día y, si el día siguiente ya estaba calculado (no es futuro y su período sigue abierto), lo recalcula también, porque hereda las marcas que usó este día.
- **Colación**: los huecos entre marcas (20-150 min) se miden con fecha y hora completas; así un hueco que cruza la medianoche no sale negativo.
- El aviso amarillo «Ingrese la marcación faltante…» solo se ve cuando de verdad falta una marca.
- **Dónde está en el código**: `marcas_que_pertenecen_al_dia` y `_marcas_del_dia` en `backend/routers/asistencia.py`; el panel en `frontend/js/marcaciones_manuales.js` (`renderPanelMarcasDia`). Listar las marcas es solo lectura: los días ya calculados se ven bien sin reprocesar.

## Cómo se prueba

Cada error que se encuentra queda como regla en este documento **y** como prueba en `backend/tests/`:
`test_dos_entradas_y_salida.py`, `test_salidas_seguidas_ultima.py` y `test_marcas_dia_cruce_medianoche.py`. Se corren desde la raíz del proyecto con `python -m pytest backend/tests -q` (requiere `pytest`, que no viene en `requirements.txt`).
Ojo: `.gitignore` ignora los archivos `test_*.py`; las pruebas nuevas se suben con `git add -f`.

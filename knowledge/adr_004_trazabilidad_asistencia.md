# ADR 004: Trazabilidad y Reglas de Negocio en Asistencia

## Fecha
16 de Mayo de 2026

## Contexto
Durante la revisión del módulo de asistencia, se identificaron situaciones que parecían ser bugs debido a una aparente inconsistencia visual, pero que en realidad eran comportamientos orgánicos correctos esperados por las reglas de negocio (e.g., feriados trasladados en turnos nocturnos y celdas en blanco para días sin marcas de turnos flexibles).

## Decisión
Se establece la obligatoriedad de implementar "Guardias Cognitivas" (comentarios explícitos marcados con `[BUSINESS_RULE: ...]`) en el motor de asistencia (`asistencia_service.py`) y mejorar la trazabilidad visual en el frontend, en lugar de intentar forzar alteraciones en la lógica temporal/matemática del motor.

Además, se toma la decisión arquitectónica para la lógica de fechas en el motor:
1. **Feriados Nocturnos (Ley Chile):** Para turnos que inician en víspera de feriado y cruzan la medianoche (nocturnos), el feriado se consolida visualmente el día de inicio del turno (la víspera). El día feriado oficial en el calendario figura como trabajado u OK. Esta lógica NO debe refactorizarse por supuesta "inconsistencia" con turnos diurnos.
2. **Predicción del Futuro (Días Dinámicos):** Para evitar mostrar falsas inasistencias en el futuro, las celdas de fechas futuras (`fecha > today`) quedan en blanco intencionalmente. 
3. **El día actual (Hoy):** La condición de bloqueo de predicción **sólo aplica al futuro estricto (`>`)**, no al día presente (`>=`). El día "hoy" siempre se evalúa, permitiendo al sistema identificar si corresponde un estado de descanso (ej. `LIB`) basado en la rotación heredada, evitando que empleados que terminan su ciclo nocturno vean su día libre de hoy en blanco.

## Consecuencias
- Todo desarrollador o IA que analice `asistencia_service.py` debe respetar los bloques etiquetados con `[BUSINESS_RULE]`.
- Se mejora la experiencia del usuario (y auditores) mediante tooltips en los estados generados automáticamente (`INA`, `LIB`, `FER`) explicando su procedencia.
- Se previene la destrucción de lógica de asistencia probada mediante refactorizaciones "estéticas".

# Lo pendiente en Asistencia

Actualizado el 15-11-2026 con datos leídos de producción ese mismo día (solo lectura). Reemplaza la versión del 7-11-2026. Los números cambian a medida que se trabaja: antes de decidir algo, conviene volver a medirlo.

> **Cómo se nombra a las personas en este documento.** Este archivo va a GitHub, así que no lleva nombres. Cada persona aparece con sus iniciales (primer nombre, apellido paterno y apellido materno) y el nombre de su horario entre paréntesis. La versión con nombres completos es `docs/PLAN_PENDIENTE_local.md`, que queda solo en el PC de la persona dueña y no se sube.

> **Regla para mantenerlo al día.** Cada vez que se termina algo de este plan, se actualiza este archivo en el mismo cambio (ver `CLAUDE.md`).

---

## 1. Lo que ya quedó resuelto (desde el 7-11)

- **Cierres:** Mayo a Octubre 2026 cerrados en las cuatro áreas (Logística Tradicional, Mantención, Producción y Seguridad). Solo Noviembre sigue abierto (mes en curso).
- **Reglas de marcaciones:** las 30 están encendidas; ya no hay reglas sin decidir. La Regla 7 (SALIDA · SALIDA) quedó en «calcula».
- **Días por revisar:** ninguno.
- **Casos raros del plan anterior:** ya no existen la SALIDA manual de las 00:00 del 30-06 ni las jornadas especiales de 0 minutos.
- **Tolerancia de atraso:** 1 minuto en los 13 horarios (14-11). Los segundos se siguen descontando; solo cambia el estado del día.
- **Umbrales de colación (15-11):** Tradicional Gruero Interno 6,75 h, Tradicional Bodega 2,75 h y Tradicional Administrativo 5,5 h, como recomendó el estudio del 24-10.
- **Cierre:** ahora frena si hay jornadas especiales por validar (15-11). El paso 3 cuadra las horas extra por persona (13-11).
- **Ciclo del día:** en horarios con rotación se elige con las marcas como las lee la regla (15-11).

---

## 2. Lo que queda

### 2.1 Cinco jornadas especiales sin validar en meses ya cerrados

Se cerraron porque el cierre todavía no revisaba las jornadas especiales (ya se corrigió para los cierres siguientes). Sin validar, no se pagaron.

| Fecha | Persona (horario) | Tipo | Minutos |
|---|---|---|---:|
| 28-06 | O.C.E. (Planta Mantencion 2) | Día libre | 900 |
| 29-06 | V.M.P. (Planta Mantencion 2) | Feriado | 58 |
| 05-07 | V.M.P. (Planta Mantencion 2) | Día libre | 123 |
| 05-07 | J.G.G. (Planta Mantencion 2) | Día libre | 287 |
| 16-07 | O.C.E. (Planta Mantencion 2) | Feriado | 390 |

**Decisión de la persona dueña:** dejarlas así o reabrir Junio y Julio de Mantención para validarlas.

### 2.2 Horarios

| Horario | Qué falta |
|---|---|
| Tradicional Bodega | Evaluar un ciclo de mañana. Hoy tiene uno solo, de 11:30 a 20:00, y hay personas que trabajan de mañana. Antes de agregarlo, revisar los días reales. |
| Planta Mantencion (el primero) | Está inactivo y sin personas (se usa Planta Mantencion 2): no hace falta tocarlo. |

### 2.3 Correo del cierre

Los destinatarios del informe de cierre están vacíos a propósito mientras se probaba con los meses pasados. Falta cargarlos en Configuración. El mensaje del cierre ya dice si el correo se envió.

### 2.4 Preinforme con señales para los jefes de área

Las propuestas se descartaron. Queda esperando un ejemplo de la persona dueña: un caso real o una frase que le gustaría leer en el preinforme.

### 2.5 Reorganizar el código grande

De la auditoría `docs/AUDITORIA_GRAFO.md` (7-11). Se dejó para después de los cierres, y ese momento ya llegó:

- **#3:** repartir `routers/asistencia.py` por tema, sin cambiar las URL.
- **#5:** sacar de `AsistenciaService` lo que no es cálculo (la tabla de Marcaciones y el cierre).
- **#9:** partir `_solve_core`, `procesar_empleado_dia` y `reprocesar_periodo_empleado`. Es lo más delicado: va al final, en pasos chicos, con la prueba guardiana en verde.
- **#4:** las «capas al revés», solo explicado.

No arregla errores visibles: da orden para cambiar el código con menos riesgo.

### 2.6 Deudas técnicas

- El Excel de cierre busca `frontend/assets/img/logo.jpg`, que no existe (hay `logo.png`): sale sin logo.
- En el servidor no está definido `DEBUG` y el valor por defecto es verdadero: ante un error, la app muestra el detalle técnico.
- La clave inicial del usuario admin está escrita en `backend/repositories/seguridad.py` (solo se usa si el admin no existe).

### 2.7 Auditoría del código del 15-11-2026

Plan en cinco etapas en `docs/AUDITORIA_CODIGO_2026-11-15.md`. La etapa 1 está en producción desde el 15-11-2026 (commit 2af619f): corrige cuatro fallas (la hora de Visitas, el selector de inasistencias, el Excel por rango de Reportes y la purga del registro de auditoría) y quita 18 funciones sin uso. Las 81 visitas pasadas con la hora corrida se dejan como están (decisión de la persona dueña, 15-11-2026); las nuevas ya se guardan con la hora correcta.

La etapa 2 quedó hecha el 15-11-2026: un solo ayudante de pantalla por tarea (`frontend/js/ayudantes.js`), cuatro choques de nombres entre archivos resueltos y una prueba guardiana. Siguen la etapa 3 (arañas como pruebas permanentes), la 4 (SQL a los repositorios) y la 5 (partir las funciones grandes del cálculo).

### 2.8 Mapa del código (graphify)

Se ve en Configuración → Mapa del código (solo el súper administrador) y se vuelve a publicar con cada cambio de código (`scripts/publicar_mapa.py`).

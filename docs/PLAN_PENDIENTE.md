# Lo pendiente en Asistencia

Actualizado el 15-11-2026 con datos leídos de producción ese mismo día (solo lectura); decisiones del 18-11-2026 agregadas. Reemplaza la versión del 7-11-2026. Los números cambian a medida que se trabaja: antes de decidir algo, conviene volver a medirlo.

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

**Decisión de la persona dueña (18-11-2026): validarlas.** Las cinco caen en el período Julio 2026 (26-06 al 25-07), así que basta reabrir ese período solo para Mantención, validarlas y volver a cerrarlo. Falta hacerlo desde la aplicación.

**Ensayo del 21-11-2026** (con el respaldo de ese día, en una base aparte del PC que se borró al terminar). Se reabrió Julio de Mantención, se validaron las cinco y se volvió a cerrar, de las dos formas:
- Como jornada EXTRA (monto fijo): solo cambian esas cinco jornadas, que pasan a EXTRA con sus minutos (900, 58, 123, 287 y 390).
- Pasándolas a horas extra y aprobándolas completas: solo cambian esos cinco días, con sus horas extra aprobadas.
- En las dos formas no cambia ningún otro día ni otra persona del mes, el cierre pasa sin frenos (pide aceptar 1 inasistencia sin justificar, como la primera vez) y al cerrar, Noviembre vuelve a quedar vigente.
- Falta que la persona dueña elija la forma de pago de cada una.

### 2.2 Horarios

| Horario | Qué falta |
|---|---|
| Tradicional Bodega | **No se cambia** (decisión de la persona dueña, 21-11-2026): trabajar de mañana son casos puntuales, cuando la jefatura cita a alguien algunos días. |
| Planta Mantencion (el primero) | Está inactivo y sin personas (se usa Planta Mantencion 2): no hace falta tocarlo. |

### 2.3 Correo del cierre

Los destinatarios del informe de cierre los carga la persona dueña en Configuración (18-11-2026: es tarea suya, no del desarrollo). El mensaje del cierre ya dice si el correo se envió.

### 2.4 Preinforme con señales para los jefes de área

Propuesta del 18-11-2026, aprobada para Ciclo Inteligente: una sección «Para coordinar antes del cierre» con quién debe horas (atrasos, salidas adelantadas) o tiene inasistencias sin justificar, y cómo recuperarlas antes del cierre. Para Bolsa Flexible se propuso el 21-11-2026 otra forma, porque en Bolsa las horas bajo la meta no se descuentan: quién va bajo la meta (horas que todavía se pueden programar) y quién ya la pasó (desde ahí se pagan como horas extra). Falta el visto bueno de la parte de Bolsa y programarlo.

### 2.5 Reorganizar el código grande

De la auditoría `docs/AUDITORIA_GRAFO.md` (7-11). Se dejó para después de los cierres, y ese momento ya llegó:

- **#3:** repartir `routers/asistencia.py` por tema, sin cambiar las URL. **Plan escrito el 21-11-2026** (etapa 6 de `docs/AUDITORIA_CODIGO_2026-11-15.md`, en 7 pasos con su ensayo). Paso 6a hecho (21-11-2026): GPS y velocidades, rutas idénticas. Paso 6b hecho: la libreta del Art. 25 bis, rutas idénticas. Paso 6c hecho: compensaciones y deuda, rutas idénticas.
- **#5:** sacar de `AsistenciaService` lo que no es cálculo (la tabla de Marcaciones y el cierre).
- **#9: hecho** (16 al 18-11-2026, etapa 5 de `docs/AUDITORIA_CODIGO_2026-11-15.md`): las tres funciones quedaron en piezas con nombre y el resultado no cambió.
- **#4:** las «capas al revés», solo explicado.

No arregla errores visibles: da orden para cambiar el código con menos riesgo.

### 2.6 Deudas técnicas

- **Hecho (18-11-2026):** el Excel de cierre buscaba `logo.jpg`, que no existe, y salía sin logo. Ahora usa el mismo logo que muestra la aplicación (`logo-aguacol.png`), sin deformarlo.
- **Hecho (21-11-2026):** en el servidor `DEBUG` estaba encendido (no estaba definido): ante un error la app mostraba el detalle técnico. Ahora está apagado en su configuración (`DEBUG=false`): muestra solo «ocurrió un error» y el detalle queda en el registro del servidor.
- La clave inicial del usuario admin está escrita en `backend/repositories/seguridad.py` (solo se usa si el admin no existe). **Se deja así** para emergencias (decisión de la persona dueña, 18-11-2026).

### 2.7 Auditoría del código del 15-11-2026

Plan en cinco etapas en `docs/AUDITORIA_CODIGO_2026-11-15.md`. La etapa 1 está en producción desde el 15-11-2026 (commit 2af619f): corrige cuatro fallas (la hora de Visitas, el selector de inasistencias, el Excel por rango de Reportes y la purga del registro de auditoría) y quita 18 funciones sin uso. Las 81 visitas pasadas con la hora corrida se dejan como están (decisión de la persona dueña, 15-11-2026); las nuevas ya se guardan con la hora correcta.

La etapa 2 quedó hecha el 15-11-2026: un solo ayudante de pantalla por tarea (`frontend/js/ayudantes.js`), cuatro choques de nombres entre archivos resueltos y una prueba guardiana.

La etapa 3 quedó hecha el 15-11-2026. Ahora son pruebas permanentes: funciones sin uso, dependencias circulares, consultas que se caen, SQL con tablas o columnas que no existen y errores de JavaScript en las pantallas. Cada una se comprobó con una falla puesta a propósito. Quedan la etapa 4 (SQL a los repositorios) y la 5 (partir las funciones grandes del cálculo).

Etapa 4, parte 1 (15-11-2026): Flota, Visitas y Llaves ya no consultan la base desde sus routers; sus 31 consultas pasaron a los repositorios sin cambios (un ensayo de 59 pasos dio idéntico antes y después). En los routers quedan 146 de 177; el orden que sigue está en docs/AUDITORIA_CODIGO_2026-11-15.md.

Etapa 4, parte 2 (15-11-2026): Portería y Productos 4 también; sus 20 consultas pasaron a los repositorios sin cambios (ensayo de 48 pasos idéntico antes y después). En los routers quedan 126 de 177. Sigue Cierre, con su propio ensayo porque toca la reapertura de períodos.

Etapa 4, parte 3 (16-11-2026): Cierre también (7 consultas, todas de la reapertura); en los routers quedan 119 de 177.

Etapa 4, parte 4 (16-11-2026): Sync también (7 consultas); en los routers quedan 112 de 177.

Etapa 4, parte 5 (16-11-2026): Empleados, Auth y Turnos (7 consultas); en los routers quedan 105 de 177.

Etapa 4, parte 6 (16-11-2026): Artículo 22 (15 consultas, a un repositorio nuevo); en los routers quedan 90 de 177.

Etapa 4, parte 7 (16-11-2026): Configuración (33 consultas: estados, áreas, cargos y géneros); en los routers quedan 57 de 177, todas de Asistencia, que es lo que sigue.

Etapa 4, parte 8 (16-11-2026): primeras 9 consultas de Asistencia, las de solo lectura (bloqueo por personas sin turno, aviso de cambios, filtro por turno, sin turno, diagnóstico, inasistencias disponibles). En Asistencia quedan 48.

Etapa 4, parte 9 (16-11-2026): compensaciones, intercambios de días y reasignar turno (7 consultas). En Asistencia quedan 42.

Etapa 4, parte 10 (16-11-2026): las marcas manuales (agregar, quitar, borrar las del día y reclasificar; 14 consultas). En Asistencia quedan 28.

Etapa 4, parte 11 (16-11-2026): el relleno masivo y los tramos (6 consultas). En Asistencia quedan 22.

Etapa 4, parte 12 (16-11-2026): asignar turno a una persona, sincronizar en grupo, condonar deuda y reproceso masivo (9 consultas). En Asistencia quedan 14.

Etapa 4, parte 13 (16-11-2026): la ventana de marcas del día (5 consultas). En Asistencia quedan 9: el GPS y las auditorías de la libreta del Art. 25 bis.

Etapa 4, parte 14 (16-11-2026): la libreta del Art. 25 bis (solo sus registros de auditoría y los nombres, sin tocar su lógica) y el GPS. **La etapa 4 quedó terminada:** ningún router consulta la base directo, y una prueba lo revisa en todos, también en los nuevos. Sigue la etapa 5.

Etapa 5 (16-11-2026): plan en 16 piezas en docs/AUDITORIA_CODIGO_2026-11-15.md; cada una se ensaya con el respaldo de producción restaurado en una base aparte del PC, solo para leer (decisión de la persona dueña). Paso 1a hecho: la precarga del recálculo de un período, idéntico en 16.756 días. Paso 1b hecho: la semana de partida de los horarios con rotación, también idéntico. Paso 1c hecho: el cálculo de un día dentro del recorrido, idéntico (también guardando, en la copia de práctica). Paso 1d hecho: el guardado final; el recálculo de un período quedó en 244 líneas (antes 646). Paso 2a hecho: los chequeos de «este día no se calcula» del recálculo de un día (563 → 392 líneas), idéntico. Paso 2b hecho: el turno del día (→ 327 líneas), idéntico. Paso 2c hecho: las marcas ya usadas y la reasignación manual (→ 271 líneas), idéntico. Paso 2d hecho: el final y el guardado; el recálculo de un día quedó en 215 líneas (antes 563). Paso 3a hecho: la ventana de observación del cálculo de un día (`_solve_core`: 820 → 740 líneas), idéntico. Paso 3b hecho: varias marcas (→ 644 líneas), idéntico. Paso 3c hecho (17-11-2026): colación y permisos (→ 577 líneas), idéntico. Paso 3d hecho: una sola marca (→ 508 líneas), idéntico. Paso 3e hecho: atrasos y salidas adelantadas (→ 441 líneas), idéntico. Paso 3f hecho: Bolsa y turnos ordinarios (→ 381 líneas), idéntico. Paso 3g hecho: las reglas de marcaciones (→ 313 líneas), idéntico. Paso 3h hecho: el día sin marcas; el cálculo de un día quedó en 265 líneas (antes 820). **La etapa 5 quedó terminada (18-11-2026):** las tres funciones grandes del cálculo quedaron en piezas con nombre y el resultado no cambió. La copia del respaldo se borró del PC.

**Hecho el 16-11-2026 (decisión de la persona dueña):** se quitaron de la ventana de marcas manuales las casillas antiguas de conducción y espera de Bolsa, y su ruta `/tramos/`. Siempre daban error 500, porque la base nunca tuvo esas columnas. Esos minutos se registran en la libreta del Art. 25 bis, que no se tocó.

**Fallas que ya existían, vistas en el ensayo de la parte 5: arregladas el 16-11-2026** (decisión de la persona dueña):
- Confirmar un cambio de área pendiente daba error 500 (buscaba un dato «area» que la tabla no tiene). Ahora usa el número del área y anota solo la ficha del empleado: el historial queda con la fecha efectiva, sin un registro de más. En producción no había cambios pendientes (0) y nadie la había usado en 30 días.
- Crear o editar un empleado con un área que no existe daba error 500: ahora avisa «El área seleccionada no existe».
- Cambiar un turno que no existe respondía «Turno actualizado correctamente»: ahora «Turno no encontrado», sin tocar días ni áreas.
- Pruebas: `test_fallas_16_11.py` (fallan con el código anterior).

**Rutas sin sesión (16-11-2026):** el historial de sincronizaciones respondía sin iniciar sesión (fechas y cantidades, sin nombres ni RUT); ahora pide sesión y el permiso de ver Configuración o de sincronizar. Una prueba (`test_rutas_con_sesion.py`) revisa todas las rutas: cada una pública lleva su motivo. La prueba de conexión con BioAlba (`/api/sync/test/`), que también respondía sin sesión, ahora pide el permiso de sincronizar (decisión de la persona dueña, 16-11-2026).

**Reabrir un período: arreglado el 18-11-2026** (decisión de la persona dueña). Antes, al reabrir un período la app no desactivaba los demás: en la copia de práctica, después de reabrir dos meses quedaron tres vigentes a la vez. Ahora:
- Al reabrir, solo queda vigente el período que se reabre. Al volver a cerrarlo, la vigencia pasa al mes en curso.
- Se reabre un período a la vez: si ya hay otro abierto que no es el del día de hoy, la app avisa que hay que cerrarlo antes.
- La reapertura sigue siendo por área: otra área del mismo período sí se puede reabrir.
- Prueba: `test_reabrir_un_periodo.py` (falla con el código anterior).

### 2.7 bis Limpieza de restos del desarrollo (15-11-2026, hecha)

- **Servidor:**
  - El registro de la app se corta cada medianoche y guarda 14 días. Antes no se cortaba y había llegado a 614 MB.
  - Se escriben menos avisos de rutina del recálculo, y ante un error ya no se anotan los valores de las variables.
  - Se borraron las copias viejas del archivo de configuración.
  - Los restos de compilación de Docker (18 GB, compartidos con otros proyectos) no se tocaron.
- **GitHub:**
  - Se quitaron una página de prueba que producción mostraba a cualquiera y el mapa fuente del Dashboard.
  - También se quitaron 4 scripts de un solo uso que llevaban nombres de trabajadores.
  - Una prueba (`test_limpieza_entornos.py`) avisa si algo de esto vuelve.

### 2.8 Mapa del código (graphify)

Se ve en Configuración → Mapa del código (solo el súper administrador) y se vuelve a publicar con cada cambio de código (`scripts/publicar_mapa.py`).

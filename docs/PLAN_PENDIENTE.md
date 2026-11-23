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

**21-11-2026:** se validaron las cinco como horas extra. **Decisión de la persona dueña:** las horas extra de un día libre o feriado se tratan igual que cualquier hora extra: el cuadre las reparte (cubren deuda y se pagan hasta el tope de «Pagar hasta») y no se deciden aparte. Antes quedaban fuera del reparto y, al aprobarlas con ✓, se pagaban por fuera del tope. Ensayo con el respaldo: de 102 cuadres abiertos solo cambian las tres personas de Julio de Mantención. Con los topes que se decidieron antes, quedan sin pagar 00:50:29, 00:43:27 y 04:47:00. Si se quiere pagar más, hay que subir el tope en «Ver cuadre».

### 2.2 Horarios

| Horario | Qué falta |
|---|---|
| Tradicional Bodega | **No se cambia** (decisión de la persona dueña, 21-11-2026): trabajar de mañana son casos puntuales, cuando la jefatura cita a alguien algunos días. |
| Planta Mantencion (el primero) | Está inactivo y sin personas (se usa Planta Mantencion 2): no hace falta tocarlo. |

### 2.3 Correo del cierre

Los destinatarios del informe de cierre los carga la persona dueña en Configuración (18-11-2026: es tarea suya, no del desarrollo). El mensaje del cierre ya dice si el correo se envió.

### 2.4 Preinforme con señales para los jefes de área

Propuesta del 18-11-2026, aprobada para Ciclo Inteligente: una sección «Para coordinar antes del cierre» con quién debe horas (atrasos, salidas adelantadas) o tiene inasistencias sin justificar, y cómo recuperarlas antes del cierre. Para Bolsa Flexible se propuso el 21-11-2026 otra forma, porque en Bolsa las horas bajo la meta no se descuentan: quién va bajo la meta (horas que todavía se pueden programar) y quién ya la pasó (desde ahí se pagan como horas extra). **Programado el 21-11-2026** con las dos frases aprobadas: el preinforme trae al final la sección «Para coordinar antes del cierre»; el informe de cierre no la lleva.

### 2.5 Reorganizar el código grande

De la auditoría `docs/AUDITORIA_GRAFO.md` (7-11). Se dejó para después de los cierres, y ese momento ya llegó:

- **#3: hecho** (21-11-2026): `routers/asistencia.py` quedó repartido por tema en 7 archivos, sin cambiar las URL (de 3.853 a 524 líneas). **Plan escrito el 21-11-2026** (etapa 6 de `docs/AUDITORIA_CODIGO_2026-11-15.md`, en 7 pasos con su ensayo). Paso 6a hecho (21-11-2026): GPS y velocidades, rutas idénticas. Paso 6b hecho: la libreta del Art. 25 bis, rutas idénticas. Paso 6c hecho: compensaciones y deuda, rutas idénticas. Paso 6d hecho: período de RR.HH., rutas idénticas. Paso 6e hecho: jornadas especiales y horas extra, rutas idénticas. Paso 6f hecho: marcas manuales y del día, rutas idénticas. Paso 6g hecho: asignaciones y reprocesos, rutas idénticas. **Etapa 6 terminada.**
- **#5:** sacar de `AsistenciaService` lo que no es cálculo (la tabla de Marcaciones y el cierre).
- **#9: hecho** (16 al 18-11-2026, etapa 5 de `docs/AUDITORIA_CODIGO_2026-11-15.md`): las tres funciones quedaron en piezas con nombre y el resultado no cambió.
- **#4:** las «capas al revés», solo explicado.

No arregla errores visibles: da orden para cambiar el código con menos riesgo.

### 2.5 bis Bonos

Revisión del 21-11-2026: el cálculo de bonos usa el mes calendario y no las fechas del período de cierre (los informes de los meses cerrados salen con todos «califica»), el informe no muestra montos, las licencias no se pueden distinguir por bono y el cargo no tiene historial con fecha. Plan por etapas en `docs/PLAN_BONOS.md`, en conversación con la persona dueña. El 22-11-2026 la persona dueña decidió: cualquier justificación se configura por bono; la inasistencia sin justificar hace perder el bono y también se configura; el cambio de labor a mitad de período se paga en proporción a los días en cada labor y se avisa por correo; Mayo a Octubre no se tocan; Productos 4 pasa a ser un bono configurable. Ese mismo día decidió también: se quita la asistencia mínima; el cargo es único (se unen los repetidos y los nombres se ven completos); el informe de cada área muestra todos los bonos que corresponden a sus personas; el correo del cambio de labor va a «Avisos generales». No quedan dudas abiertas. **Hecho (22-11-2026):** con autorización expresa de la persona dueña y respaldo previo, se unificaron en la base los cargos repetidos: queda «AYUDANTE DE BODEGA» y «ASISTENTE FACTURA»; los nombres anteriores quedaron como alias y el cambio está en la auditoría. Los cargos cortados a 20 letras por BioAlba se dejan así. **Etapa B1 hecha (22-11-2026, commit b118d0e):** los bonos se calculan con las fechas del período de cierre en la grilla, el Excel y el informe; el ensayo con el respaldo confirmó que antes el informe de los meses cerrados daba todos «califica» con monto 0 y la grilla inflaba los montos. **Etapa B2 hecha (22-11-2026, commit b0f33a2):** el informe PDF y el Excel de cierre muestran el monto de cada bono, sus totales y, en el PDF, el detalle de los bonos no pagados o pagados en parte; las columnas son los bonos que les corresponden a las personas del área. **Etapa B3a hecha (22-11-2026, commit 13f144c):** cada justificación tiene su efecto en cada bono (cuenta como asistido, descuenta en proporción o hace perder el bono) y cada bono su efecto de la inasistencia sin justificar, todo en la pantalla; se llenó con lo de hoy (ensayo: 0 cambios). Sigue abierto el caso de Bolsa Flexible. **Etapa B3b hecha (22-11-2026, commit be56814):** los cargos de las reglas se eligen de la lista (por su identificador, un cambio de nombre no las rompe), en Configuración → Cargos se puede renombrar y unir cargos, y se quitó la asistencia mínima de la pantalla; ensayo: 0 cambios. **Etapa B3c hecha (22-11-2026, commit dea3dc8):** vista previa del bono antes de guardar (quién lo recibe y cuánto en el período vigente) y aviso cuando dos reglas del mismo bono calzan con la misma persona. **Etapa B3d hecha (22-11-2026, commit bf36034):** 4 Productos tiene su propio bono «4 Productos» (beneficio en especie) configurable en la pantalla y lo lee por su identificador; ensayo: 0 cambios. Pendiente de decidir: la regla de antigüedad de 4 Productos (segundo mes) sigue escrita en el código. **Bolsa (M) hecho (22-11-2026, commit b6ff0f7):** en Bolsa Flexible un día justificado cuenta igual que en Ciclo y se le aplica lo configurado; en el ensayo cambia solo una persona de Bolsa (Logística Tradicional), con Licencia Común en Septiembre a Noviembre (en 4 Productos deja de calificar). **Etapa B4a hecha (22-11-2026, commit 8f1cba9):** historial de cargos con fecha (cada persona con su cargo desde su ingreso) y el bono usa el cargo de cada día; ensayo: 0 cambios. **Etapa B4b hecha (22-11-2026, commit 2373d04):** en la ficha de la persona, pestaña «Historial de cargos» con el botón «Cambiar labor desde una fecha» (muestra antes qué bonos cambian, no deja fechas en períodos cerrados, avisa por correo y queda en la auditoría). **Etapa B5 hecha (22-11-2026, commit b8505bf):** al cerrar se guardan los bonos de cada persona y el informe y el Excel del período cerrado leen lo guardado (al reabrir se borra); Mayo a Octubre siguen calculándose como antes. **Etapa B6 hecha (22-11-2026, commit 3ad6205):** Bolsa por sus dos nombres de tipo, sin «labor requerida» y la lista de bonos por persona con las reglas del cálculo (agrega Supervisor a 3 personas que ya lo cobraban). La antigüedad de 4 Productos pasó a la pantalla (bono «4 Productos» → «Antigüedad mínima», 1 mes; commit 7949140). **El plan de bonos quedó completo.** Los correos de aviso se configuran al final, cuando la persona dueña dé todo por terminado.

### 2.5 ter Jornadas extra en el informe de cierre

**Hecho (23-11-2026, commit d4c5c43):** a pedido de la persona dueña, el informe de cierre en PDF y el preinforme muestran las jornadas extra de monto fijo (las jornadas especiales validadas «como jornada extra»), que antes no aparecían: columna «Jornadas extra» en «A cargar», recuadro arriba, sección «Jornadas extra (monto fijo)» con los días de cada persona, y la línea en el resumen del paso 5 y del correo de cierre. Las jornadas especiales validadas como horas extra y los +2 ya van en las horas extra y no se muestran aparte (decisión de la persona dueña). Ensayo con el respaldo del 23-11-2026: en cada área, las del informe son las mismas que marca la grilla (por ejemplo, Producción en Octubre: 85 en 32 personas). Prueba `test_jornadas_extra_en_informe.py`.

### 2.5 quater Informe de cierre que cabe en la hoja

**Hecho (23-11-2026, commit 313dcd4):** la persona dueña avisó que en el preinforme de Producción (en la vista de la aplicación y en el PDF) la tabla y los recuadros de arriba quedaban cortados: con los montos de los bonos y las jornadas extra la tabla era más ancha que la hoja. Ahora la tabla se ajusta de a poco hasta caber: primero los títulos pasan a dos líneas, después baja la letra, después los nombres largos van en dos líneas, se achica el relleno de las celdas y, como último paso, los montos de bonos van sin «$» (el título del grupo queda «Bonos ($)»). Los recuadros de arriba pasan a otra fila cuando no caben. Si aun así no cupiera, queda un aviso en el registro. Ensayo con el respaldo del 23-11-2026: el preinforme de cada área y tipo de horario de Octubre y Noviembre cabe en la hoja. Prueba `test_informe_cabe_en_la_hoja.py`.

### 2.5 quinquies Bajas del período aparte de la dotación

**Hecho (23-11-2026, commit 9a775b0):** la persona dueña pidió mostrar y contar aparte a quienes se dieron de baja, porque contarlas como dotación engaña, y eligió la propuesta B entre tres. Es baja del período quien tiene su salida decidida (inactiva, «No renovar» o «BAJA: …») con fecha dentro del período; quien se va después fue dotación de ese período, y un término de contrato sin decidir no es baja. Antes el informe marcaba «Inactivo» según el estado de hoy (en Octubre, Producción marcaba a 2 personas que se fueron después) y la grilla no marcaba nada. Ahora, en la grilla, el informe de cierre y el preinforme, las bajas van al final de su horario bajo «Bajas del período», con la fila en gris y el rótulo «Baja dd-mm»; en la grilla, los días después de la salida quedan rayados. El conteo va aparte («12 en dotación · 2 bajas») en los recuadros, en el título de cada horario, en la fila de total, en el paso 5 y en el correo de cierre. Las bajas se pagan y descuentan como el resto, y no reciben el aviso de recuperar horas. Ensayo con el respaldo del 23-11-2026: Producción, 0 bajas en Octubre y 3 en Noviembre; Logística Tradicional, 5 en Octubre; lo que se carga es idéntico con o sin marcar las bajas, y todo cabe en la hoja. Prueba `test_bajas_del_periodo.py`.

### 2.5 sexies Todo cuenta desde la asignación de turno

**Hecho (23-11-2026, commit 36cd8d9):** decisión de la persona dueña: la fecha de ingreso de la ficha es solo referencial (BioAlba la reemplaza por la fecha de creación del usuario en el reloj y, a quien se fue y volvió, le deja la antigua), así que todo cuenta desde la asignación de turno dentro del período configurado. Los bonos en proporción, la meta de la Bolsa Flexible, la antigüedad de 4 Productos y el inicio del historial de cargos ahora parten del inicio del turno continuo vigente en el período (`inicio_turno.py`; un cambio de turno sin corte mantiene el primero, una vuelta después de un corte cuenta desde el turno nuevo). El artículo 22 (excluidos de asistencia, sin turno) recibe siempre 4 Productos, salvo que se dé de baja. Renovar un contrato es «como si nada pasara»: la pantalla de bloqueo ya obliga a decidirlo antes del término. Ensayo con el respaldo del 23-11-2026 (Noviembre): solo cambia el Compromiso de G.G.H. (de $31.429 a $60.000; su ficha dice ingreso 08-11 pero tiene turno desde el 05-10); en 4 Productos califican 86 personas en vez de 78 (las 13 del artículo 22 y G.G.H.), y nadie que calificaba deja de hacerlo. Octubre (cerrado y pagado) no se toca; recalculado hoy, mostraría más Compromiso y Transporte para G.P. y G.G.H.. Pruebas `test_inicio_turno.py`.

Corrección en la base (23-11-2026, autorizada por la persona dueña, con respaldo antes): la asignación de turno de J.A.H. pasó del 02-09 al 02-11-2026 y la de P.A.P. del 16-11 al 17-11-2026, y se borraron sus días anteriores (5 inasistencias y 2 feriados; 1 inasistencia). Ningún mes cerrado tocado. El mismo día, también a pedido de la persona dueña: se deshizo la baja registrada por error a G.P. (vuelve a activo, indefinido, turno sin término), y a J.P.L. se le quitó la baja hasta que llegue su renuncia (activo, contrato hasta el 12-02-2027, turno hasta esa fecha). Una baja anterior con fecha 12-11 le había cortado el turno y borrado sus días, por eso salían inasistencias con libreta registrada; se volvieron a calcular sus días del 13 al 23-11 (los de libreta quedan trabajados; el 20 y el 23-11, sin libreta, como inasistencia).

### 2.5 septies Jornadas extra como tabla

**Hecho (23-11-2026, commit 36cd8d9):** a pedido de la persona dueña, la sección «Jornadas extra (monto fijo)» del informe y el preinforme pasa de lista a tabla: una fila por persona y una columna por cada fecha (día de la semana y fecha completa, con «FERIADO» o «DÍA LIBRE» escrito en el encabezado), con las horas de la jornada en cada celda, y al final jornadas y horas por persona y una fila de total. Si las fechas no caben, la tabla sigue debajo. Prueba `test_jornadas_extra_tabla.py`.

### 2.5 octies Bono semanal Fill Rate

**Hecho (23-11-2026, commit 2636436):** a pedido de la persona dueña, bono nuevo de evaluación semanal para choferes y peonetas. En Configuración → Bonos se elige «Evaluación: semanal, de lunes a domingo» y los horarios que lo tienen; el monto semanal sale de las reglas por cargo (por ejemplo chofer $40.000, peoneta $30.000) y el efecto de cada justificación se configura como en los demás bonos (Descanso Operativo: proporcional, porque la empresa decidió no enviarlo; licencia o inasistencia: pierde). En la grilla, el switch «Fill Rate» muestra cada día de turno como «cumple» (✓) y con un clic se marca «no cumple» (N/C) con un comentario, lo que hace perder la semana completa; en el domingo va el resultado de la semana. Queda registrado quién marcó y en la auditoría. Cada semana se paga en el período donde cae su domingo. Va al informe de cierre y al preinforme como una columna más de «Bonos», con las semanas perdidas o en parte en el detalle de bonos, y se guarda al cerrar como los demás. Probado en la copia de práctica (configurar, marcar y quitar «no cumple», preinforme); ensayo con el respaldo del 23-11-2026: sin el bono creado no cambia ningún monto. Además, todos los bonos (mensuales y semanales) ahora dicen «¿A quién se le paga?»: áreas («todas» o «solo estas») y horarios («todos» o «solo estos»), más las reglas de cargo y contrato. Antes las «áreas asignadas» se guardaban pero el cálculo no las usaba; los bonos que ya existían parten con «todas» y «todos» (sus áreas marcadas quedan guardadas y se activan bono por bono), así que no cambia ningún monto (ensayo de cero diferencias con el respaldo del 23-11-2026). La lista de bonos por persona usa las mismas reglas. Falta que la persona dueña cree el bono «Fill Rate» en Configuración (semanal, solo los horarios de choferes y peonetas, montos por cargo). Prueba `test_bono_semanal_fill_rate.py`.

### 2.5 nonies Ajustes de la vista Fill Rate

**Hecho (23-11-2026, falta subir):** a pedido de la persona dueña, en el switch «Fill Rate» los días que cumplen van en blanco (el bono se gana) y solo se ve lo que cambia la semana (N/C, justificaciones, inasistencias); al final de cada semana hay una columna «Total semana» con su resultado; el clic en un día ya no abre las acciones de asistencia, sino una ventana con «Cumple» y «No cumple» (con comentario). En el bono de producción, Descanso Operativo pasó de proporcional a «cuenta como cumplido» (no es causal de descuento), con respaldo antes. Probado en la copia de práctica. Prueba en `test_bono_semanal_fill_rate.py`.

### 2.6 Deudas técnicas

- **Hecho (22-11-2026):** `backend/tests/test_libreta_en_orden.py` tenía nombres reales de cuatro personas; se cambiaron por nombres inventados (la prueba no cambia). Siguen en el historial de git anterior: borrarlos de ahí exigiría reescribir el historial, que no se hace sin decisión de la persona dueña.

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

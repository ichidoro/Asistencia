# Auditoría del código con el grafo (15-11-2026)

Pedido de la persona dueña: «realiza una auditoría usando el grafo y crea un plan acabado y probado; si eso requiere simulaciones tipo arañas, efecto dominó, hilo rojo, debes realizarlo».

Este documento no lleva nombres de personas. Todo se hizo en solo lectura sobre producción o en copias aparte; nada se cambió en producción para medir.

---

## 1. Cómo se hizo

| Herramienta | Qué hace | Dónde está |
|---|---|---|
| **Grafo** (graphify) | Mapa de 5.109 piezas y 11.736 conexiones del código, armado el 15-11 sobre el commit `284cfeb`. | `backend/mapa_codigo/` (Configuración → Mapa del código) |
| **Efecto dominó** («hilo rojo») | Para una pieza, recorre el grafo hacia atrás nivel por nivel (quién la llama, quién llama a esos…) hasta los endpoints, las pantallas que los piden y las pruebas que la cuidan. | `scripts/efecto_domino.py` |
| **Simulación de copias** | Toma cada copia de un ayudante repetido (mismo nombre en varios archivos), le da las mismas entradas y compara lo que devuelve. | Simulación con el lector Babel (en el ensayo) |
| **Araña de consultas** | Llama cada endpoint de consulta (GET) de la copia de práctica como administrador y anota los que se caen. | `scripts/arana_consultas.py` |
| **Araña de SQL** | Toma cada consulta SQL fija del servidor (también las que guardan), la traduce como la aplicación y le pide a la base que la prepare, sin ejecutarla: detecta tablas o columnas que no existen. | `scripts/revisar_sql.py` |
| **Ensayo aislado** | Los cambios se aplicaron en una copia aparte del código (otra carpeta, sin tocar la de trabajo), con todas las pruebas y otra pasada de la araña. | Copia `Asistencia_ensayo_auditoria` |

**Límites honestos.** El grafo ve quién llama a quién, no si un cálculo está bien. El efecto dominó sobrestima un poco (el grafo no distingue la dirección de algunas conexiones), así que sirve como cota máxima de lo que se puede romper. La araña de consultas solo llama endpoints GET; lo que guarda se revisó con la araña de SQL (527 de 955 llamadas a la base tienen SQL fijo y se pudieron revisar; las armadas con partes variables no).

---

## 2. Fallas encontradas (reales, comprobadas): 4

| # | Falla | Cómo se encontró | Efecto para las personas | Comprobación |
|---|---|---|---|---|
| F1 | **Visitas guardan la hora con UTC-4 fijo.** Desde el cambio a horario de verano (6-09-2026) Chile está en UTC-3: cada visita queda con **una hora menos**. | Simulación de copias: la «hora de Chile» está escrita 6 veces y una de ellas no sigue el cambio de horario. | 81 visitas (43 entradas y 38 salidas) del 7-09 al 10-11 con la hora corrida (por ejemplo, una registrada a las 18:19 figura 17:19). Ninguna quedó a las 23:xx, así que corregirlas no cambiaría su fecha. | Datos de producción: la diferencia con la hora real del servidor es siempre 4 h, también en noviembre. |
| F2 | **El selector de inasistencias siempre falla** («Error consultando inasistencias.» al compensar una inasistencia en Marcaciones). La consulta pide una columna `estado` que la tabla de justificaciones no tiene. | Araña: error 500. | Cualquier persona con una inasistencia: la ventana no carga. | Columna inexistente también en la base de producción. |
| F3 | **Reportes → Excel por rango de fechas siempre falla.** Recibe una lista de filas donde espera la matriz del período. | Araña: error 500. | El botón de Excel de la pantalla Reportes no descarga nada. | Corregido, devuelve un Excel válido con sus 6 hojas para un día, un tramo, 40 días y tres meses (unos 2 s). El permiso por área no cambia: quien no tiene alcance global no puede pedir «Todas» ni otra área. |
| F4 | **La purga semanal del registro de auditoría falla siempre.** Borra según una columna `fecha` que la tabla no tiene (se llama `created_at`). | Araña de SQL. | El registro de auditoría no se recorta a 12 meses. Hoy no se nota (el registro más antiguo es del 29-05-2026); se notaría desde mayo de 2027. | Corregida, la base acepta la consulta traducida. |

## 3. Limpieza confirmada

**16 funciones que nadie usa.** Sin llamadas en el grafo, sin ninguna mención en el código, las pantallas, los scripts ni las pruebas, y con efecto dominó cero (ninguna pieza, endpoint ni pantalla depende de ellas): 520 líneas.

`database.get_table_names`, `database.save_setting`, `events.get_empleado_service_internal`, `AsistenciaRepository.get_cierres_bulk`, `.get_turno_detalle_dia`, `.save_cierre_periodo`, `.toggle_condonacion_deuda`, `calendario.is_feriado`, `flota.get_vehiculo_by_patente`, `hora_extra.get_embudo_he`, `turno.save_raw_log`, `AsistenciaService._apply_rounding`, `.replicar_libreta_chofer`, `bono_service.evaluar_bonos_mes`, `ConfiguracionService.audit_all_assignments`, `EmpleadoService.repair_all_period_inconsistencies`.

Al corregir F3, `AsistenciaService.get_matrix_data_by_range` queda también sin uso, y al quitar `get_embudo_he` queda sin uso `HoraExtraRepository.get_resumen_periodo`, que solo esa función llamaba (efecto dominó en cadena). Total: 18 funciones.

Se descartó `informe_cierre_pdf.draw`: el detector la marcó, pero la llama por dentro la librería de PDF.

## 4. Copias que deberían hacer lo mismo y no lo hacen (simulación)

| Ayudante | Copias | Comportamientos distintos | Lo que se vio | Riesgo |
|---|---:|---:|---|---|
| Escapar texto para HTML (`esc`, `_esc`, `escHtml`) | 25 | 5 | 2 copias no escapan nada si no cargó otro archivo antes; 5 no escapan la comilla simple; 2 muestran «null» cuando no hay valor. | Bajo hoy (ningún texto escapado termina dentro del código de un botón), pero cualquier cambio futuro puede romper una pantalla y no otra. |
| Fecha corta día-mes (`ddmm`) | 5 | 4 | Con una fecha mal formada devuelven «-1-», «undefined-undefined» o la fecha sin cambiar. | Bajo (las fechas vienen bien formadas del servidor). |
| Iniciales para el avatar (`iniciales`) | 5 | 3 | Una pantalla muestra las dos primeras letras del apellido y las demás las iniciales: el mismo avatar se ve distinto según la pantalla. | Solo visual. |
| Minutos a texto (`fmt`) | 5 | 5 | Son funciones distintas con el mismo nombre (fecha, HH:MM:SS, HH:MM redondeado, número). Una redondea 0,5 min a «00:01». | Confusión al mantener; revisar que lo que se muestra a RR.HH. sea HH:MM:SS. |
| Hora de Chile en el servidor (`_now_chile`, `_get_now_local`) | 6 | 2 | Cinco siguen el cambio de horario; la de Visitas no (falla F1). | Real: corregido en el ensayo. |

## 5. Riesgos estructurales (con su efecto dominó)

| Pieza | Tamaño | Efecto dominó | Pruebas que la cuidan |
|---|---|---|---|
| `_solve_core` (cálculo del día) | 820 líneas | 124 piezas, 43 endpoints, 19 pantallas, 10 niveles | 11 archivos de prueba + prueba guardiana de valores fijos |
| `check_fecha_cerrada` (días cerrados) | pequeña | 128 piezas, 46 endpoints, 19 pantallas | 14 archivos de prueba |
| `routers/asistencia.py` | 4.178 líneas, 57 consultas SQL directas | — | 12 de sus 66 endpoints nombrados en pruebas |
| `marcaciones_ui.js` | 9.909 líneas | — | solo pruebas de texto y de pantallas |

**Cobertura:** de 268 endpoints, **233 no los nombra ninguna prueba** (las pruebas cuidan sobre todo los servicios). Por eso F2 y F3 no se habían visto: no había ninguna prueba que pasara por ahí.

---

## 6. El plan, por etapas

Cada etapa se ensaya primero en una copia aparte, con todas las pruebas y con la araña antes y después. Una etapa no empieza si la anterior no quedó en verde.

### Etapa 1: fallas y código muerto (**probada**)

1. Corregir F1, F2, F3 y F4, cada una con su prueba (`backend/tests/test_auditoria_fallas.py`).
2. Quitar las 16 funciones sin uso (y `get_matrix_data_by_range`).
3. Dejar en el proyecto `scripts/efecto_domino.py`, `scripts/arana_consultas.py` y `scripts/revisar_sql.py`.

**Ensayo (15-11-2026):**
- 550 pruebas pasan (4 nuevas) y 5 se saltan. Las 4 nuevas fallan con el código de hoy: detectan las fallas.
- La aplicación arranca con las mismas 290 rutas.
- La hora de Visitas da UTC-3 en noviembre y UTC-4 en julio.
- Araña de consultas: antes 2 endpoints caídos (F2 y F3), después ninguno; 112 respuestas correctas contra 110.
- Araña de SQL: antes 4 consultas rechazadas, después 2, y esas 2 no son fallas (tablas que el código crea justo antes de usarlas).
- El selector de inasistencias sigue la misma regla que el servicio de compensación (una justificación registrada excluye el día), así que hay un solo criterio. Con la condición corregida, un día con un permiso registrado tampoco aparece como inasistencia para compensar.

**Decisión de la persona dueña (15-11-2026):** las 81 visitas pasadas con la hora corrida se dejan como están. La etapa 1 está en producción desde el 15-11-2026 (commit 2af619f).

### Etapa 2: un solo ayudante por tarea (**hecha**)

1. Un archivo común de ayudantes de pantalla (escapar HTML, fecha corta, iniciales, minutos a HH:MM:SS) con el comportamiento de la mayoría y sin «null».
2. Cada pantalla deja su copia y usa el común, un archivo por vez.
3. Una prueba que falle si vuelve a aparecer una copia nueva de esos ayudantes.

**Cómo se prueba:**
- La simulación de copias se corre antes y después: el común tiene que dar lo mismo que la mayoría de las copias para todas las entradas.
- Las diferencias se anotan una por una: son las correcciones.
- Pruebas de pantallas en teléfono, tablet y escritorio, y araña.

**Resultado (15-11-2026, hecha):**
- Nuevo `frontend/js/ayudantes.js` con `window.Ayuda.esc`, `window.Ayuda.ddmm` y `window.Ayuda.iniciales`. Carga antes que todo en `index.html` y `login.html`.
- 43 copias en 24 archivos (escapar HTML, fecha corta e iniciales) pasan a llamar al común.
  - Diferencias que quedan corregidas: ya no se muestra «null», se escapa la comilla simple, y las dos copias que no escapaban nada ahora escapan.
  - Las iniciales salen igual en todas las pantallas.
  - Reincorporación escapaba solo «<» en el mensaje de error de BioAlba.
- Se dejan aparte, a propósito:
  - `_esc` de Marcaciones devuelve tal cual lo que no es texto; así lo usa esa pantalla.
  - `m180AcompIniciales` recibe «Nombre Apellido», que es otra tarea.
  - Las iniciales de la Ficha se arman desde los campos nombre y apellido paterno. No adivinan por la posición de las palabras, que fallaría sin apellido materno o con apellidos de varias palabras.
  - La fecha corta del Dashboard (React) se dejó como estaba.
  - Las funciones `fmt` de minutos son tareas distintas con el mismo nombre (sección 4): no se juntan.
- **Choques de nombres entre archivos** (el archivo que carga último reemplaza al otro sin aviso): se buscaron con un lector de JavaScript y aparecieron 5.
  - `_escAttr` (Configuración y Marcaciones): la de Marcaciones solo escapaba comillas y reemplazaba a la de Configuración. Ahora se llama `_escComillas`.
  - `updateSortIcons` (Horarios y main.js): la de Horarios ahora se llama `updateBulkSortIcons`.
  - `formatExactMinutesToTime`: se quitó la copia de `asistencia.js`, que nunca se usaba porque la de Marcaciones carga después. No cambia lo que se ve.
  - `showToast`: se quitó la copia de Configuración, que nunca se usaba (main.js la reponía al terminar la carga).
  - `nombreTitulo` queda: `auth.js` la define solo si falta, como respaldo para la pantalla de ingreso.
- Arreglo de paso: en Mapa del código, en teléfono, la etiqueta «Desactualizado: …» se salía 25 px del borde. Ahora se parte en dos líneas.
- **Prueba guardiana** `backend/tests/test_ayudantes_unicos.py` (5 pruebas). Falla si:
  - vuelve un escape HTML fuera de `ayudantes.js`;
  - aparece una copia propia de fecha corta o de iniciales;
  - `ayudantes.js` deja de cargar primero;
  - aparece un nombre global repetido entre archivos.
  Se comprobó contra el código anterior: las 5 fallan.
- **Cómo se probó:**
  - 560 pruebas pasan, incluidas las 5 de pantallas contra la copia de práctica.
  - Se recorrieron la pantalla de ingreso, todas las pantallas y las 20 pestañas de Configuración, anotando cada error de JavaScript. La aplicación no dio ninguno.
    - Se vio un solo aviso, en la pestaña Mapa del código: venía de la propia prueba. El navegador automático escribe la sesión en cada marco de la página, también en el marco cerrado del grafo, que no lo permite. No es de la aplicación.
  - La araña no encontró nada nuevo: solo los dos avisos de Nexacol, que no está configurado en el PC.
  - La simulación da un solo comportamiento por ayudante, salvo los que se dejaron aparte.

### Etapa 3: red de seguridad permanente (**hecha**)

1. La araña de consultas como prueba automática contra la copia de práctica, junto a las de pantallas: ningún endpoint de consulta puede devolver 500.
2. La araña de SQL como prueba automática: ninguna consulta fija puede nombrar tablas o columnas que no existen.
3. Pruebas guardianas del mapa: sin funciones nuevas sin uso, sin copias nuevas de ayudantes y sin dependencias circulares.

**Cómo se prueba:** se agrega a propósito una falla de cada tipo en la copia aparte y la prueba tiene que detectarla, como ya hace la autocomprobación de las pruebas de pantallas.

**Resultado (15-11-2026, hecha):**
- **Corren siempre**, sin la app encendida (`backend/tests/test_red_seguridad_codigo.py`). Se calculan desde el código y no desde el mapa publicado, así que avisan antes de subir:
  - Ninguna función del servidor sin uso: una función cuyo nombre aparece una sola vez en todo el código no la llama nadie.
  - Ningún módulo del servidor que se importe en círculo.
  - Las copias de ayudantes ya las cuida `test_ayudantes_unicos.py`, de la etapa 2.
- **Corren con la copia de práctica encendida**, junto a las de pantallas:
  - `test_arana_consultas.py`, araña de consultas: llama los GET y ninguno puede devolver 500 ni quedarse sin responder. Un 503 «no está configurada» (Nexacol en este PC) no cuenta como falla.
  - `test_arana_consultas.py`, araña de SQL: ninguna de las 527 consultas fijas puede nombrar tablas o columnas que no existen. Solo corre contra una base de este PC y en modo solo lectura.
    - Al pasarla a prueba aparecieron 2 avisos que no eran fallas: tablas que el código crea justo antes de usarlas (`registros_anulados` y una tabla temporal de una migración vieja). La araña ahora las reconoce.
  - `test_pantallas.py` ahora también recorre la pantalla de ingreso, cada pantalla y cada pestaña de Configuración, y falla ante cualquier error de JavaScript. Trae su propia autocomprobación: lanza un error a propósito.
  - Ya no se siembra la sesión dentro del marco del grafo, que era lo que causaba el único aviso que aparecía.
- **Autocomprobación.** En una copia aparte se pusieron a propósito 5 fallas:
  - una consulta que se cae;
  - una columna que no existe;
  - una función sin uso;
  - dos módulos en círculo;
  - un error de JavaScript al cargar.

  Las 5 pruebas fallaron, cada una mostrando exactamente la falla puesta, y nada más. Con el código real pasan las 568.

**Cómo correr todo antes de una subida que toque el servidor o las pantallas:** encender la copia de práctica (base en el puerto 5433 y app en el 8001) y correr `PANTALLAS_URL=http://127.0.0.1:8001 PANTALLAS_USUARIO=… PANTALLAS_CLAVE=… .venv\Scripts\python.exe -m pytest backend\tests -q`. Usuario y clave son los de práctica del `.env`.

### Etapa 4: consultas SQL a su lugar

Mover las 177 consultas de los routers a los repositorios, de a un router por vez, empezando por los más chicos. Las URL y las respuestas no cambian.

**Cómo se prueba:**
- Araña antes y después en la copia de práctica, comparando no solo el estado sino también la respuesta.
- Revisar la traducción a PostgreSQL de cada consulta movida.
- Pruebas completas.

**Avance (15-11-2026): parte 1 hecha.** Flota, Visitas y Llaves ya no tienen consultas en sus routers: eran 31, y en todos los routers quedan 146 de 177.
- **Flota:**
  - Usa lo que ya existía: el nombre del área sale de `AreaRepository`, el registro de auditoría de `SeguridadRepository.log_auditoria` y la última marca del vehículo de `FlotaRepository`.
  - Se agregó una sola función: `get_salida_anterior`.
- **Visitas y Llaves:** cada uno tiene ahora su repositorio (`repositories/visitas.py` y `repositories/llaves.py`), con las mismas consultas sin cambios.
  - La lista de llaves activas, que estaba escrita dos veces, ahora es una sola.
- **Cómo se probó:**
  - Como la copia de práctica no tenía datos de estos módulos, se armó un ensayo de 59 pasos con la propia app:
    - altas, cambios y bajas;
    - despachos y retornos;
    - visitas y entregas de llaves;
    - los errores esperados (área que no existe, llave ya entregada, empleado no autorizado);
    - todas las consultas.
  - El ensayo se corrió dos veces con el código anterior: dio lo mismo, así que es estable. Con el código nuevo dio **exactamente lo mismo**: las 59 respuestas, sus códigos y mensajes, y las filas guardadas, incluido el registro de auditoría.
  - También pasan las 569 pruebas, con la araña de consultas, la de SQL y las pantallas.
- **Guardián:** `test_routers_ordenados_sin_consultas_propias` falla si uno de estos routers vuelve a consultar la base directo. Se comprobó contra el código anterior. Cada router que se ordene se suma a su lista.
- **Siguen:** Portería (13), Productos 4, Cierre y Sync (7 cada uno), los chicos (Empleados, Auth y Turnos), Artículo 22 (15), Configuración (33) y, al final, Asistencia (57).

**Avance (15-11-2026): parte 2 hecha.** Portería y Productos 4 ya no tienen consultas en sus routers: eran 20, y en los routers quedan 126 de 177.
- **Auditoría:** los 13 registros de auditoría de los dos módulos ahora pasan por `SeguridadRepository.log_auditoria`, el mismo INSERT de antes.
- **Portería:** las revisiones de nombre o código repetido quedan en `PorteriaRepository`: `get_hallazgo_con_nombre`, `get_ubicacion_con_nombre` y `get_ubicacion_con_codigo`.
- **Productos 4:** el área del empleado al asignar productos queda en `EmpleadoRepository.get_area_actual_para_permisos`.
  - Se dejó **aparte y tal cual**: a diferencia de las otras consultas de ese archivo, no exige que el área esté validada. Juntarla con ellas habría cambiado qué empleados se pueden asignar.
- **Cómo se probó:**
  - Ensayo de 48 pasos. Antes de cada corrida, las tablas se reponen a su estado de fábrica (Portería trae 8 hallazgos y 5 ubicaciones). Recorre:
    - el catálogo de hallazgos y las ubicaciones: altas, nombres y códigos repetidos, cambios y bajas;
    - las rondas: sincronización, repetidas y recientes;
    - los productos, las asignaciones y entregas, y el cierre y la reapertura del mes.
  - Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**, incluidos los 16 registros de auditoría.
  - Se repitió el ensayo de la parte 1: sigue idéntico.
  - Pasan las 569 pruebas.
- **El guardián** ahora reconoce también las consultas hechas con `repo.db.…`, la forma que usaba Portería. Se comprobó contra el Portería anterior.
- **Siguen:**
  - Cierre (7): toca la reapertura de períodos, así que va con su propio ensayo.
  - Sync (7).
  - Los chicos: Empleados, Auth y Turnos.
  - Artículo 22 (15).
  - Configuración (33).
  - Asistencia (57).

**Avance (16-11-2026): parte 3 hecha.** Cierre ya no tiene consultas en su router. Eran 7, todas de la reapertura de un período, y en los routers quedan 119 de 177.
- **Dónde quedó cada consulta:**
  - buscar y borrar el cierre: `AsistenciaRepository` (`get_cierre_by_id` y `eliminar_cierre`), junto a las demás consultas de cierres;
  - el registro de auditoría: `SeguridadRepository.log_auditoria`;
  - volver el período a «abierto» y vigente: `ConfiguracionRepository.reabrir_periodo_rrhh`.
- **La reapertura se movió tal cual.** No se reutilizó `set_periodo_rrhh_activo`, porque esa función desactiva todos los demás períodos y la reapertura no lo hace.
- **Cómo se probó:**
  - El ensayo crea en la copia de práctica sus propios casos, y antes de cada corrida deja las tablas como estaban. Los casos son: dos meses cerrados con su período, un cierre sin período que le corresponda, un cierre que no existe y uno ya reabierto.
  - Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**: respuestas, cierres, períodos y registro de auditoría.
  - Se repitieron los ensayos de las partes 1 y 2. Como pasó la medianoche, solo cambian datos que dependen del día: la fecha de los pedidos, la hora de creación (la base la guarda en UTC) y el «desde» del historial de Visitas, que es hoy menos 7 días. Todo lo demás es idéntico.
  - Pasan las 569 pruebas.
- **Observación, sin cambiar nada (Cierre):** al reabrir un período, el código no desactiva los demás. En el ensayo, después de reabrir dos meses quedaron **tres períodos vigentes a la vez**. Así funcionaba antes de este cambio; queda anotado en el plan para que la persona dueña decida si es lo que se quiere.

**Avance (16-11-2026): parte 4 hecha.** Sync ya no tiene consultas en su router: eran 7, y en los routers quedan 112 de 177.
- **Dónde quedó cada consulta:**
  - los turnos y sus áreas para el asistente de alta: `TurnoRepository` (`get_turnos_para_asistente`, `get_areas_de_los_turnos` y `get_turno_de_area`);
  - los bonos y los de cada área: `ConfiguracionRepository` (`get_bonos_para_asistente` y `get_bonos_de_area`);
  - el historial de sincronizaciones: `SeguridadRepository.get_sync_logs`, donde ya se creaba esa tabla;
  - la prueba de salud de la base: `Database.responde()`.
- **La prueba de salud** hace exactamente lo de antes. No se usó `health_check`, que ya existía, porque si la conexión figura como cerrada no lo intenta.
- **Cómo se probó:**
  - El ensayo crea en la copia de práctica una segunda área sin turno, dos bonos asignados y tres registros de sincronización: uno con detalle, uno con un detalle dañado y uno sin detalle.
  - Llama al asistente de turnos y de bonos con áreas que existen y que no, al historial y a la salud.
  - Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**.
  - Aparte se comprobó que la salud responde «no» cuando la consulta falla.
  - Pasan las 569 pruebas.
- **Un tropiezo del ensayo, ya corregido:**
  - Qué pasó: la primera versión vació la tabla de áreas con `CASCADE`, y eso borró también, **en la copia de práctica**, sus 2 empleados de prueba, su historial de áreas y sus asignaciones de turno.
  - Cómo se arregló: se repusieron con el guion original, con los mismos ids, y el ensayo ahora borra solo lo que él crea.
  - Producción no se tocó: los ensayos solo se conectan al contenedor de práctica.
- **Siguen:**
  - Los chicos: Empleados (3), Auth (2) y Turnos (2).
  - Artículo 22 (15).
  - Configuración (33).
  - Asistencia (57).

**Avance (16-11-2026): parte 5 hecha.** Empleados, Auth y Turnos ya no tienen consultas en sus routers: eran 7, y en los routers quedan 105 de 177.
- **Dónde quedó cada consulta:**
  - el nombre del área por su id: `AreaRepository.get_area_by_id`;
  - un registro del historial de áreas: `EmpleadoRepository.get_historial_area_by_id`;
  - al ingresar, volver a guardar una contraseña en el formato antiguo y anotar el último acceso: `SeguridadRepository.actualizar_password_hash` y `registrar_ultimo_acceso`;
  - las áreas de un turno, que estaba escrita dos veces: `TurnoRepository.get_nombres_areas_del_turno`.
- **Cómo se probó:**
  - Ensayo de 15 pasos:
    - ingresar con una contraseña en el formato antiguo (que se migra a bcrypt), con un usuario inactivo y con una clave equivocada;
    - el alta y el cambio de un empleado con solo el id del área;
    - confirmar un cambio de área;
    - el alta, el cambio y la baja de un turno.
  - Con el código anterior dio lo mismo en dos corridas.
- **El ensayo atrapó un error de este cambio, antes de subirlo:**
  - Qué pasó: al quitar la consulta de «cambiar turno» se borró también la línea `db = …`, que más abajo programaba el recálculo de sus personas. Fallaba en silencio y respondía «recalculo: ninguno».
  - Se corrigió, y con eso el ensayo dio **idéntico**.
  - Se repitieron los cuatro ensayos anteriores: siguen idénticos.
  - Pasan las 573 pruebas.
- **Prueba nueva** `test_nombres_definidos.py`: revisa todo el servidor con el analizador de Python y falla si se usa un nombre que no existe. Se comprobó que habría atrapado el error de Turnos.
- **Fallas que ya existían** (vistas en el ensayo; **arregladas aparte el 16-11-2026**, con `test_fallas_16_11.py`; ver el plan):
  - **Confirmar un cambio de área pendiente da error 500.** El código lee `pendiente['area']`, pero esa tabla no tiene esa columna, solo `area_id` (`KeyError: 'area'`).
  - **Crear o editar un empleado con un área que no existe da error 500** en vez de un aviso: la base rechaza el área y nadie lo maneja.
  - **Cambiar un turno que no existe responde «Turno actualizado correctamente».**
- **Siguen:**
  - Artículo 22 (15).
  - Configuración (33).
  - Asistencia (57).

**Avance (16-11-2026): parte 6 hecha.** Artículo 22 ya no tiene consultas en su router: eran 15, y en los routers quedan 90 de 177.
- **Dónde quedó:** todo pasó a un repositorio nuevo, `repositories/articulo22.py`, con las mismas consultas sin cambios.
- **Lo que se ordenó de paso:**
  - La lista de empleados con Artículo 22 estaba escrita dos veces (una sin la columna «activo»). Ahora es una sola. Las pantallas no usan esa columna, así que no cambia nada de lo que muestran.
  - Los filtros del historial y del Excel se arman en un solo lugar, en el mismo orden que antes.
- **Cómo se probó:**
  - El ensayo crea en la copia de práctica un empleado con Artículo 22 y otro sin él, con marcas de otros días:
    - un día con salida a almorzar;
    - uno que cruza la medianoche;
    - uno con solo una salida;
    - uno normal.
  - Recorre 18 pasos: la lista de empleados, marcar (con errores, con el doble clic de menos de 5 segundos y con la salida que se anota en el día de la entrada), el estado del día, el historial con sus filtros y el resumen, y el Excel con sus errores.
  - Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**, Excel incluido. Lo único distinto es la hora real de las marcas de hoy en la hoja «Resumen por día».
  - Pasan las 577 pruebas.
- **Siguen:**
  - Configuración (33).
  - Asistencia (57).

**Avance (16-11-2026): parte 7 hecha.** Configuración ya no tiene consultas en su router: eran 33, y en los routers quedan 57 de 177, todas de Asistencia.
- **Dónde quedó cada cosa:** cada consulta fue al repositorio de su tabla.
  - Los estados de asistencia: `ConfiguracionRepository`, donde ya se creaba esa tabla. La lista de «otros estados activos», que estaba dos veces, ahora es una sola.
  - Las áreas: `AreaRepository`, con los bloqueos que impiden borrar un área que tiene empleados, marcas, jornadas u horas extra en su historia.
  - Los cargos: `CargoRepository`.
  - Borrar las jornadas y horas extra de una persona: `AsistenciaRepository`.
  - Los géneros: `EmpleadoRepository`.
  - Los 5 avisos a la auditoría: `SeguridadRepository.log_auditoria`.
- **Una función que ya existía no se reutilizó, porque no hace lo mismo:** `get_periodo_rrhh_activo` corre antes un auto-arreglo de períodos. Para el período vigente se agregó `get_fechas_periodo_vigente`, que solo lee, como antes.
- **Cómo se probó:**
  - El ensayo tiene 33 pasos.
    - Usa áreas, cargos y empleados propios del ensayo.
    - Al terminar, deja el estado PERMISO exactamente como estaba.
  - Recorre:
    - los estados: listar, los errores (no existe, campo inválido, sigla repetida, color inválido), cambiar, desactivar y activar;
    - las áreas: crear (repetida, con otras mayúsculas, igual a un alias, vacía), flota, y borrar con cada bloqueo (empleados, marcas, jornadas, horas extra) hasta que se puede;
    - los cargos: crear con los mismos errores, y marcarlo y desmarcarlo como Artículo 22;
    - los géneros.
  - **Marcar un cargo como Artículo 22 borra datos**, así que se comprobó en detalle. Borra las jornadas y horas extra del período vigente de los empleados manuales con ese cargo. No toca las de otros meses ni las del empleado sincronizado.
  - Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**, incluidos lo que se borra y el registro de auditoría.
  - Se repitieron los seis ensayos anteriores: siguen idénticos.
  - Pasan las 577 pruebas.
- **Sigue:** Asistencia (57). Es el más grande y el más delicado, porque toca el cálculo.

**Avance (16-11-2026): parte 8 hecha, la primera de Asistencia.** Se movieron sin cambios 9 consultas de solo lectura; en el router de Asistencia quedan 48. Son estas:
- El bloqueo por personas con marcas y sin turno: `AsistenciaRepository.get_anomalias_de_bloqueo`.
- El aviso de «hay cambios» de la grilla: `get_ultimo_cambio` y `get_resumen_marcas_crudas`.
- Las inasistencias que se pueden compensar y la justificación de un día: `get_inasistencias_sin_consumir` y `get_justificacion_del_dia`.
- Los empleados de un turno en el filtro: `EmpleadoRepository.get_activos_del_turno`.
- Los empleados sin turno: `get_activos_sin_turno`.
- El diagnóstico por área: `contar_sin_turno_en_area`.
- El RUT para la primera marcación: `get_rut`.

Quedan para otra parte, porque el servidor se conecta antes a Nexacol o a BioAlba (en la copia de práctica no hay conexión) y se prueban de otra forma: la patente propuesta de la libreta, las velocidades de los choferes y los nombres de la libreta.

**Cómo se probó:**
- El ensayo crea en la copia de práctica tres empleados de ensayo:
  - uno sin turno y con marcas;
  - uno con turno y con inasistencias, de las cuales una está cubierta por una licencia, una ya está compensada y una es una «FALTA»;
  - uno sin turno y sin marcas.
- Recorre 16 pasos: el bloqueo de este mes, de otro mes y con una fecha mala; el aviso de cambios con y sin área; el filtro por turno; los sin turno; el diagnóstico de dos meses; las inasistencias con y sin día de origen; y los «no encontrado».
- Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**. Pasan las 577 pruebas.

**Ajustes en las pruebas:**
- La prueba de la etapa 1 sobre las justificaciones ahora lee la consulta desde su nuevo lugar, el repositorio. La condición que revisa es la misma.
- Un guardián nuevo, `test_funciones_ordenadas_sin_consultas_propias`, vigila función por función las que ya se ordenaron. Se comprobó contra el código anterior.

**Avance (16-11-2026): parte 9 hecha.** Se movieron 7 consultas más de Asistencia: compensaciones, intercambios de días y reasignar turno. En Asistencia quedan 42 (según el mapa).
- **Dónde quedaron:**
  - Buscar una compensación y un intercambio por su número: `AsistenciaRepository.get_compensacion_by_id` y `get_intercambio_by_id`.
  - El tipo de programación del turno de la persona: `TurnoRepository.get_tipo_programacion_ultima_asignacion`. Con ese dato se impide reasignar a quien está en Bolsa.
  - Los 3 avisos a la auditoría: `SeguridadRepository.log_auditoria`.
- **La prueba de nombres sin definir atrapó un error de este cambio antes de subirlo:** el router no tenía importado `SeguridadRepository` arriba. Como esos avisos están dentro de un `try`, la auditoría habría fallado sin que nadie lo notara. Se corrigió.
- **Cómo se probó:**
  - El ensayo crea un empleado de ensayo con turno, 3 horas extra aprobadas el lunes, una inasistencia el martes y marcas el jueves.
  - Recorre 11 pasos:
    - compensaciones: empleado que no existe, saldo insuficiente, una compensación de 60 minutos y su borrado;
    - intercambios: uno que no existe, y uno creado para el ensayo y borrado;
    - reasignar turno: empleado que no existe, un empleado de Bolsa, y dos reasignaciones.
  - Compara también lo guardado: los días recalculados, las marcas, las compensaciones, los intercambios y los 3 registros de auditoría.
  - Con el código anterior dio lo mismo en dos corridas; con el nuevo, **idéntico**, auditoría incluida.
  - Pasan las 578 pruebas.

### Etapa 5: partir las funciones gigantes del cálculo (la más delicada)

`_solve_core`, `reprocesar_periodo_empleado` y `procesar_empleado_dia`, en pasos con nombre, sin cambiar ningún resultado. Es el punto #9 de `docs/AUDITORIA_GRAFO.md`.

**Cómo se prueba, en cada paso:**
- La prueba guardiana de valores fijos en verde.
- Un ensayo con los días reales del período abierto, en memoria (`collect_only`, sin guardar), que tiene que dar **0 diferencias** contra lo guardado.
- Revisar contra `backend/docs/REGLAS_ASISTENCIA.md`.

---

## 7. Lo que no promete este plan

- No asegura que no haya fallas de cálculo: eso lo cuidan las pruebas del cálculo, la prueba guardiana y los ensayos con datos reales.
- Las arañas no ejecutan lo que guarda: revisan que el SQL sea válido, no que el resultado sea el correcto. Para probar los guardados de punta a punta haría falta una base de práctica con datos de ejemplo que se pueda borrar después de cada pasada.

# Auditoría de la estructura del código (con el grafo de graphify)

Hecha el 7-11-2026. **No se cambió nada del código.** Es un análisis de solo lectura.

**De dónde salen los datos**

- El grafo de `graphify-out/`, construido sobre el commit `48c4485`. Después de ese commit solo cambiaron `.gitignore`, `.graphifyignore` y `CLAUDE.md`, así que el grafo corresponde al código actual.
- El grafo tiene 4.644 piezas (nodos) y 10.828 relaciones. De ellas, 9.218 se leyeron directamente del código y 1.609 son *inferidas*, es decir, el programa las supuso.
- Revisé en el código real lo que el grafo sugería. También medí tamaños, funciones largas y dependencias entre archivos con scripts que solo leen.

**Lo que el grafo no ve.** No ve las llamadas del frontend al backend por URL, los `onclick` escritos dentro del HTML ni las llamadas armadas en tiempo de ejecución. Por eso «sin conexiones en el grafo» no significa «sin uso». Cada caso lo revisé con una búsqueda en todo el proyecto.

---

## 1. Piezas con demasiadas responsabilidades

### SecurityContext: falsa alarma, no conviene repartirlo

Es la pieza con más conexiones del grafo (282), pero no es porque haga muchas cosas. Es una ficha con los datos del usuario conectado: quién es, su rol, sus áreas y sus permisos. Tiene 6 funciones pequeñas que responden «¿puede ver esto?» o «¿tiene acceso a esta área?», y todo el archivo (`backend/core/security.py`) mide 197 líneas.

Tiene tantas conexiones porque **cada endpoint la recibe** para revisar permisos: hay unas 276 apariciones de `: SecurityContext` en los routers. Funciona como una credencial de acceso: todos la usan, pero hace una sola cosa. Repartirla no aporta nada.

### Otras dos «piezas centrales» que en realidad son errores del grafo

En la lista de las 10 piezas más conectadas aparecen `post()` (94 conexiones) y `e()` (69). Las dos son funciones pequeñitas de dos archivos de prueba. El grafo las confundió con código real (ver sección 3), así que no hay nada que corregir en ellas.

### Las que sí tienen demasiadas responsabilidades

| Pieza | Tamaño | Qué mezcla | ¿Conviene repartirla? |
|---|---|---|---|
| **`AsistenciaService`** (`services/asistencia_service.py`) | 32 funciones, 3.511 líneas | Mezcla seis temas: (a) el cálculo del día y del período; (b) la validación de jornadas especiales y llamados; (c) los datos de la tabla de Marcaciones para la pantalla; (d) el cierre de período; (e) la libreta de 180 h (purgar y replicar al acompañante); (f) la aprobación de horas extra. Varias funciones son enormes: `reprocesar_periodo_empleado` tiene 635 líneas, `procesar_empleado_dia` 579 y `get_matrix_data_with_projections` 512. | **Sí, pero por partes.** Primero conviene sacar lo que no es cálculo, como la tabla de pantalla y el cierre. El cálculo en sí queda para el final. |
| **`routers/asistencia.py`** | 4.445 líneas, 103 funciones | Endpoints de temas muy distintos: libreta de 180 h, horas extra, jornadas especiales, marcas manuales, reproceso, OCR de libretas. Además tiene **69 consultas SQL escritas directamente en el router**, sin pasar por los servicios. | **Sí.** Es lo más fácil de repartir por tema sin cambiar lo que hace. |
| **`quantum_matrix_engine.py`** (el motor) | 3.020 líneas | El archivo está bien ordenado en clases: una para la colación, otra para la elección de semana, otra para las justificaciones, etc. El problema es una sola función, **`_solve_core`, de 1.023 líneas**: es el corazón del cálculo y es muy difícil de leer o probar por partes. | **A largo plazo sí, pero con mucho cuidado.** Es lo más delicado del sistema. Existe una prueba guardiana (`test_guardian_valores_fijos.py`) que avisa si cambia algún resultado, y es la red de seguridad para cualquier cambio. |
| **`ConfiguracionService`** y **`ConfiguracionRepository`** | 43 y 46 funciones | Mezclan seis temas: bonos, justificaciones, ajustes, avisos por correo, pagadores y períodos de RRHH. La mayoría de las funciones del servicio miden 2 líneas: solo pasan la llamada al repositorio. La función `init_tables`, que crea las tablas, mide 442 líneas. | **Es opcional.** Son grandes pero simples, así que repartirlas da orden y poco más. |
| **`AsistenciaRepository`** | 47 funciones | Además de la asistencia, maneja la libreta de 180 h, los intercambios, las compensaciones, los viajes largos y los cierres. | Es opcional y va junto con lo anterior. |
| **`report_service._generate_excel_workbook`** | Una función de 870 líneas | Arma todo el Excel en una sola función. | Sí, si se vuelve a tocar el Excel. |
| **`sync_service.sync_marcaciones`** | Una función de 695 líneas | La lectura de marcas desde los relojes. | Solo si hay que cambiarla. |
| **Frontend** | `marcaciones_ui.js` 9.948 líneas, `marcaciones_manuales.js` 5.458, `index.html` 4.563 | Pantallas enteras en un solo archivo. | Sí, pero es mucho trabajo y casi no hay pruebas automáticas de pantallas. |

---

## 2. Código que parece no usarse

**Piezas con cero conexiones en el grafo: 4, y ninguna es código muerto.**

- `backend/models/__init__.py`: solo tiene una línea de descripción. Es normal que exista.
- Tres ventanas de `index.html`: la de progreso de recálculo (`modal-reproceso-progreso`), la de carga por lotes (`batch-loading-overlay`) y la de inasistencias para reasignar (`modalSelectorInasistencias`). **Se usan las tres**: `marcaciones_ui.js`, `main.js` y `marcaciones_manuales.js` las abren por su `id`. El grafo no ve esa conexión.

**Funciones a las que el grafo no les ve ninguna llamada: 179**, sin contar pruebas ni bibliotecas. Las busqué por nombre en todo el proyecto:

- **126 sí se usan.** El grafo no vio la llamada, casi siempre porque viene de un `onclick` en el HTML o de otro archivo JS.
- **17 son funciones especiales de Python** (`__init__`, `__aexit__`), que Python llama solo.
- **36 aparecen únicamente donde se definen.** Nadie las llama en el proyecto, y son candidatas reales a borrarse:

| Dónde | Funciones |
|---|---|
| `core/config.py` | `db_url`, `is_production` |
| `core/database.py` | `is_connected`, `fetchone` |
| `core/events.py` | `on_startup`, `on_shutdown`. Su comentario dice «compatibilidad»: son una versión antigua del arranque. |
| `core/login_limiter.py` | `reiniciar_todo` |
| `models/empleado.py` | `from_dict` |
| `repositories/asistencia.py` | `get_raw_logs_summary` |
| `repositories/cargo.py` | `get_all_cargos` |
| `repositories/configuracion.py` | `get_justificacion_activa`, `close_asignaciones`, `delete_today_asignaciones`, `get_active_asignaciones`, `get_justificaciones_periodo` |
| `repositories/empleado.py` | `get_area_at_date`, `get_ruts_by_areas` |
| `repositories/hora_extra.py` | `get_by_periodo`, `get_por_empleado_periodo` |
| `routers/flota.py` | `_diff_minutes` |
| `scraper/bioalba_scraper.py` | `_clean` |
| `services/asistencia_service.py` ⚠️ | `get_cached_turno_dia`, `_empty_list_coro`, `asignacion_valida` |
| `services/quantum_matrix_engine.py` ⚠️ | `unwrap_overnight_span` |
| `frontend/js/configuracion_ui.js` | `editTipoJ` |
| `frontend/js/main.js` | `setSyncSpeed` |
| `frontend/js/marcaciones_manuales.js` | `activarRecorteImagen`, `m180EsSuperAdmin` |
| `frontend/js/marcaciones_ui.js` | `generateMonthOptions`, `generateYearOptions`, `_getEstadoIcon`, `_getEstadoNombre`, `getStatusHEBadgeClass`, `mostrarSelectorPeriodosParaCierre`, `renderBonoStatus` |

⚠️ = está en un archivo del cálculo de asistencia. Como nadie llama a estas funciones, borrarlas no cambia ningún resultado, pero igual conviene correr la prueba guardiana después.

**Antes de borrar, revisar cada una.** Una función puede llamarse desde fuera del proyecto, por ejemplo desde la consola del navegador o desde un script del servidor que no esté en git. Esta auditoría tampoco revisó endpoints que el frontend ya no llama, porque el grafo no conecta las URL del frontend con el backend.

---

## 3. Relaciones inferidas: cuáles confirmar y cuáles son falsas

Las 1.609 relaciones inferidas se reparten así:

| Tipo | Cantidad | ¿Confiables? |
|---|---:|---|
| «Usa X» porque una función recibe X como parámetro con su tipo escrito | 471 | **Sí.** Salen de lo escrito en el código. Por ejemplo, las 256 conexiones de `SecurityContext` las confirmé contando en los routers. |
| «Usa X» sin parámetro escrito | 269 | Probables. Son funciones que crean o reciben ese servicio. |
| «Llama a X» con nombre único en el proyecto | 450 | **Parecen correctas.** Revisé 15 al azar por nombre y todas tienen sentido, por ejemplo «crear viaje largo → reprocesar período del empleado». No las abrí una por una. |
| «Llama a X» cuando hay varias funciones con ese nombre | 353 | **Hay que confirmarlas.** El grafo pudo elegir la equivocada. Los nombres más repetidos son `get_by_id` (35), `init_tables` (9), `procesar_empleado_dia` (9) y `get_all_bonos` (6). |
| Relaciones de ideas entre documentos («se parece a», «está relacionado con») | 32 | Sirven poco para el código. |

### Falsas confirmadas: 162 conexiones del código real hacia funciones de prueba

El código real nunca llama a funciones de prueba, así que estas conexiones son todas falsas:

- **67 llamadas a `e()`**. En `test_gps_entregas.py` hay una función auxiliar llamada `e`. El grafo la confundió con la variable `e` de `except Exception as e`, que aparece en todo el backend. Por eso `e()` sale entre las 10 piezas «más conectadas».
- **93 referencias a `post()`**. En `test_libreta_en_orden.py` hay una función auxiliar llamada `post`. El grafo la confundió con `@router.post(...)`, que marca cada endpoint POST.
- **2 llamadas a `.sql()`**, una función de un archivo de prueba, desde `core/database.py`.

### Relaciones de ideas que no aportan o son dudosas

- «Tooltips de Marcaciones» se parece a «Tarjeta flotante de parada»: solo se parecen en que ambos muestran una tarjeta al pasar el mouse.
- «Tabla del GPS (`m180GpsTabla`)» se parece al «Simulador de la regleta del manual»: son cosas distintas.
- La relación entre el «Manual de 180 h» y «Cero menciones del Art. 25 bis en la interfaz» la marcó el propio grafo como dudosa.

### Las que vale la pena confirmar, porque tocan el cálculo

- Qué endpoints disparan un recálculo, es decir, qué llama a `reprocesar_periodo_empleado`, `procesar_periodo` y `procesar_empleado_dia`. Las 9 llamadas a `procesar_empleado_dia` están entre las de nombre repetido, porque cuatro archivos de prueba tienen su propia versión de mentira con el mismo nombre.
- «Colación legal de 30 minutos (Art. 34)» está relacionada con «Colación automática del motor (`AutoMealOperator`)». Es plausible, y si es correcta une una regla legal con el cálculo. Habría que confirmarla en `REGLAS_ASISTENCIA.md`.

---

## 4. Bucles o dependencias cruzadas

**No hay bucles de imports en el backend.** Lo revisé dos veces sobre todos los archivos Python:

- con los imports del inicio de cada archivo;
- sumando los imports escritos dentro de funciones, que es donde suelen esconderse los bucles.

En las dos revisiones salieron cero bucles.

**Sí hay «capas al revés»**: una pieza de abajo que depende de una de arriba. Hoy no causan errores, pero son el lugar por donde podría aparecer un bucle en el futuro.

| De | Hacia | Comentario |
|---|---|---|
| `core/events.py` | 11 repositorios y 7 servicios | Es el arranque de la aplicación y conecta todo. Es aceptable, pero hace que `core` dependa de todo el sistema. |
| `core/security.py` | `repositories/seguridad.py` | Lee los permisos del usuario. Es aceptable. |
| `repositories/configuracion.py` | `services/libreta_revision.py` | El import está escrito dentro de una función, lo que suele hacerse para esquivar un bucle. |
| `repositories/entrega_ubicaciones.py` | `services/gps_nexacol.py` | Un repositorio usa un servicio. |
| `repositories/reglas_marcas.py` | `services/reglas_marcas_def.py` | Un repositorio usa las definiciones de las reglas de marcaciones. |
| `schemas/turno.py` | `services/libreta_corte.py` | Un esquema usa un servicio, también con el import dentro de una función. |

**El frontend no se pudo revisar por bucles.** Sus archivos JS se comunican con funciones globales y el grafo no sabe en qué orden se cargan.

---

## 5. Lo que recomiendo cambiar

Están ordenados de mejor a peor relación entre lo que se gana y lo que cuesta. La última columna indica si el cambio toca los cálculos de asistencia.

| # | Cambio | Qué gano | Riesgo | Trabajo | ¿Toca los cálculos? |
|---|---|---|---|---|---|
| 1 | Cambiar el nombre de las funciones auxiliares `e` y `post` en esas dos pruebas por nombres claros, y regenerar el grafo. | El grafo deja de mostrar 162 conexiones falsas y dos «piezas centrales» que no existen. | Muy bajo: solo cambian pruebas. | Muy poco (minutos). | No |
| 2 | Borrar las 36 funciones que nadie llama, después de revisarlas una por una. | Menos código que leer y mantener. | Bajo: la búsqueda confirma que nadie las usa. | Poco | Mueve código del cálculo sin cambiar resultados: 4 de las funciones están en archivos del cálculo (⚠️). Correr la prueba guardiana. |
| 3 | Repartir `routers/asistencia.py` en 4 o 5 archivos por tema (libreta 180 h, horas extra, jornadas especiales, marcas manuales, reproceso), moviendo los endpoints sin cambiarlos. | El archivo más grande del backend queda fácil de recorrer, y los cambios futuros tocan menos líneas. | Bajo a medio: las URL deben quedar idénticas. | Medio | No, si solo se mueven los endpoints |
| 4 | Corregir las 4 «capas al revés» de repositorios y esquemas, llevando lo compartido (por ejemplo, las definiciones de reglas o el corte de libreta) a un lugar común. | Se evita que aparezcan bucles más adelante. | Bajo | Poco a medio | Mueve código del cálculo sin cambiarlo (`reglas_marcas_def`, `libreta_corte`) |
| 5 | Sacar de `AsistenciaService` lo que no es cálculo: los datos de la tabla de Marcaciones y el cierre de período. | El servicio central baja de 3.500 a unas 2.700 líneas y queda más claro qué es cálculo y qué no. | Medio | Medio a alto | No en lo que se mueve. Revisar si `get_matrix_data_with_projections` calcula algo propio. |
| 6 | Llevar a repositorios las 69 consultas SQL de `routers/asistencia.py` y las 33 de `routers/configuracion.py`. | Todo el SQL en un solo lugar, más fácil de revisar con la traducción a PostgreSQL. | Medio: hay que revisar la traducción en `sql_compat.py`. | Alto | En parte: algunas consultas cambian estados de jornadas y llamados |
| 7 | Repartir `ConfiguracionService` y `ConfiguracionRepository` por tema. | Orden | Bajo | Medio | En parte: las justificaciones y los períodos de RRHH influyen en el cálculo |
| 8 | Repartir `marcaciones_ui.js` (casi 10.000 líneas) y `marcaciones_manuales.js`. | El frontend queda más fácil de cambiar. | Medio: usa funciones globales y casi no hay pruebas de pantallas. | Alto | No |
| 9 | Partir `_solve_core` (1.023 líneas), `procesar_empleado_dia` y `reprocesar_periodo_empleado` en pasos con nombre. | Es la mayor ganancia a largo plazo: el cálculo se podría leer y probar por partes. | **Alto**: cualquier error cambia horas y estados de días reales. | Alto | **Sí, de lleno.** Hacerlo al final, en pasos pequeños, con la prueba guardiana en verde y contrastando con `REGLAS_ASISTENCIA.md`. |

**Por dónde empezaría:** por el 1, el 2 y el 4, que son baratos y casi sin riesgo, y después por el 3. El 9 lo dejaría para cuando no haya cierres de período urgentes, porque es el único que puede cambiar resultados de asistencia.

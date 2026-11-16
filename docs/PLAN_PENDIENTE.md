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

La etapa 2 quedó hecha el 15-11-2026: un solo ayudante de pantalla por tarea (`frontend/js/ayudantes.js`), cuatro choques de nombres entre archivos resueltos y una prueba guardiana.

La etapa 3 quedó hecha el 15-11-2026. Ahora son pruebas permanentes: funciones sin uso, dependencias circulares, consultas que se caen, SQL con tablas o columnas que no existen y errores de JavaScript en las pantallas. Cada una se comprobó con una falla puesta a propósito. Quedan la etapa 4 (SQL a los repositorios) y la 5 (partir las funciones grandes del cálculo).

Etapa 4, parte 1 (15-11-2026): Flota, Visitas y Llaves ya no consultan la base desde sus routers; sus 31 consultas pasaron a los repositorios sin cambios (un ensayo de 59 pasos dio idéntico antes y después). En los routers quedan 146 de 177; el orden que sigue está en docs/AUDITORIA_CODIGO_2026-11-15.md.

Etapa 4, parte 2 (15-11-2026): Portería y Productos 4 también; sus 20 consultas pasaron a los repositorios sin cambios (ensayo de 48 pasos idéntico antes y después). En los routers quedan 126 de 177. Sigue Cierre, con su propio ensayo porque toca la reapertura de períodos.

Etapa 4, parte 3 (16-11-2026): Cierre también (7 consultas, todas de la reapertura); en los routers quedan 119 de 177.

Etapa 4, parte 4 (16-11-2026): Sync también (7 consultas); en los routers quedan 112 de 177. Siguen Empleados, Auth y Turnos, después Artículo 22, Configuración y Asistencia.

**Rutas sin sesión (16-11-2026):** el historial de sincronizaciones respondía sin iniciar sesión (fechas y cantidades, sin nombres ni RUT); ahora pide sesión y el permiso de ver Configuración o de sincronizar. Una prueba (`test_rutas_con_sesion.py`) revisa todas las rutas: cada una pública lleva su motivo. La prueba de conexión con BioAlba (`/api/sync/test/`), que también respondía sin sesión, ahora pide el permiso de sincronizar (decisión de la persona dueña, 16-11-2026).

**Para decidir (visto en el ensayo de Cierre, sin cambiar nada):** al reabrir un período cerrado, la app lo marca vigente pero no desactiva los demás. En la copia de práctica, después de reabrir dos meses quedaron tres períodos vigentes a la vez. ¿Es lo que se quiere o al reabrir solo debería quedar vigente el período reabierto (o el mes en curso)?

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

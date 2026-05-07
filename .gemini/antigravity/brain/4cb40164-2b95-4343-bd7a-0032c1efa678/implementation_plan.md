# Plan RBAC v2 — Actualizado con Auditoría de Interconexión Total

> **Versión:** 3.0 | **Auditado:** 2026-05-07 (Re-auditoría iteración 2)  
> Expande el sistema de 18 → 28 permisos. Incorpora 10 correcciones descubiertas por 2 rondas de Auditoría de Interconexión Total.

---

## Diagnóstico: Por qué el sistema actual es insuficiente

El sistema actual tiene **solo 18 permisos** para una aplicación con **más de 60 acciones distintas** repartidas en 6 módulos. El resultado: la granularidad es tan gruesa que no existe control real. Un "Jefe de Área" o bien tiene todo o no tiene nada dentro de cada módulo.

---

## Inventario Completo de Acciones por Módulo

### 🟢 MÓDULO: Dashboard
| Acción | Descripción | Permiso propuesto |
|--------|-------------|-------------------|
| Ver KPIs | Ver métricas diarias, gráficos, top infractores | *(libre — sin permiso, todos lo ven)* |
| Filtrar por área | Usar los filtros de área y fecha | *(libre)* |

**Conclusión:** No necesita permisos. Es visualización pública para cualquier usuario autenticado.

---

### 🟡 MÓDULO: Empleados
| Acción | Descripción | Permiso propuesto |
|--------|-------------|-------------------|
| Ver lista empleados | Acceder al módulo y ver la tabla | `empleados.ver` |
| Crear empleado | Botón "Nuevo Empleado" | `empleados.crear` |
| Editar empleado | Botón editar en la fila | `empleados.editar` |
| Eliminar empleado | Botón rojo eliminar en la fila | `empleados.eliminar` |
| Reincorporar empleado | Botón reactivar (inactivos) | `empleados.reincorporar` |
| Cambiar turno de empleado | Botón cambiar horario en la fila | `empleados.horarios` |
| Ver pestanas Contratos/Cumpleanos/Turnos | Solo lectura | `empleados.ver` *(incluido)* |
| Asignacion Masiva Ver/Ejecutar | Pestana + boton asignar masivo | `empleados.horarios` |
| Ver Bonos Asignados (Matrix) | Ver que bonos tiene cada empleado | `empleados.bonos` |
| Sincronizar Empleados BioAlba | Boton en el header | `empleados.sincronizar_biometrico` |

---

### 🟠 MÓDULO: Marcaciones
| Acción | Descripción | Permiso propuesto |
|--------|-------------|-------------------|
| Ver grilla de asistencia | Acceder al modulo y ver matriz | `marcaciones.ver` |
| Filtrar (area, horario, empleado) | Usar filtros para cargar datos | `marcaciones.ver` *(incluido)* |
| Editar marcacion manual | Clic en celda - agregar/modificar hora | `marcaciones.editar` |
| Agregar justificacion | En popover de celda - asignar tipo justificacion | `marcaciones.justificar` *(nuevo)* |
| Sugerir/Aprobar horas extras | Boton en grilla para proponer o aprobar HE | `marcaciones.horas_extras` |
| Procesar/Reprocesar periodo | Boton engranaje en toolbar de marcaciones | `marcaciones.procesar` |
| Sincronizar BioAlba (marcaciones) | Boton sincronizar en toolbar de marcaciones | `marcaciones.sincronizar_biometrico` |
| Cierre/Revertir cierre de mes | Crear o revertir cierre del periodo | `marcaciones.cierre_periodo` |
| Bypass cierre (editar periodo cerrado) | Modal de desbloqueo | `marcaciones.bypass_cierre` |
| Ver reporte PDF/Excel individual | Descargar reporte de un empleado | `marcaciones.ver` *(incluido)* |

---

### 🔵 MÓDULO: Reportes
| Acción | Descripción | Permiso propuesto |
|--------|-------------|-------------------|
| Ver modulo reportes | Acceder a la pantalla de reportes | `reportes.ver` |
| Filtrar y visualizar | Usar filtros y ver tabla | `reportes.ver` *(incluido)* |
| Descargar Excel | Boton verde exportar | `reportes.exportar` |
| Reprocesar (boton) | Disparar el motor de calculo desde reportes | `reportes.reprocesar` *(nuevo)* |
| Sincronizar desde reportes | Boton sync asistencia en toolbar de reportes | `reportes.sincronizar` *(nuevo)* |

DECISION CLAVE: Los botones Reprocesar y Sincronizar en el modulo de Reportes NO deben depender de permisos de Marcaciones.
✅ Estado: Ya implementado correctamente en routers/reportes.py

---

### ⚙️ MÓDULO: Configuración
| Pestaña | Acciones | Permiso propuesto |
|---------|----------|-------------------|
| Horarios | Ver, crear, editar, eliminar turnos | `configuracion.horarios` |
| Bonos | Ver, crear, editar, eliminar bonos | `configuracion.bonos` |
| Justificaciones | Ver, crear, editar, eliminar tipos | `configuracion.justificaciones` |
| Calendario | Ver feriados, agregar, sincronizar | `configuracion.calendario` |
| Correo | Ver config, guardar ajustes, agregar notificaciones | `configuracion.correo` |
| Estados | Ver, activar/desactivar, guardar cambios | `configuracion.estados` |
| Seguridad | Ver/crear/editar usuarios y roles | `configuracion.seguridad` |
| Robot BioAlba | Solo lectura (sin inputs de accion) | `configuracion.ver` |

⚠️ D3 + D8 (AUDITORIA — CORREGIDO EN RE-AUDITORIA): El router configuracion.py NO estaba sin guards:
USA 'configuracion.editar' (permiso generico de los 18 originales) que el plan v2 elimina.
La operacion correcta es REEMPLAZAR ese permiso por el permiso granular especifico.
El permiso 'configuracion.editar' existia en la BD viva (18 permisos) pero NO en la semilla de 22.
Esto significa que en instalaciones nuevas todos los endpoints de escritura de config ya dan 403
excepto al Super Admin (que bypassa via is_superuser=True en security.py L30).

Mapa exacto de reemplazos en configuracion.py (resultado de la re-auditoria):
- POST   /bonos/                       : 'configuracion.editar' → 'configuracion.bonos'
- PUT    /bonos/{id}/                  : 'configuracion.editar' → 'configuracion.bonos'
- DELETE /bonos/{id}/                  : 'configuracion.editar' → 'configuracion.bonos'
- GET    /bonos/                       : 'configuracion.ver'    → MANTENER (solo lectura)
- POST   /justificaciones/tipos/       : 'configuracion.editar' → 'configuracion.justificaciones'
- PUT    /justificaciones/tipos/{id}/  : 'configuracion.editar' → 'configuracion.justificaciones'
- DELETE /justificaciones/tipos/{id}/  : 'configuracion.editar' → 'configuracion.justificaciones'
- GET    /justificaciones/tipos/       : get_current_user (sin permiso) → D9: cambiar a 'marcaciones.ver'
- POST   /pagadores/                   : 'configuracion.editar' → 'configuracion.bonos'
- PUT    /pagadores/{id}/              : 'configuracion.editar' → 'configuracion.bonos'
- POST   /ajustes/{clave}/             : 'configuracion.editar' → 'configuracion.correo'
- POST   /notificaciones_areas/        : 'configuracion.editar' → 'configuracion.correo'
- DELETE /notificaciones_areas/{area}/ : 'configuracion.editar' → 'configuracion.correo'
- POST   /feriados/sync/{year}/        : 'configuracion.editar' → 'configuracion.calendario'
- POST   /feriados/                    : 'configuracion.editar' → 'configuracion.calendario'
- DELETE /feriados/{id}/               : 'configuracion.editar' → 'configuracion.calendario'
- PUT    /estados/{codigo}/            : 'configuracion.editar' → 'configuracion.estados'
- GET    /estados/                     : get_current_user (sin permiso) → OK (solo lectura interna)

---

## Comparacion: Permisos Actuales vs Propuestos

### Estado Actual (18 permisos en BD viva)
- configuracion.ver / seguridad
- empleados.ver / editar / eliminar / horarios / bonos / sincronizar_biometrico
- marcaciones.ver / editar / procesar / cierre_periodo / sincronizar_biometrico / bypass_cierre / horas_extras
- reportes.ver / exportar

### Estado Propuesto (28 permisos)

MODULO EMPLEADOS (8):
- empleados.ver
- empleados.crear          (NUEVO - separado de editar)
- empleados.editar
- empleados.eliminar
- empleados.reincorporar   (NUEVO)
- empleados.horarios
- empleados.bonos
- empleados.sincronizar_biometrico

MODULO MARCACIONES (8):
- marcaciones.ver
- marcaciones.editar
- marcaciones.justificar   (NUEVO - antes mezclado con editar)
- marcaciones.horas_extras
- marcaciones.procesar
- marcaciones.cierre_periodo
- marcaciones.sincronizar_biometrico
- marcaciones.bypass_cierre

MODULO REPORTES (4):
- reportes.ver
- reportes.exportar
- reportes.reprocesar      (NUEVO - ya implementado en backend)
- reportes.sincronizar     (NUEVO - ya implementado en backend)

MODULO CONFIGURACION (8):
- configuracion.ver
- configuracion.horarios   (NUEVO)
- configuracion.bonos      (NUEVO)
- configuracion.justificaciones (NUEVO)
- configuracion.calendario (NUEVO)
- configuracion.correo     (NUEVO)
- configuracion.estados    (NUEVO)
- configuracion.seguridad

Total: 18 -> 28 permisos (+10 nuevos, eliminando configuracion.editar generico)

⚠️ D4+D5 (AUDITORIA): Los 6 permisos configuracion.* granulares NO estan en la semilla actual.
La semilla solo corre si COUNT(*) == 0 (BD vacia).
En produccion se requiere migracion incremental obligatoria con INSERT OR IGNORE.

---

## Matriz de Roles Propuesta

### Rol: Super Administrador (ID 1 - Inmutable)
Todos los permisos sin restriccion

### Rol: Jefe de Area (Existente)
- Dashboard: libre
- Empleados: ver, crear, editar, reincorporar, horarios, bonos, sincronizar_biometrico
- Marcaciones: ver, editar, justificar, horas_extras, procesar, cierre_periodo, sincronizar_biometrico
- Reportes: ver, exportar, reprocesar, sincronizar
- Configuracion: ver (Robot BioAlba solo lectura)

### Rol: Operador RRHH (Nuevo)
- Dashboard: libre
- Empleados: ver, editar, reincorporar, horarios
- Marcaciones: ver, editar, justificar, horas_extras
- Reportes: ver, exportar

### Rol: Supervisor / Solo Lectura (Nuevo)
- Dashboard: libre
- Empleados: ver
- Marcaciones: ver
- Reportes: ver

---

## ⚠️ Discrepancias Descubiertas por Auditoría de Interconexión Total

| # | Tipo | Descripción | Urgencia | Fase |
|---|---|---|---|---|
| D1 | BACKEND CRÍTICO | POST /empleados/ usa empleados.editar en vez de empleados.crear | CRÍTICA | Fase 1 |
| D2 | BACKEND CRÍTICO | /activate/ y /reincorporar/ usan empleados.editar en vez de empleados.reincorporar | CRÍTICA | Fase 1 |
| D3 | BACKEND CRÍTICO | routers/configuracion.py usa 'configuracion.editar' (obsoleto) en 17 endpoints | CRÍTICA | Fase 1 |
| D4 | BD CRÍTICO | Los 6 permisos configuracion.* granulares no estan en la semilla | CRÍTICA | Fase 0 |
| D5 | BD CRÍTICO | Sin script de migracion para BD existente (semilla no corre en produccion) | CRÍTICA | Fase 0 |
| D6 | FRONTEND MEDIO | 'turnos.asignar' es permiso fantasma en main.js L796 | MEDIA | Fase 2 |
| D7 | SEMILLA MEDIO | Actualizar log de semilla a 28 permisos y agregar los 6 de configuracion | MEDIA | Fase 5 |
| D8 | BACKEND MEDIO | Fase 1 requiere REEMPLAZAR 'configuracion.editar' (no agregar) — mapa de 17 endpoints en tabla del modulo Configuracion | MEDIA | Fase 1 |
| D9 | BACKEND MEDIO | GET /configuracion/justificaciones/tipos/ usa get_current_user sin permiso especifico — abierto a cualquier autenticado | MEDIA | Fase 1 |
| D10 | BD MEDIO | Script de Fase 0 debe incluir explicitamente INSERT de empleados.crear en rol_permisos del Jefe de Area (rol_id=2) | MEDIA | Fase 0 |

---

## Plan de Implementacion en 6 Fases

---

### FASE 0 — Migración Incremental de BD (NUEVO — prerequisito de todo)

OBJETIVO: Insertar los 10 permisos nuevos y asignarlos a roles en la BD existente.

ARCHIVOS: scratch/migrate_rbac_v2.py (NUEVO)

ACCIONES:
1. Script Python con INSERT OR IGNORE para los 10 permisos nuevos
2. INSERT OR IGNORE en rol_permisos para asignar permisos nuevos a cada rol segun la matriz
   D10 FIX: incluir explicitamente INSERT OR IGNORE rol_permisos(rol_id=2, permiso='empleados.crear')
   para el Jefe de Area, ya que la semilla original no lo tenia
3. Verificacion final: SELECT COUNT(*) FROM permisos debe devolver 28
4. El script NO modifica la semilla (eso es Fase 5). Solo opera sobre la BD viva.

PERMISOS A INSERTAR (10 nuevos):
- empleados.crear
- empleados.reincorporar
- marcaciones.justificar
- reportes.reprocesar
- reportes.sincronizar
- configuracion.horarios
- configuracion.bonos
- configuracion.justificaciones
- configuracion.calendario
- configuracion.correo
- configuracion.estados
(Nota: son 11 listados — verificar contra BD viva con SELECT id FROM permisos para no duplicar)

---

### FASE 1 — Backend: Corregir Endpoints + Guards en Configuracion (antes era Fase 2)

OBJETIVO: Corregir D1, D2, D3. Backend defensivo en profundidad.

ARCHIVOS: backend/routers/empleados.py, backend/routers/configuracion.py

ACCIONES EN empleados.py:
- POST /empleados/ (L197): RequirePermission("empleados.editar") → RequirePermission("empleados.crear")
- POST /{id}/activate/ (L624): RequirePermission("empleados.editar") → RequirePermission("empleados.reincorporar")
- POST /{id}/reincorporar/ (L650): RequirePermission("empleados.editar") → RequirePermission("empleados.reincorporar")

ACCIONES EN configuracion.py (D3/D8 — REEMPLAZAR, no agregar):
Usar el mapa exacto de la seccion 'Modulo Configuracion' del plan. Operacion: buscar
'configuracion.editar' en cada endpoint y reemplazar segun el mapa:
- POST/PUT/DELETE /bonos/*              → RequirePermission("configuracion.bonos")
- POST/PUT/DELETE /justificaciones/tipos/* → RequirePermission("configuracion.justificaciones")
- POST/PUT        /pagadores/*          → RequirePermission("configuracion.bonos")
- POST            /ajustes/{clave}/     → RequirePermission("configuracion.correo")
- POST/DELETE     /notificaciones_areas/* → RequirePermission("configuracion.correo")
- POST/DELETE     /feriados/*           → RequirePermission("configuracion.calendario")
- PUT             /estados/{codigo}/    → RequirePermission("configuracion.estados")

ACCION ADICIONAL D9 — GET /justificaciones/tipos/:
Cambiar Depends(get_current_user) → Depends(RequirePermission("marcaciones.ver"))
(este endpoint es llamado por el popover de marcaciones para listar los tipos disponibles)

---

### FASE 2 — Frontend HTML: data-permiso + Fix D6 (antes era Fase 3)

ARCHIVOS: frontend/index.html, frontend/js/marcaciones_ui.js, frontend/js/main.js

ACCIONES:
- Boton "Nuevo Empleado": ya tiene data-permiso="empleados.crear" (OK)
- main.js L804 boton eliminar ficha: cambiar 'empleados.editar' → 'empleados.eliminar'
- main.js L809 boton reincorporar tabla: cambiar 'empleados.editar' → 'empleados.reincorporar'
- D6 FIX: main.js L796: cambiar 'turnos.asignar' → 'empleados.horarios' (permiso fantasma)
- Pestana "Asignacion Masiva": agregar data-permiso="empleados.horarios"
- Botones Bonos: ya tiene data-permiso="empleados.bonos" (OK)
- Pestanas de Configuracion: agregar data-permiso segun su permiso individual
- Marcaciones: agregar data-permiso a botones de justificar, horas_extras, procesar, cierre

---

### FASE 3 — auth.js: Blindaje de pestanas de Configuracion (antes era Fase 4)

ARCHIVOS: frontend/js/auth.js

OBJETIVO: Las pestañas de Configuracion usan data-permiso → auth.js ya las oculta automaticamente.
No se requiere logica adicional. Solo verificar que el HTML tenga el data-permiso correcto.

---

### FASE 4 — seguridad_ui.js: Rediseno de la Matriz de Roles (antes era Fase 5)

ARCHIVOS: frontend/js/seguridad_ui.js, frontend/index.html (modal de rol)

OBJETIVO: Redisenar la modal de edicion de roles para mostrar permisos agrupados en tabla horizontal
tipo grilla, con checkboxes claramente organizados por modulo. Modal XL o full-width.

---

### FASE 5 — Semilla: Actualizar para Instalaciones Futuras

ARCHIVOS: backend/repositories/seguridad.py

ACCIONES:
- Agregar los 6 permisos de configuracion granular al array permisos_base
- Actualizar log: "22 permisos" → "28 permisos"
- Verificar que la matriz de rol_permisos de cada rol incluye los nuevos permisos

---

## Orden de Ejecución Definitivo

Fase 0: scratch/migrate_rbac_v2.py      ← BD viva en produccion (PRIMERO SIEMPRE)
         incluye D10: empleados.crear para Jefe de Area en rol_permisos
Fase 1: empleados.py                    ← D1, D2: correccion de 3 endpoints
         configuracion.py               ← D3/D8: reemplazo de 17 endpoints + D9: fix tipos
Fase 2: index.html + main.js            ← Frontend HTML + fix D6 (turnos.asignar → empleados.horarios)
Fase 3: auth.js                         ← Verificacion del blindaje de pestanas config (no requiere logica nueva)
Fase 4: seguridad_ui.js                 ← Modal roles rediseñada (grilla por modulo)
Fase 5: seguridad.py (semilla)          ← D7: actualizacion para instalaciones futuras

---

## Preguntas Abiertas (Resueltas)

1. Crear los 2 roles nuevos (Operador RRHH y Supervisor)? → SI, ya estan en la semilla actual
2. empleados.crear separado de empleados.editar? → SI, separados (y D1 obliga a corregir el backend)
3. Ocultar pestanas enteras de Configuracion segun permiso? → SI, con data-permiso individual
4. Robot BioAlba es 100% solo lectura? → SI, configuracion.ver es suficiente
5. El Super Admin bypassa TODOS los RequirePermission? → SI, verificado en security.py L30:
   check_permission() hace 'if self.is_superuser: return True' antes de consultar la lista de permisos
6. 'configuracion.editar' existe en BD viva? → SI (era uno de los 18 originales).
   La semilla de 22 lo elimino. La Fase 0 no debe insertarlo. La Fase 1 lo REEMPLAZA.
7. Cuantos endpoints toca la Fase 1 en configuracion.py? → 17 endpoints mapeados (ver tabla en modulo Configuracion)

---

## Historial de Auditorías de Interconexión Total

| Iteracion | Discrepancias encontradas | Nuevas | Tipo |
|---|---|---|---|
| Auditoría v1 (plan original) | D1-D7 | 7 | 5 críticas, 2 medias |
| Re-Auditoría v2 (plan v2) | D8-D10 | 3 | 0 críticas, 3 medias |
| **Total acumulado** | **D1-D10** | **10** | **5 críticas, 5 medias** |

Estado: todas las discrepancias documentadas tienen accion asignada a una fase concreta.
Estimacion de trabajo adicional descubierto por las auditorias: ~8h sobre el plan original.

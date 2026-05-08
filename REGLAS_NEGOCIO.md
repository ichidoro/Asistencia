# 🧠 MEMORIA CENTRAL Y REGLAS INMUTABLES DEL SISTEMA

Este documento es la "Memoria a Largo Plazo" del proyecto.
**DIRECTIVA PARA AGENTE IA:** Debes leer este archivo usando tus herramientas ANTES de modificar código estructural. Si durante el desarrollo descubres una regla nueva o resolvemos un bug crítico juntos, DEBES escribir y documentar el aprendizaje aquí mismo, bajo la categoría correspondiente.

---

## 1. 🏗️ REGLAS DE ARQUITECTURA Y BASE DE DATOS
- **Control de Concurrencia (Turso):** Operaciones masivas en base de datos híbrida deben realizarse dentro de un `_sync_lock` (ver `Database.execute_batch`) y usando `suppress_auto_sync=True` para prevenir cuellos de botella con la réplica en la nube (evita un bloqueo silencioso de 22 segundos).
- **Seguridad y Autorización (RBAC v3):** Nunca validar permisos usando `rol_id == 1` hardcodeado. Utilizar los atributos inyectados en `SecurityContext`, como `is_superuser` o los métodos `check_area_access` y `check_permission`.

## 2. 💼 REGLAS DE LÓGICA DE NEGOCIO Y FRONTEND
- **Cierre de Periodo Zero-Trust:**
  - **Requisito 30 Días:** Un periodo de cierre no puede exceder 31 días. Evita colapsos de memoria y protege la semántica mensual.
  - **Área Obligatoria:** No se puede ejecutar un cierre seleccionando "Todas las áreas". Cada área se cierra por separado y de forma secuencial.
  - **Bloqueo Hoy y Futuro:** Está prohibido cerrar periodos que incluyan el día actual (hoy) o fechas futuras para prevenir errores por turnos en curso.
  - **Hard Stops:** El periodo no se cerrará si existen: anomalías pendientes, turnos en curso (evita error de media noche), u horas extras pendientes de validación.
  - **Soft Stops:** Inasistencias no justificadas mostrarán un Soft Stop y solo se podrán cerrar si el jefe aprueba su consolidación explícitamente mediante el Wizard.
  - **Smart Dates:** Al elegir un área en el frontend, el sistema consultará automáticamente el `/ultimo-cierre/` del área y sugerirá el día inmediatamente posterior para evitar fisuras temporales (continuidad ininterrumpida).
- **Reversión de Cierre:** Solo un `is_superuser` puede revertir un cierre de periodo mediante la opción habilitada en el historial de cierres.

## 3. 🛡️ EXCEPCIONES Y CÓDIGO PROTEGIDO (EDGE CASES)
- **Cierre de Periodo y Turnos En Curso:** La validación de estado `EN_CURSO` en el cierre previene el "Error de Media Noche", evitando que turnos cruzados sean contabilizados erróneamente en el periodo o causen inconsistencias.

## 4. 🐛 REGISTRO DE BUGS HISTÓRICOS Y LECCIONES (POST-MORTEMS)
- [2026-05-07]: **Latencia de Inicio Backend:** Se identificó que inicializar dependencias de DB al arranque del backend tomaba 40s debido a colisiones en `conn.sync()`. Solucionado moviendo tareas asíncronas con bloqueos optimizados a un worker de background en `events.py`.
- [2026-05-07]: **Atributos Faltantes en SecurityContext:** El objeto `SecurityContext` no almacena `rol_global`. Cualquier endpoint que usaba `current_user.usuario.get("rol_global")` fallaba. Solución: usar `current_user.is_superuser` y refactorizar todo el RBAC v3 a este estándar.
- [2026-05-08]: **LibSQL Race Condition — Rust Panic (Solución Definitiva v5, 4 rondas de simulación):**
  - **Causa raíz:** `conn.sync()` y `conn.cursor()` ejecutándose concurrentemente en threads del `ThreadPoolExecutor` causan un Panic en Rust (`Option::unwrap() on None`). La GIL de CPython se libera durante llamadas C/Rust, haciendo que mecanismos Python puros (bool, asyncio.Lock, threading.Event) sean insuficientes.
  - **Solución:** `threading.Lock()` nativo (`self._conn_native_lock`) compartido entre `_do_sync()` (en `_push_to_cloud`) y los 4 puntos `conn.cursor()` (`_do_fetch`, `_do_execute`, `_do_batch_local`, `_do_script`).
  - **Patrón:** `lock.acquire(timeout=5.0)` → si timeout, retornar `"RECONNECT"` → el retry loop existente reintenta con 200ms backoff (máx 3 intentos).
  - **Reglas derivadas:**
    - ❌ NO usar `asyncio.Lock` para serializar threads OS (solo funciona en event loop).
    - ❌ NO usar `threading.Event` (TOCTOU: `wait()` y `cursor()` no son atómicos).
    - ❌ NO usar `bool` (invisible entre threads cuando GIL se libera en C/Rust).
    - ✅ `offline=True` en `libsql.connect()` SOLO si `.db` Y `.meta` existen. Sin `.meta` = fresh-start, requiere `offline=False` para el protocolo Hrana.
    - ✅ `_apply_pragmas()` NO necesita guard: corre antes de que exista cualquier `_push_to_cloud()`.
    - ✅ Sync inicial en `connect()`: máximo 5s de timeout para no bloquear el startup.
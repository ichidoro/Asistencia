# Reglas de Negocio: Gestión de Áreas y Asistencia

## 1. Integridad Referencial de Áreas (Modelo Inmutable)
- **Las áreas son maestras:** Las áreas (tabla `areas`) representan los departamentos oficiales de la empresa. NO deben ser eliminadas ni editadas por los usuarios desde la interfaz. 
- **La fuente de verdad es relativa:** El reloj control (BioAlba) puede enviar nombres de áreas con errores ortográficos, espacios adicionales o nombres antiguos. Estas variaciones se consideran **alias** (tabla `areas_alias`).
- **El Guardián:** Cuando el sistema detecta un área desde BioAlba que no existe en `areas` ni en `areas_alias`, la sincronización se detiene (hard-stop) y requiere la intervención de Recursos Humanos para mapear este texto erróneo a un área maestra existente o crear una nueva área maestra si corresponde.

## 2. El Catálogo de Auditoría (No Destructivo)
- El módulo de configuración presenta un "Catálogo de Áreas" de **solo lectura** para las áreas maestras.
- La única acción destructiva permitida en el catálogo es **desvincular (eliminar) un alias**.
- **Regla de Inmunidad:** Si se elimina un alias (por ejemplo, porque se mapeó incorrectamente), el sistema no reasigna automáticamente a los empleados pasados. Simplemente, la próxima vez que BioAlba envíe ese texto erróneo, el Guardián lo atrapará de nuevo y forzará a RRHH a mapearlo correctamente.

## 3. Modelo Relacional vs Texto Plano
- Anteriormente (v1), las áreas se guardaban como texto plano en la tabla de `empleados`. 
- Ahora (v2), los empleados tienen un `area_id` (Clave Foránea) que apunta a la tabla `areas`.
- Este diseño previene fallos en cascada en la generación de reportes: si un empleado cambia de área, su historial puede rastrearse correctamente sin depender de cómo el reloj control tipeó el área en diferentes meses.

## 4. Política de Edición
* **Prohibido:** Proveer una UI para renombrar áreas (afectaría históricamente a todos los reportes).
* **Prohibido:** Proveer una UI para eliminar áreas maestras (dejaría a empleados huérfanos).
* **Permitido:** Eliminar (desvincular) un alias.
* **Permitido:** Ver las áreas y contar cuántos alias (errores) tienen asociados como medida de "suciedad" de datos provenientes del reloj.

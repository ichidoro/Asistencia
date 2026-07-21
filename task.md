# Plan de Acción y Tareas — Rediseño Premium Artículo 22

- [x] Modificar `articulo22_ui.js`
  - [x] Actualizar CSS en `initTab` con estilos de tarjetas squircle, hover premium y botones outline minimalistas de alta gama.
  - [x] Implementar escala de 24h (ticks cada 3h con ocultado automático de impares en móviles).
  - [x] Integrar lógica de marcas alternadas (`level-1` / `level-2` / `level-3`) con burbujas unificadas.
  - [x] Integrar protección de solapamiento para `AHORA` (ocultar texto si la diferencia es < 75m con la última marcación).
  - [x] Diseñar el encabezado de las tarjetas en 2 filas (para evitar solapamientos en anchos de tarjeta reducidos de 2 columnas).
- [x] Verificar funcionamiento localmente
  - [x] Iniciar el servidor local.
  - [x] Validar vista de escritorio (2 columnas, botones minimalistas, escala completa, alternancia).
  - [x] Validar vista móvil (1 columna, cabecera apilada, escala de 6h, burbujas escalonadas).
- [x] Desplegar en producción
  - [x] Compilar y desplegar a Cloud Run.
  - [x] Incrementar versión en `index.html` a `_v7` e invalidar Service Worker (`aguacol-v10`).
- [x] Verificar en producción
  - [x] Validar comportamiento responsivo y visual en producción.
  - [x] Asegurar que el Service Worker haya recargado con el nuevo caché.

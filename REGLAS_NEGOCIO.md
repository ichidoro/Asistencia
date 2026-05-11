# MEMORIA Y REGLAS DE NEGOCIO (Asistencia App)

Este documento centraliza las lecciones aprendidas y los dogmas arquitectónicos inquebrantables del proyecto para prevenir la amnesia del Agente y evitar regresiones ("Sistema Inmune"). Toda edición o creación lógica debe leer primero este documento.

---

## 1. Dogma Principal: Soberanía de Datos (C1 sobre C2)
**Bajo ninguna circunstancia** la capa de servicios o el backend (`C2`) tiene autorización para "adivinar", imponer heurísticas o usar variables estáticas (hardcodeadas) para cálculos de asistencia, horarios o tolerancia.
*   **Prohibido el uso de "time-deltas" fijos:** Si un turno necesita cruzar la medianoche o esperar marcas tardías, **no se pueden sumar `horas=33` o `horas=38` u `horas=3` por defecto en el código.**
*   **Origen de la verdad:** Toda tolerancia, delta de horas, redondeo o exigencia disciplinaria nace única y exclusivamente desde los campos paramétricos de Base de Datos (`C1`), tales como `anclaje_entrada_minutos`, `anclaje_salida_minutos`, `tolerancia_retraso_descuento`, etc. Si estos campos no existen o vienen nulos, el servicio debe manejarlo de forma neutra y predecible (ej. `0`), pero NUNCA inventar un comportamiento empresarial en código.

## 2. Bifurcación Asistencia: Finanzas vs Disciplina
La Asistencia en esta aplicación tiene un modelo Dual, el cual jamás debe mezclarse:
*   **Eje Disciplinario (Incidencias):** Totalmente inflexible. Se rige por la hora reloj. Llegar tarde genera un estado de `ATRASO` imborrable para RRHH, aunque el trabajador recupere las horas más tarde.
*   **Eje Financiero (Deuda):** Es un pozo aritmético. Si `Horas Trabajadas >= Horas Teóricas`, la Deuda del día es `0`. El sistema permite pagar un día completo a alguien que tiene una incidencia disciplinaria de atraso, porque compensó quedándose más tarde.
*   **Turnos Libres/Bolsa:** Se suprimen los castigos del eje disciplinario. Todo el cálculo recae puramente en la sumatoria aritmética del eje financiero contra una meta estipulada a fin de semana.

## 3. Preservación del Flujo Frontend
*   La UI (`C3`) es completamente "Tonta" en decisiones de negocio; solo pinta lo que responde `C2`. Si `C3` intenta calcular un estado de deuda con un "If deuda >= 15 minutos", es meramente visual. Todo cálculo monetario y paramétrico se audita en el servidor.
*   Los modales de edición (Ej: Wizard de Pagadores, Justificaciones y Empleados) dependen del anclaje continuo del estado (`window.currentX`). No se deben alterar los flujos de "cerrar modal A y abrir modal B" sin asegurar que el estado asíncrono sobrevive.

---
*(Última actualización: Extirpación de heurísticas duras de tiempo en agrupar_marcaciones - Auditoría SRE)*

# 🧠 MEMORIA CENTRAL Y REGLAS INMUTABLES DEL SISTEMA

Este documento es la "Memoria a Largo Plazo" del proyecto.
**DIRECTIVA PARA AGENTE IA:** Debes leer este archivo usando tus herramientas ANTES de modificar código estructural. Si durante el desarrollo descubres una regla nueva o resolvemos un bug crítico juntos, DEBES escribir y documentar el aprendizaje aquí mismo, bajo la categoría correspondiente.

---

## 1. 🏗️ REGLAS DE ARQUITECTURA Y BASE DE DATOS
*(Agente: Anota aquí reglas sobre la base de datos, tipos de datos obligatorios, infraestructura o librerías permitidas).*
- [Ejemplo - Borrar después]: Nunca hacer un DELETE físico de usuarios, usar borrado lógico cambiando el estado a "inactivo".


## 2. 💼 REGLAS DE LÓGICA DE NEGOCIO Y FRONTEND
*(Agente: Anota aquí reglas sobre la interfaz de usuario, cálculos matemáticos del negocio, flujos de usuario y restricciones).*
- [Ejemplo - Borrar después]: Los precios en el carrito siempre deben procesarse con el IVA incluido antes de enviarse a la pasarela de pago.


## 3. 🛡️ EXCEPCIONES Y CÓDIGO PROTEGIDO (EDGE CASES)
*(Agente: Documenta aquí funciones específicas o lógicas complejas que NO deben ser modificadas o borradas durante refactorizaciones, ya que previenen bugs muy específicos).*
- 


## 4. 🐛 REGISTRO DE BUGS HISTÓRICOS Y LECCIONES (POST-MORTEMS)
*(Agente: Cuando ocurra un error difícil que tome varios intentos solucionar, documenta aquí el Síntoma, la Causa Raíz y la Solución inyectada para no volver a cometer el mismo error mañana).*
- [Fecha de hoy]: Sistema de memoria inicializado correctamente.
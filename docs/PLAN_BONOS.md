# Plan de bonos

Borrador del 21-11-2026 para conversar con la persona dueña (respuestas del 22-11-2026 en la sección 4). Hecho con el código y con lectura de producción (solo
lectura); no cambia nada todavía. Sin nombres de personas: los casos van con iniciales en `PLAN_BONOS_local.md` si
hacen falta.

Reglas de trabajo que manda este plan (de la persona dueña):

- **Nada escrito en el código.** Montos, cargos, contratos, qué justificación hace perder un bono, cómo se reparte,
  umbrales: todo sale de la configuración de cada bono en la pantalla. Si hoy algo no se puede configurar, se agrega a
  la configuración; no se resuelve con un valor fijo en el código.
- **Cada período tiene sus propias fechas.** El bono se calcula con la fecha de inicio y la fecha de fin del período de
  cierre (tabla de períodos de RR.HH.), sean las que sean. Hoy todos van del 26 al 25, pero eso es un dato del período,
  no una regla.
- **Los bonos se pagan por período de cierre** y RR.HH. debe ver en el informe cuánto paga por cada bono.

---

## 1. Cómo funciona hoy

### 1.1 Lo que se configura en la pantalla (Configuración → Bonos)

Por bono: nombre, descripción, activo y las áreas marcadas. Cada bono tiene una o más **reglas**, y cada regla tiene:

| Campo | Qué hace hoy en el cálculo |
|---|---|
| Contrato (Todos / Indefinido / Temporal) | Se usa: la regla aplica solo a ese contrato |
| Monto | Se usa |
| Cargo requerido (uno o varios, separados por coma) | Se usa: el cargo de la ficha debe ser **igual** a uno de ellos |
| Cargos excluidos | Se usa: si el cargo es uno de ellos, la regla no aplica |
| Proporcional | Se usa: si está marcado, se paga por días asistidos y nunca se pierde entero |
| Asistencia mínima (%) | **No se usa**: la pantalla lo muestra («asistencia sobre X %») pero el cálculo lo ignora |
| Áreas del bono | **No se usan en el cálculo**: solo deciden qué columnas salen en el informe |

Se toma la **primera regla** del bono que calce con el cargo y el contrato de la persona.

El interruptor **Prop.** vale para todas las causas a la vez: con él encendido, también una inasistencia sin justificar
solo descuenta en proporción; con él apagado, cualquier día perdido hace perder el bono entero. No se puede elegir por
causa.

### 1.1 bis Lo que se configura en cada justificación (Configuración → Justificaciones) y qué efecto tiene en los bonos

| Campo de la justificación | Efecto en los bonos hoy |
|---|---|
| Nombre, Sigla, Descripción | Ninguno (la sigla es la que se ve en la grilla) |
| Cómo se cuentan los días (hábiles / corridos) | Ninguno directo: solo decide qué días quedan justificados; el bono mira solo los días de turno |
| **Goce de sueldo** (sí / no) | **El único campo que afecta los bonos, y para todos por igual.** «Sí, se paga»: el día cuenta como asistido en todos los bonos. «No se paga»: el día hace perder los bonos «todo o nada» y descuenta en los proporcionales |
| Quién paga (Empleador / Mutual / Fonasa) | Ninguno. El cálculo espera una marca «el pagador aplica para bono» que no existe en ninguna tabla, así que siempre vale como si aplicara |
| Días por defecto, En uso, Mínimo y Máximo de días, Veces al año | Ninguno: solo controlan el registro de la justificación |
| Si cae en un feriado (respeta / reemplaza) | Ninguno en la práctica: el bono no cuenta los feriados |
| Horas sindicales, Duración (día completo / por horas), Genera deuda de horas | Ninguno en los bonos: afectan las horas del día. Un permiso por horas deja el día como trabajado |

**Respuesta a «¿cómo se configura una licencia para que pague el bono en proporción?»: hoy no se puede.** Ningún campo
de la justificación ni del bono lo permite. Las dos salidas que existen están mal:
- marcar la licencia como «Sí, se paga» la deja como asistida en todos los bonos (se paga completo, no en proporción),
  y además cambia lo que dice sobre el sueldo;
- encender **Prop.** en el bono hace que todas las faltas, también las sin justificar, solo descuenten en proporción.

### 1.2 Bonos configurados hoy

| Bono | Monto | Contrato | Cargo | Tipo |
|---|---:|---|---|---|
| Compromiso | 70.000 / 60.000 | Indefinido / Temporal | Todos salvo excluidos (lista distinta por contrato) | Todo o nada |
| Transporte | 30.000 | Indefinido | Todos salvo excluidos | Todo o nada (la regla no tiene marcado «Prop.»; revisado el 22-11-2026) |
| Operador Línea | 30.000 | Indefinido | Operador de línea | Todo o nada |
| Retail | 30.000 | Todos | Operario armado | Todo o nada |
| Cloro | 50.000 | Todos | Operario cloro | Todo o nada |
| Supervisor | 100.000 | Indefinido | Ingreso producción y tres cargos de supervisor | Todo o nada |

### 1.3 Cómo se pierde hoy

La persona parte con el bono. Se revisan sus días de turno:

- Cuentan como asistidos: los días trabajados (aunque tengan atraso o salida adelantada), vacaciones, permisos,
  inasistencias compensadas, y los días justificados **con goce de sueldo**.
- Hacen perder: la **inasistencia sin justificar** y la **justificación sin goce de sueldo** (hoy solo la Licencia común).
- Bono «todo o nada»: un día perdido y se pierde entero. Bono «proporcional»: se paga días asistidos / días de turno.
- Ingreso a mitad de período: proporcional a los días que le tocaban.

La única distinción entre justificaciones es «con goce» o «sin goce», y vale igual para todos los bonos.

### 1.4 Dónde se ve

Grilla (✓ / ✗), Excel de cierre (SÍ / NO), informe PDF de cierre (✓), correo de cierre, y Productos 4 (usa
Compromiso para decidir quién recibe productos). **En ninguno sale el monto.**

---

## 2. Vacíos encontrados

### 2.1 Graves: afectan lo que se paga

**A. El cálculo no usa las fechas del período de cierre, usa el mes calendario.**
- El Excel y el informe calculan con el **mes de la fecha en que se sacan**. El informe de un período ya cerrado
  (por ejemplo, 26-09 al 25-10 sacado en noviembre) no encuentra ningún día y deja a todos como «califica».
- En el período abierto, los días del inicio del período que caen en el mes anterior (26 al 31) no se revisan.
- La grilla usa el mes de la fecha de inicio y calcula mal el monto proporcional (con el período completo trabajado,
  Compromiso da cerca de 4,6 veces el monto). Hoy no se nota porque la grilla muestra solo ✓ / ✗.
- Comprobado con un ensayo con datos inventados.

**B. Meses ya cerrados.** Mayo a Octubre se cerraron entre el 10 y el 13 de noviembre: sus informes se generaron con la
falla A. Por período hubo entre 1 y 4 personas con inasistencias sin justificar y entre 0 y 6 con licencia sin goce,
que según las reglas debían perder bonos. Falta confirmarlo mirando uno de esos informes.

**C. No hay montos en el informe.** RR.HH. no puede saber cuánto pagar, menos en un bono proporcional.

### 2.2 Configuración que falta (para no escribir reglas en el código)

**D. Las licencias no se pueden distinguir por bono.** Hoy una justificación con goce mantiene todos los bonos y una sin
goce hace perder todos (salvo el proporcional). No se puede decir, por ejemplo, «esta licencia hace que Compromiso y
Transporte se paguen en proporción, pero el bono del cargo se pierde».

**E. La «asistencia mínima» se muestra pero no se aplica.** Quien la configure cree que vale y no vale.

**F. El cargo se escribe a mano.** Un cargo con otra escritura (hay cargos repetidos con nombres parecidos y otros
cortados a 20 letras) se queda sin su bono sin aviso.

**M. Ciclo y Bolsa no pierden igual.** En Ciclo Inteligente, un día de licencia sin goce hace perder el bono. En Bolsa
Flexible ese día ni siquiera se cuenta (solo cuentan los días trabajados o con inasistencia), así que **una persona de
Bolsa con licencia sin goce no pierde el bono** y, en el proporcional, se le paga completo. En producción hay 67 días de
licencia común en personas de Bolsa desde el 26-04.

**N. El «Quién paga» no afecta los bonos aunque el cálculo lo espera.** Ver 1.1 bis.

**O. Bonos que no salen en el informe PDF.** Las columnas del PDF salen de las áreas marcadas en cada bono. Operador
Línea, Retail y Supervisor no están marcados en ningún área, así que el PDF de Producción (donde están los 8 operadores
de línea y los 4 operarios de armado) no trae esas columnas, aunque el cálculo sí los evalúa (revisado en producción,
solo lectura, 22-11-2026).

**P. Productos 4 busca el bono por su nombre escrito en el código.** Toma el bono que se llame «compromiso» y le cambia
las reglas en memoria (sin cargos excluidos, cualquier contrato). Si alguien renombra el bono, Productos 4 deja de mirar
la asistencia sin avisar.

**Q. Cargos con dos escrituras en la lista de cargos.** «AYUDANTE BODEGA» (2 personas, creado el 13-10) y «AYUDANTE DE
BODEGA» (4 personas); «ASISTENTE DE FACTURA» y «ASISTENTE FACTURACIO»; y nombres cortados a 20 letras («SUPERVISOR
ELABORACI», «ASISTENTE ADMINISTRA», «JEFA G. OPERACIONE»). Si una regla de bono nombra una escritura, las personas con
la otra quedan fuera. Hoy ningún bono usa esos cargos.
De dónde vienen los nombres cortados (revisado el 22-11-2026 en BioAlba, solo mirando): **el campo «Cargo» de la
ficha de usuario de BioAlba acepta como máximo 20 letras**, y BioAlba entrega el cargo ya cortado («ASISTENTE
ADMINISTRA», «ASISTENTE DE COBRANZ»). El código de la aplicación no corta el nombre: los 16 cargos creados a mano en la
pantalla tienen su nombre completo, hasta 33 letras. Como BioAlba no puede guardar más de 20 letras, el nombre completo
tiene que vivir en la aplicación, con el nombre cortado de BioAlba como alias (B3.3).
Lo que tiene BioAlba hoy: de 356 usuarios, solo 14 tienen cargo; el resto dice «---». Con «---» la sincronización no
toca el cargo de la aplicación (lo deja como está).
**Decisión de la persona dueña (22-11-2026):** el cargo es único. Queda «AYUDANTE DE BODEGA» (ya corregido en BioAlba
para las dos personas que tenían «AYUDANTE BODEGA»); queda «ASISTENTE FACTURA» (así está en BioAlba); los nombres se
ven completos.
**Hecho (22-11-2026, excepción autorizada por la persona dueña para corregir la base directo, con respaldo previo):**
«AYUDANTE BODEGA» se unió en «AYUDANTE DE BODEGA» (2 personas); «ASISTENTE DE FACTURA» pasó a llamarse «ASISTENTE
FACTURA» y «ASISTENTE FACTURACIO» se unió en él (2 personas); los nombres anteriores quedaron como alias, para que la
sincronización los reconozca. Queda en la auditoría (REGULARIZA_CARGOS). Los tres cargos cortados por BioAlba
(«ASISTENTE ADMINISTRA», «JEFA G. OPERACIONE», «SUPERVISOR ELABORACI») se dejan así (decisión de la persona dueña).

### 2.3 Historial

**G. El cargo no tiene historial con fecha.** El área sí lo tiene. Consecuencias: volver a sacar un período cerrado
después de cambiar un cargo da otros bonos; un cambio de labor a mitad de período no se puede reflejar.

**H. Hay una tabla de «bonos asignados con fecha» que el cálculo no usa.** Se llena al guardar la ficha, con la fecha
del guardado (no la del cambio real) y con otra forma de comparar cargos (busca si el nombre contiene la palabra).

**I. Al cerrar no se guarda el resultado de los bonos.** Volver a sacar un informe de un mes cerrado lo recalcula con lo
que haya hoy (cargos, reglas): puede dar distinto a lo que se pagó.

### 2.4 Orden

**J.** La Bolsa se reconoce por un solo nombre de tipo (el resto del sistema acepta dos). **K.** El esquema tiene un
campo «labor requerida» que no existe en la base. **L.** La regla que se usa es la primera que calce: si dos reglas
calzan, el orden en que se guardaron decide, sin aviso.

---

## 3. Lo que propongo, por etapas

Cada etapa es un cambio aparte, con pruebas, ensayo y la pregunta «¿Subo a GitHub?».

### Etapa B1 · Calcular por las fechas del período de cierre (corrige A)

- Toda evaluación de bonos recibe el **período** (fecha de inicio y fecha de fin de la tabla de períodos) y revisa
  exactamente esos días: grilla, Excel, informe PDF, correo de cierre y Productos 4.
- El proporcional por ingreso o salida se calcula contra los días de turno **de ese período**.
- Se elimina el uso del mes calendario en el cálculo de bonos.
- **Pruebas:** una por cada caso de la falla A (período cerrado sacado después, días del inicio del período en el mes
  anterior, monto de la grilla), que fallen con el código de hoy; y una con un período de fechas distintas a 26–25
  para asegurar que se usan las del período.
- **Ensayo:** copia del respaldo; bonos de cada período antes y después.
- **Hecho (22-11-2026, commit b118d0e):** el cálculo recibe la fecha de inicio y de fin del período en la grilla, el
  Excel y el informe de cierre (Productos 4 ya pasaba las fechas del período; ahora también lee sus feriados por esas
  fechas). La matriz puede traer días fuera del período: no cuentan. Los feriados se leen por las fechas del período
  (puede cruzar el año). El proporcional por ingreso o salida usa los días de turno del período; la salida cuenta solo
  en personas inactivas (en una activa es el término del contrato, que puede renovarse; hoy hay 14 así). En el período
  abierto quien no ha faltado va con el monto completo. Prueba nueva `test_bonos_por_periodo.py` (10 casos);
  618 pruebas en verde con la copia de práctica.
  **Ensayo en el servidor** con el respaldo del 22-11-2026, en una base temporal aislada que se borró al terminar:
  - Informe de cierre de Mayo a Octubre: antes todos salían «califica» con monto 0 (falla A confirmada). Ahora cada
    período tiene su total (entre 7,85 y 8,16 millones) y en cada período entre 4 y 16 bonos se pierden por
    inasistencia sin justificar o licencia sin goce.
  - Grilla: antes los montos salían inflados (Compromiso hasta 385.000 en vez de 70.000; el total de un período
    llegaba a 72 millones). Ahora la grilla y el informe dan el mismo total en todos los períodos.
  - Ningún bono que antes se perdía pasa a ganarse.
  - Los meses ya pagados no se tocan: el ensayo solo muestra cómo saldrían si se sacaran de nuevo.
- Los períodos ya pagados (Mayo a Octubre) no se tocan (decisión de la persona dueña, 22-11-2026).

### Etapa B2 · Montos en el informe de cierre (corrige C)

- El informe PDF y el Excel muestran, por persona y por bono, el **monto a pagar**; y el total por bono y por persona.
- Bono proporcional: muestra los días que cuentan sobre los días de turno (por ejemplo 18 / 20) junto al monto.
- Bono perdido: «—» y, en el detalle, el motivo (por ejemplo «inasistencia sin justificar el 08-10»).
- El resumen de arriba del informe suma lo que se paga en bonos.
- Depende de B1 (si el cálculo está mal, el monto también).
- **Hecho (22-11-2026, commit b0f33a2):**
  - Informe PDF: el monto de cada bono por persona (en pesos), una columna «Total» por persona, la fila de total por
    bono, «Bonos a pagar» en el resumen de arriba y una sección «Detalle de bonos» con los que no se pagan (causa y
    días, por ejemplo «Inasistencia sin justificar el 08-10; Licencia Común el 15-10 y 16-10») y los que se pagan en
    parte (por ejemplo «10 de 22 días de turno del período»). Un bono no pagado va en rosado con «—»; en blanco, no le
    corresponde.
  - Columnas (B3.8 adelantado): el informe muestra los bonos que les corresponden a sus personas según las reglas de
    cada bono, no las áreas marcadas en el bono. Así Operador Línea, Retail y Supervisor salen en Producción.
  - Excel de cierre: el monto en vez de «SÍ», «NO» si no se paga, una columna «Total bonos» y la suma en la fila de
    totales.
  - El cálculo entrega los días perdidos con su causa (para el detalle).
  - Pruebas nuevas `test_bonos_montos_en_informe.py` (7 casos que fallan con el código anterior); 625 pruebas en verde.

### Etapa B3 · Configuración ampliada de cada bono (corrige D, E, F, L, M, O, P, Q)

Todo se agrega a la pantalla de Configuración → Bonos; el cálculo solo lee lo configurado.

1. **Qué hace cada justificación con cada bono.** Se configura **en la justificación**, en una sección nueva
   «Efecto en los bonos» de Configuración → Justificaciones: una fila por bono activo y, para cada uno, una de tres
   opciones (la misma información se ve también desde el bono, como una tabla de justificaciones):
   - *Cuenta como asistido* (no afecta el bono).
   - *Descuenta en proporción* (el bono se paga por los días restantes).
   - *Hace perder el bono*.
   Vale para **todas las justificaciones**, las de hoy y las que se creen después: no hay ninguna con trato especial
   en el código. Al crear una justificación nueva, la sección aparece con una opción por bono y no se guarda sin
   elegirla (sin valor por defecto escondido).
   La **inasistencia sin justificar** se configura en el bono (no es una justificación), con las mismas opciones. Al
   crear la tabla queda en «hace perder el bono» en todos (lo que pasa hoy y lo que pidió la persona dueña), y se
   puede cambiar desde la pantalla. Así el interruptor **Prop.** deja de mezclar todas las causas. Al crear la tabla
   cada justificación se llena con lo que pasa hoy (con goce = cuenta como asistido; sin goce = hace perder, o en
   proporción si el bono es proporcional), así nada cambia hasta que alguien lo cambie. Ejemplo: en una licencia se
   elige «Descuenta en proporción» en Compromiso y Transporte, y lo que se decida en el bono del cargo.
   El «Goce de sueldo» queda solo para lo que dice del sueldo, sin decidir los bonos.
**Partes de B3** (cada una con su ensayo y su «¿Subo?»): **B3a** efecto de cada justificación en cada bono e
inasistencia sin justificar en el bono (puntos 1 y la mitad de 5); **B3b** cargos desde la lista, renombrar y unir
cargos, quitar la asistencia mínima (puntos 2 y 3); **B3c** aviso de reglas que se pisan y vista previa (4 y 6);
**B3d** Productos 4 como un bono (7).

**B3a hecho (22-11-2026, commit 13f144c):**
- Tabla nueva `bono_efectos` (bono × justificación → cuenta como asistido / descuenta en proporción / hace perder el
  bono) y en cada bono «Inasistencia sin justificar» (hace perder el bono / descuenta en proporción). Al crearlas se
  llenaron con lo de hoy. El cálculo solo lee lo configurado; si algo falta, el bono no se paga y el motivo dice
  «Falta configurar…».
- Pantallas: sección «Efecto en los bonos» en la ficha de cada justificación (y en la ventana del asistente de
  configuración), y en la ventana del bono la inasistencia sin justificar y el efecto de cada justificación. No se
  guarda sin elegirlos todos. El interruptor «Prop.» de la regla ya no se muestra (lo reemplazan los efectos); su
  valor se conserva en la base.
- Arreglo de paso: en una lista vacía de Configuración, «Nuevo» no abría la ficha.
- **Ensayo en el servidor** con el respaldo del 22-11-2026 (base temporal borrada al terminar): con lo llenado de hoy,
  0 cambios en todos los períodos (informe y grilla). Cambiando en la base temporal Licencia Común en Compromiso a
  «Descuenta en proporción», solo cambia Compromiso: 19 casos que antes lo perdían lo cobran en proporción.
- Prueba nueva `test_efecto_justificaciones_en_bonos.py` (13 casos); 638 pruebas en verde.
- **Sigue abierto M (Bolsa):** en Bolsa Flexible los días justificados no se cuentan, así que el efecto configurado
  solo alcanza a Ciclo Inteligente. Corregirlo cambia lo que cobran personas de Bolsa: va aparte, con su ensayo.

**B3b hecho (22-11-2026, commit be56814):**
- Los cargos de cada regla se eligen con casillas de la lista de cargos («Cargos que lo reciben», vacío = todos;
  «Cargos que no lo reciben») y la regla guarda su identificador. El cálculo compara el cargo de la persona, no su
  nombre escrito. Al crearse, las reglas de hoy se pasaron a la lista buscando sus nombres en la lista y en los alias
  de BioAlba (si una regla pidiera un cargo que no está, no lo recibe nadie, en vez de pasar a «todos»).
- Configuración → Cargos: «Renombrar» (el nombre anterior queda como alias para BioAlba) y «Unir con otro cargo»
  (pasan personas, alias y reglas de bono; el cargo unido queda como alias y se borra). Antes de guardar se ve cuántas
  personas y qué reglas cambian. Queda en la auditoría (RENOMBRAR_CARGO, UNIR_CARGOS).
- Se quitó «% Asist.» de la pantalla (no existe en las reglas de Aguacol); la columna queda en la base sin uso.
- **Ensayo en el servidor** con el respaldo del 22-11-2026 (base temporal borrada): 0 cambios en todos los períodos;
  los cargos de las 7 reglas de hoy se encontraron todos en la lista.
- Prueba nueva `test_cargos_de_la_lista_en_bonos.py` (5 casos); 643 pruebas en verde. Renombrar y unir probados contra
  la copia de práctica (PostgreSQL), también con una persona.

**B3c hecho (22-11-2026, falta subir):**
- Botón «Vista previa» en la ventana del bono: con lo que se está editando y sin guardarlo, muestra para el período
  vigente quién lo recibe, cuánto, con qué regla y por qué no lo cobra quien no lo cobra (días que no cuentan,
  resumidos por causa), y el total.
- Aviso de reglas que se pisan (L): la vista previa dice quién calza con más de una regla del mismo bono; al guardar
  así, la pantalla pregunta antes («¿Guardar con reglas que se pisan?»). Se sigue usando la primera que calza.
- El cálculo y la vista previa eligen la regla con la misma función.
- Prueba nueva `test_vista_previa_bono.py` (3 casos); 646 pruebas en verde. Probado en el navegador con la copia de
  práctica (vista previa, aviso y cancelar sin guardar). No cambia ningún cálculo.

2. **Se quita la «Asistencia mínima» (E).** No existe en las reglas de Aguacol (decisión de la persona dueña,
   22-11-2026): lo que decide el bono es la relación entre la asistencia del día y las justificaciones (punto 1). Se
   quita el campo «% Asist.» de la pantalla y de la regla.
3. **Cargos desde la lista de cargos**, no escritos a mano: se eligen con casillas, y la regla guarda el cargo (no su
   nombre escrito), así un cambio de nombre no la rompe.
   **Renombrar y unir cargos (Q)**, nuevo en Configuración → Cargos (hoy solo se puede crear un cargo, borrar un alias
   y marcarlo excluido):
   - *Renombrar:* cambia el nombre (por ejemplo «SUPERVISOR ELABORACI» a su nombre completo) y guarda el nombre anterior como alias, así
     la sincronización con BioAlba lo sigue reconociendo aunque llegue cortado.
   - *Unir:* pasa las personas, alias y reglas de bono de un cargo a otro y deja el nombre del cargo unido como alias
     (por ejemplo «AYUDANTE BODEGA» → «AYUDANTE DE BODEGA»). Antes de guardar muestra cuántas personas y reglas cambian.
   - Queda en la auditoría.
   Las uniones de hoy ya se hicieron (vacío Q); la pantalla queda para las que vengan. Prueba: después de unir y renombrar, una sincronización con el nombre cortado de
   BioAlba deja a la persona en el cargo correcto.
4. **Aviso de reglas que se pisan:** si dos reglas del mismo bono calzan con la misma persona, la pantalla lo dice.
5. **Ciclo y Bolsa iguales (M):** un día justificado cuenta igual en los dos tipos de horario, según lo configurado.
6. **Vista previa:** la pantalla muestra, para el período abierto, quién califica y cuánto, con las reglas que se están
   editando, antes de guardar.
7. **Productos 4 como un bono más (P).** Se crea en Configuración → Bonos como un beneficio (sin monto en pesos), con
   sus propias reglas y su fila en «Efecto en los bonos» de cada justificación. Productos 4 lee el resultado de ese
   bono por su identificador, no por un nombre escrito en el código. Al crearlo se llena con lo que hace hoy (cualquier
   cargo y contrato, mismas faltas que Compromiso), así nada cambia hasta que alguien lo cambie.
8. **Columnas del informe (O), hecho en B2:** el informe de cierre de un área muestra todos los bonos que corresponden a las
   personas de esa área según las reglas de cada bono, y no muestra un bono que nadie del área tiene (decisión de la
   persona dueña, 22-11-2026: «que se muestre todo lo que corresponde»; el cierre es por área). Así Operador Línea,
   Retail y Supervisor salen en el informe de Producción.

### Etapa B4 · Historial de cargos y «Cambiar labor desde una fecha» (corrige G, H)

- **Historial de cargos** con fecha de inicio y de fin, motivo y quién lo hizo, igual que el de áreas. Carga inicial:
  el cargo actual de cada persona desde su fecha de ingreso.
- **Botón «Cambiar labor desde una fecha»** en la ficha del empleado (y en la ventana de la persona en la grilla):
  cargo nuevo (de la lista), fecha desde, motivo. Antes de guardar muestra qué bonos gana y cuáles pierde en el período.
  No deja una fecha dentro de un período cerrado. Queda en la auditoría. La ficha muestra los cargos anteriores.
- **El bono usa el cargo de cada día del período, en proporción** (decisión de la persona dueña, 22-11-2026). Un bono
  ligado a un cargo se paga por los días de turno en que la persona tuvo ese cargo: monto × días en ese cargo / días de
  turno del período, y sobre esos días se aplica el efecto de las faltas y justificaciones. Ejemplo: período de 22 días
  de turno, Operario Cloro los primeros 10 y Operador de Línea desde el 11: Cloro 50.000 × 10/22 y Operador Línea
  30.000 × 12/22. Un bono que no depende del cargo (Compromiso) no cambia, salvo que el cargo nuevo esté excluido.
- **Aviso por correo del cambio de labor (nuevo).** Al guardar «Cambiar labor desde una fecha» se envía un correo con
  la persona, el cargo anterior y el nuevo, la fecha desde, el motivo, quién lo hizo y qué bonos gana o pierde en el
  período. Va a los correos de «Avisos generales» (Configuración → Correo; decisión de la persona dueña, 22-11-2026),
  con el mismo sistema de correos del cierre. Se envía solo con los correos encendidos en el servidor.
- La tabla de «bonos asignados con fecha» se reemplaza por el historial de cargos (o se elimina si no hace falta).

### Etapa B5 · Bonos guardados al cerrar (corrige I, B)

- Al cerrar un período se guarda el resultado de los bonos de cada persona (bono, monto, motivo).
- El informe y el Excel de un período cerrado leen lo guardado: volver a sacarlos da siempre lo mismo.
- Mayo a Octubre se dejan como están: lo que ya se pagó no se toca (decisión de la persona dueña, 22-11-2026).

### Etapa B6 · Orden (J, K)

- La Bolsa por sus dos nombres de tipo; quitar el campo «labor requerida» que no existe.

### Orden recomendado

B1 → B2 → B3 → B4 → B5 → B6. B1 va primero porque B2 muestra montos y deben salir bien calculados.

---

## 4. Dudas para conversar

### 4.1 Respondidas por la persona dueña (22-11-2026)

- **Justificaciones:** no se trata de una licencia en particular; cualquier justificación se configura (B3.1).
- **Inasistencia sin justificar:** hace perder todo bono, y debe poder configurarse desde la pantalla (B3.1).
- **Cambio de labor a mitad de período:** proporcional a los días en cada labor; aviso por correo del cambio (B4).
- **Meses ya pagados (Mayo a Octubre):** no se tocan (B1, B5).
- **Temporales sin Transporte ni Operador Línea** y **exclusiones de Compromiso distintas por contrato:** dependen de la
  configuración de cada bono; el plan no las cambia.
- **Productos 4:** configurarlo como un bono, sin nada escrito en el código (B3.7).
- **Asistencia mínima:** no existe; se quita (B3.2).
- **Cargos con dos escrituras:** el cargo es único; quedan «AYUDANTE DE BODEGA» y «ASISTENTE FACTURA» (hecho el
  22-11-2026). Los tres cargos cortados por BioAlba se dejan así (vacío Q).
- **Áreas del bono:** el informe de cada área muestra todo lo que corresponde a sus personas (B3.8).
- **Correo del cambio de labor:** a «Avisos generales» (B4).

### 4.2 Abiertas

Ninguna por ahora.

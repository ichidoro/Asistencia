"""
Reglas de marcaciones: definiciones puras (sin base de datos).

Una regla dice, para una SECUENCIA exacta de marcas de una jornada (ENTRADA y
SALIDA, con el tipo ya corregido por una persona si lo hubo y con los dobles
toques ya quitados), cómo debe leerla el motor y qué se le ofrece a la persona
que revisa.

Las reglas pertenecen al TIPO de horario (tipo_programacion de `turnos`), nunca
a un turno ni a un área. Solo Ciclo Inteligente usa reglas; Bolsa Flexible
conserva su lógica.

Las reglas NO se escriben en el código: viven en la tabla `reglas_marcas` y se
crean y configuran desde la pantalla (las secuencias aparecen solas desde las
marcas reales, en la bandeja «Secuencias encontradas sin regla»). Aquí solo está
la lógica: los valores posibles, la validación y cómo se nombran las marcas.
Internamente una secuencia se guarda como texto de una letra por marca; hacia la
persona se muestra siempre con la palabra completa (ENTRADA, SALIDA).
"""
import json
import re

TIPOS_HORARIO_CON_REGLAS = ('CICLO_INTELIGENTE',)

LECTURAS = ('RELOJ', 'EXTREMOS', 'ORDEN', 'ALTERNADA', 'NINGUNA')
# RELOJ    = leer las marcas tal como las rotuló el reloj (con sus correcciones).
# EXTREMOS = la primera marca es la ENTRADA del día y la última la SALIDA; las del
#            medio solo valen como pausa si son una SALIDA seguida de una ENTRADA.
# ORDEN    = en el orden que indica la persona en la pantalla: para cada marca de la secuencia, ENTRADA (E),
#            SALIDA (S) o «no se usa» (-). Se guarda en `orden_marcas` (p. ej. «E--S»). La pantalla
#            lo propone alternando y la persona lo cambia. Sin las que no se usan debe quedar ENTRADA · SALIDA
#            repetido: así el motor puede calcular el día. No cambia las marcas: solo cómo se leen.
# ALTERNADA = el orden que propone el sistema: por hora, la primera es ENTRADA, la siguiente SALIDA, y así
#             alternando (ENTRADA · SALIDA · ENTRADA · SALIDA…). Una SALIDA seguida de una ENTRADA a mitad del
#             día es una pausa. Solo para secuencias con número PAR de marcas: con un número impar el orden no es
#             seguro (falta o sobra una marca). No cambia las marcas: solo cómo se leen.
# NINGUNA  = no leer: el día queda en anomalía hasta que una persona lo resuelva.

COLACIONES = ('TURNO', 'MEDIDA', 'NINGUNA')
# TURNO  = se descuenta la colación automática del horario asignado.
# MEDIDA = se mide con las marcas de la pausa; sin pausa completa rige la del horario.
#          (El descuento siempre es el mayor entre la del horario y la medida.)
# NINGUNA = no se descuenta colación.

ELECCIONES_COLACION = ('PARECIDA', 'CORTE_UMBRAL')
# Solo cuando el día tiene dos pausas o más (con una sola pausa, esa pausa es la colación):
# PARECIDA     = la colación es la pausa que más se parece en minutos a la colación del horario.
# CORTE_UMBRAL = las pausas que terminan antes de la ENTRADA del horario más su «Mínimo para descontar»
#                (umbral de colación) son permiso; entre las demás, la que más se parece en minutos.
#                Si ninguna termina después de esa hora, o el horario tiene mínimo 0, decide como PARECIDA.

ACCIONES = ('CALCULA', 'CALCULA_Y_REVISA', 'SOLO_REVISA')
# CALCULA          = calcula y listo, sin aviso.
# CALCULA_Y_REVISA = calcula igual y el día queda en «Días por revisar» (triángulo).
# SOLO_REVISA      = no calcula (anomalía) hasta que una persona lo resuelva.

OPCIONES_REVISION = ('AGREGAR_ENTRADA', 'AGREGAR_SALIDA', 'RECLASIFICAR', 'NO_SE_USA', 'CONFIRMAR')
# NO_SE_USA = quien revisa indica que una marca del reloj no se usa ese día (sobra). La marca no se borra: queda
#             guardada como «No se usa» en logs_tipo_override y el cálculo la deja fuera; se puede deshacer.
TIPO_NO_SE_USA = 'No se usa'

# Cómo se llama cada marca hacia la persona: siempre la palabra completa.
PALABRA_MARCA = {'E': 'ENTRADA', 'S': 'SALIDA'}
_LETRA_DE_PALABRA = {v: k for k, v in PALABRA_MARCA.items()}

_RE_SECUENCIA = re.compile(r'^[ES]{1,12}$')

# Marcador estable que el motor escribe en las observaciones de un día cuya regla
# lo manda a revisión. La lista «Días por revisar», el triángulo de la grilla y el
# bloqueo del cierre lo buscan tal cual; no cambiarlo sin recalcular el tramo abierto.
MARCA_REVISION_REGLA = 'Revisar las marcas (regla '
# Se lee con la palabra completa (lo que escribe el motor) y también con letras
# (lo que escribía antes), para no perder días ya anotados.
_TOKEN = r'(?:ENTRADA|SALIDA|E|S)'
_RE_MARCADOR = re.compile(re.escape(MARCA_REVISION_REGLA) + r'(' + _TOKEN + r'(?: · ' + _TOKEN + r'){0,11})\)')


def secuencia_en_palabras(secuencia, separador: str = ' · ') -> str:
    """'ESE' → 'ENTRADA · SALIDA · ENTRADA'. Lo que no sea una marca conocida se deja tal cual."""
    return separador.join(PALABRA_MARCA.get(c, c) for c in str(secuencia or ''))


def secuencia_en_revision(observaciones) -> str:
    """Si las observaciones de un día traen el marcador de revisión, devuelve su
    secuencia interna ('SSES'); si no, ''."""
    m = _RE_MARCADOR.search(observaciones or '')
    if not m:
        return ''
    return ''.join(_LETRA_DE_PALABRA.get(t, t) for t in m.group(1).split(' · '))


def firma_marcas(marcas_consumidas_ids) -> str:
    """Firma estable del conjunto de marcas que usó un día (ids ordenados, separados
    por coma). Una confirmación de revisión vale mientras la firma no cambie: si al
    día le llegan marcas nuevas, la firma cambia y el día vuelve a la lista."""
    if isinstance(marcas_consumidas_ids, str):
        try:
            marcas_consumidas_ids = json.loads(marcas_consumidas_ids or '[]')
        except ValueError:
            return ''
    try:
        return ','.join(str(i) for i in sorted(int(x) for x in (marcas_consumidas_ids or [])))
    except (TypeError, ValueError):
        return ''


def pausas_de(secuencia, lectura, orden=None) -> int:
    """Cuántas pausas (una SALIDA seguida de una ENTRADA) tiene el día según cómo se leen sus marcas.
    RELOJ: se leen como las marcó el reloj. EXTREMOS: la primera es la ENTRADA y la última la SALIDA, y las del
    medio solo cuentan como pausa si son una SALIDA seguida de una ENTRADA. NINGUNA: no se calcula."""
    s = str(secuencia or '')
    if lectura == 'NINGUNA' or len(s) < 4:
        return 0
    if lectura == 'ALTERNADA':
        return len(s) // 2 - 1 if len(s) % 2 == 0 else 0
    if lectura == 'ORDEN':
        usadas = str(orden or '').replace(MARCA_NO_SE_USA, '')
        return len(usadas) // 2 - 1 if _RE_BIEN_MARCADA.fullmatch(usadas) else 0
    if lectura == 'RELOJ':
        pares, i = [], 0
        while i < len(s) - 1:
            if s[i] == 'E' and s[i + 1] == 'S':
                pares.append(i)
                i += 2
            else:
                i += 1
        return max(0, len(pares) - 1)
    medio, n, j = s[1:-1], 0, 0
    while j < len(medio) - 1:
        if medio[j] == 'S' and medio[j + 1] == 'E':
            n += 1
            j += 2
        else:
            j += 1
    return n


def validar_regla(regla: dict) -> str:
    """Devuelve '' si la regla es válida, o el motivo del rechazo en palabras simples."""
    sec = str(regla.get('secuencia') or '')
    if not _RE_SECUENCIA.fullmatch(sec):
        return "La secuencia solo puede tener marcas de ENTRADA y SALIDA (hasta 12 marcas)."
    lectura = regla.get('lectura')
    colacion = regla.get('colacion')
    accion = regla.get('accion')
    opciones = regla.get('opciones_revision') or []
    if lectura not in LECTURAS:
        return "Cómo se leen las marcas: valor desconocido."
    if colacion not in COLACIONES:
        return "Colación: valor desconocido."
    if (regla.get('eleccion_colacion') or 'PARECIDA') not in ELECCIONES_COLACION:
        return "Cuál pausa es la colación: valor desconocido."
    if accion not in ACCIONES:
        return "Qué hace el sistema: valor desconocido."
    if not isinstance(opciones, list) or len(set(opciones)) != len(opciones):
        return "Las opciones de revisión vienen repetidas o mal formadas."
    for op in opciones:
        if op not in OPCIONES_REVISION:
            return f"Opción de revisión desconocida: {op}."
    if len(sec) == 1 and lectura != 'NINGUNA':
        return "Con una sola marca no se puede calcular: la lectura debe ser «no leer»."
    if lectura == 'ORDEN':
        motivo = validar_orden(sec, regla.get('orden_marcas'))
        if motivo:
            return motivo
    if lectura == 'ALTERNADA' and len(sec) % 2 == 1:
        return ("«Como las ordena el sistema» solo vale con un número par de marcas: con un número impar "
                "el orden no es seguro (falta o sobra una marca).")
    if lectura == 'NINGUNA' and accion != 'SOLO_REVISA':
        return "Si las marcas no se leen, el día solo puede quedar en revisión."
    if accion == 'CALCULA' and opciones:
        return "Si el día se calcula sin aviso, no corresponden opciones de revisión."
    if accion != 'CALCULA' and not opciones:
        return "Si el día va a revisión, elija al menos una opción para quien revisa."
    if no_calcula(regla) and _RE_BIEN_MARCADA.fullmatch(sec):
        return ("Una secuencia bien marcada (ENTRADA · SALIDA) es la salida de todas las revisiones: "
                "siempre debe calcularse. Elija «Calcular» o «Avisar, pero calcular igual».")
    if no_calcula(regla) and 'CONFIRMAR' in opciones:
        return ("«Confirmar que está bien» no sirve si el día queda sin calcular: confirmarlo lo saca de la "
                "lista, pero sigue sin horas y bloquea el cierre. Quítelo.")
    if accion != 'CALCULA' and 'CONFIRMAR' not in opciones_efectivas(regla) and not tiene_salida(sec, opciones):
        return ("Con estas opciones nadie podría dejar el día bien marcado (ENTRADA · SALIDA). "
                "Agregue «Escribir la SALIDA que falta», «Escribir la ENTRADA que falta», "
                "«Cambiar si una marca es ENTRADA o SALIDA» o «Una marca no se usa», según corresponda.")
    return ''


MARCA_NO_SE_USA = '-'


def validar_orden(secuencia: str, orden) -> str:
    """'' si el orden indicado por la persona sirve para calcular, o el motivo en palabras simples.
    Una letra por marca: E (ENTRADA), S (SALIDA) o - (no se usa). Sin las que no se usan debe quedar
    ENTRADA · SALIDA repetido."""
    orden = str(orden or '')
    sec = str(secuencia or '')
    if len(orden) != len(sec) or any(c not in ('E', 'S', MARCA_NO_SE_USA) for c in orden):
        return "Indique para cada marca si se lee como ENTRADA, SALIDA o si no se usa."
    if not _RE_BIEN_MARCADA.fullmatch(orden.replace(MARCA_NO_SE_USA, '')):
        return ("Con ese orden el día no se puede calcular: sin las marcas que no se usan, tiene que quedar "
                "ENTRADA · SALIDA (o ENTRADA · SALIDA · ENTRADA · SALIDA…), empezando por una ENTRADA y "
                "terminando en una SALIDA.")
    return ''


def orden_propuesto(secuencia: str) -> str:
    """La propuesta del sistema para el orden: la primera ENTRADA, la última SALIDA y las del medio alternando
    (la misma que muestra la ventana «Corregir marcas»). Con un número impar no es segura: la persona decide cuál
    no se usa."""
    n = len(str(secuencia or ''))
    o = ['E' if i % 2 == 0 else 'S' for i in range(n)]
    if n >= 2:
        o[-1] = 'S'
    return ''.join(o)


def no_calcula(regla: dict) -> bool:
    """True si la regla deja el día sin calcular (anomalía) hasta que una persona cambie las marcas."""
    return regla.get('accion') == 'SOLO_REVISA' or regla.get('lectura') == 'NINGUNA'


def opciones_efectivas(regla: dict, estado_dia: str = '') -> list:
    """Las opciones que de verdad se ofrecen a quien revisa. «Confirmar» solo existe cuando el día
    ya está calculado (regla «Avisar, pero calcular igual» y el día no quedó en anomalía): confirmar un
    día sin horas lo sacaría de la lista sin resolverlo."""
    ops = [o for o in (regla.get('opciones_revision') or []) if o in OPCIONES_REVISION]
    if no_calcula(regla) or regla.get('accion') != 'CALCULA_Y_REVISA' or str(estado_dia or '').upper() == 'ANOMALIA':
        ops = [o for o in ops if o != 'CONFIRMAR']
    return ops


_RE_BIEN_MARCADA = re.compile(r'^(ES)+$')


def secuencias_alcanzables(secuencia: str, opciones) -> set:
    """Secuencias a las que puede llegar quien revisa en una sola corrección, usando solo las opciones
    permitidas: escribir una ENTRADA y/o una SALIDA a cualquier hora (en cualquier posición) y, si puede
    cambiar el tipo, darle a cada marca el tipo que quiera."""
    ops = set(opciones or [])
    actuales = {str(secuencia or '')}
    for op, letra in (('AGREGAR_ENTRADA', 'E'), ('AGREGAR_SALIDA', 'S')):
        if op in ops:
            actuales |= {s[:i] + letra + s[i:] for s in actuales for i in range(len(s) + 1)}
    if 'NO_SE_USA' in ops:
        # Una o más marcas pueden quedar sin usar (sin bajar de una marca)
        nuevas = set(actuales)
        while True:
            mas = {s[:i] + s[i + 1:] for s in nuevas for i in range(len(s)) if len(s) > 1} - nuevas
            if not mas:
                break
            nuevas |= mas
        actuales = nuevas
    if 'RECLASIFICAR' in ops:
        largos = {len(s) for s in actuales}
        actuales |= {''.join('ES'[(m >> k) & 1] for k in range(n)) for n in largos for m in range(2 ** n)}
    return actuales


def tiene_salida(secuencia: str, opciones) -> bool:
    """True si con las opciones permitidas el día puede quedar bien marcado (ENTRADA · SALIDA repetido),
    que el motor siempre calcula por pares."""
    return any(_RE_BIEN_MARCADA.fullmatch(s) for s in secuencias_alcanzables(secuencia, opciones))


# Orden de los grupos en la pantalla. El número de cada regla («Regla N») sale de este orden
# (grupo y, dentro del grupo, la más antigua primero) la primera vez y queda guardado en la base:
# una regla nueva toma el número siguiente y las que ya tienen número no se mueven.
ORDEN_GRUPOS = ('Bien marcadas', 'Se repite un tipo', 'Falta una marca', 'Una sola marca')


def numerar_sin_numero(reglas, ultimo: int = 0) -> dict:
    """{id: número} para las reglas que todavía no tienen número, a continuación de `ultimo`."""
    pendientes = sorted((r for r in reglas if not r.get('numero')),
                        key=lambda r: (ORDEN_GRUPOS.index(grupo_de_secuencia(r['secuencia'])), r['id']))
    return {r['id']: ultimo + i for i, r in enumerate(pendientes, 1)}


def grupo_de_secuencia(sec: str) -> str:
    """Familia de una secuencia, para agrupar en la pantalla."""
    if len(sec) == 1:
        return 'Una sola marca'
    if re.fullmatch(r'(ES)+', sec):
        return 'Bien marcadas'
    if any(sec[i] == sec[i + 1] for i in range(len(sec) - 1)):
        return 'Se repite un tipo'
    return 'Falta una marca'


def _min_reloj(hora) -> int:
    """'HH:MM[:SS]' (o 'YYYY-MM-DD HH:MM:SS') → minutos del día."""
    h = str(hora or '')
    h = h[11:16] if len(h) >= 16 and h[4] == '-' else h[:5]
    hh, mm = h.split(':')
    return int(hh) * 60 + int(mm)


def _dist_reloj(a: int, b: int) -> int:
    """Distancia en el reloj de 24 horas (sirve para horarios que cruzan la medianoche)."""
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def propuesta_tres_marcas(marcas, entrada, salida, colacion_min: int, colacion_max: int, colacion_horario: int = 0):
    """Propuesta para un día con 3 marcas que se usan (falta una o sobra una), comparándolas con el horario del día.
    `marcas`: 'YYYY-MM-DD HH:MM:SS' en orden. `entrada`/`salida`: horas del horario. Una pausa «es colación» si dura
    entre `colacion_min` y `colacion_max` minutos (ajustes de la pestaña Reglas de marcaciones).
      1 · falta la SALIDA final: la 1.ª calza con la entrada y la 2.ª y la 3.ª son una colación → ENTRADA·SALIDA·ENTRADA,
          y luego se escribe la SALIDA del horario (el día queda como la regla 2).
      2 · falta la ENTRADA inicial: la 3.ª calza con la salida y la 1.ª y la 2.ª son una colación → SALIDA·ENTRADA·SALIDA,
          y luego se escribe la ENTRADA del horario (regla 2).
      6 · sobra la del medio: la 1.ª calza con la entrada, la 3.ª con la salida y ninguna pausa es colación → la del medio
          no se usa (regla 1, con la colación del horario).
    Cada propuesta trae también `caminos`: para «Se le olvidó marcar la ENTRADA/SALIDA», qué tipo queda en cada marca y qué
    hora se propone para la marca nueva, de modo que una sola corrección deje el día ENTRADA · SALIDA · ENTRADA · SALIDA.
    En 6, además de «no se usa», se puede escribir la marca de colación que falta: si la del medio fue la salida a colación,
    la ENTRADA de vuelta a esa hora + `colacion_horario` minutos (los de su horario); si fue la vuelta, la SALIDA a esa hora
    − esos minutos. Sin minutos de colación en el horario no se proponen.
    Si no calza con ninguna, devuelve None y decide la persona. «Calza con la entrada» = está más cerca de la entrada que
    de la salida del horario (y al revés). Una pausa del tamaño de una colación no cuenta como colación si la marca del
    extremo está más cerca de la hora del horario que de su vecina (es la entrada o la salida del día)."""
    if len(marcas or []) != 3 or not entrada or not salida:
        return None
    from datetime import datetime as _dt
    try:
        t = [_dt.strptime(str(m)[:19], '%Y-%m-%d %H:%M:%S') for m in marcas]
        he, hs = _min_reloj(entrada), _min_reloj(salida)
    except (ValueError, IndexError):
        return None
    m = [x.hour * 60 + x.minute for x in t]
    g12 = (t[1] - t[0]).total_seconds() / 60.0
    g23 = (t[2] - t[1]).total_seconds() / 60.0
    es_col = lambda g: colacion_min <= g <= colacion_max
    cerca_entrada = lambda x: _dist_reloj(x, he) < _dist_reloj(x, hs)
    cerca_salida = lambda x: _dist_reloj(x, hs) < _dist_reloj(x, he)
    # La 1.ª ES la entrada si queda más cerca de la entrada del horario que de la marca siguiente; la 3.ª ES la salida si
    # queda más cerca de la salida del horario que de la marca anterior (así una pausa larga que termina justo a la hora de
    # salida no se confunde con una colación).
    m1_es_entrada = _dist_reloj(m[0], he) < g12
    m3_es_salida = _dist_reloj(m[2], hs) < g23
    hora = lambda x: f'{(x % 1440) // 60:02d}:{x % 60:02d}'
    hm = lambda x: hora(x)
    if cerca_entrada(m[0]) and cerca_salida(m[2]) and (not es_col(g12) or m1_es_entrada) and (not es_col(g23) or m3_es_salida):
        caminos = {}
        col = int(colacion_horario or 0)
        if col > 0:
            caminos['AGREGAR_ENTRADA'] = {
                'tipos': ['Entrada', 'Salida', 'Salida'], 'hora': hora(m[1] + col),
                'titulo': 'Se le olvidó marcar la vuelta de colación',
                'texto': f'Salió a colación a las {hm(m[1])}: se propone la ENTRADA a las {hora(m[1] + col)} ({col} min de su horario)'}
            caminos['AGREGAR_SALIDA'] = {
                'tipos': ['Entrada', 'Entrada', 'Salida'], 'hora': hora(m[1] - col),
                'titulo': 'Se le olvidó marcar la salida a colación',
                'texto': f'Volvió de colación a las {hm(m[1])}: se propone la SALIDA a las {hora(m[1] - col)} ({col} min de su horario)'}
        return {'combinacion': 6, 'tipos': ['Entrada', TIPO_NO_SE_USA, 'Salida'], 'falta': None, 'caminos': caminos}
    if es_col(g23) and not m3_es_salida and cerca_entrada(m[0]) and (not es_col(g12) or m1_es_entrada):
        return {'combinacion': 1, 'tipos': ['Entrada', 'Salida', 'Entrada'], 'falta': {'tipo': 'Salida', 'hora': hora(hs)},
                'caminos': {'AGREGAR_SALIDA': {'tipos': ['Entrada', 'Salida', 'Entrada'], 'hora': hora(hs),
                                               'titulo': 'Se le olvidó marcar la SALIDA',
                                               'texto': f'Se propone la SALIDA de su horario ({hora(hs)})'}}}
    if es_col(g12) and not m1_es_entrada and cerca_salida(m[2]) and (not es_col(g23) or m3_es_salida):
        return {'combinacion': 2, 'tipos': ['Salida', 'Entrada', 'Salida'], 'falta': {'tipo': 'Entrada', 'hora': hora(he)},
                'caminos': {'AGREGAR_ENTRADA': {'tipos': ['Salida', 'Entrada', 'Salida'], 'hora': hora(he),
                                                'titulo': 'Se le olvidó marcar la ENTRADA',
                                                'texto': f'Se propone la ENTRADA de su horario ({hora(he)})'}}}
    return None

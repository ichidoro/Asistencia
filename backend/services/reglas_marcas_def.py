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

LECTURAS = ('RELOJ', 'EXTREMOS', 'NINGUNA')
# RELOJ    = leer las marcas tal como las rotuló el reloj (con sus correcciones).
# EXTREMOS = la primera marca es la ENTRADA del día y la última la SALIDA; las del
#            medio solo valen como pausa si son una SALIDA seguida de una ENTRADA.
# NINGUNA  = no leer: el día queda en anomalía hasta que una persona lo resuelva.

COLACIONES = ('TURNO', 'MEDIDA', 'NINGUNA')
# TURNO  = se descuenta la colación automática del horario asignado.
# MEDIDA = se mide con las marcas de la pausa; sin pausa completa rige la del horario.
#          (El descuento siempre es el mayor entre la del horario y la medida.)
# NINGUNA = no se descuenta colación.

ACCIONES = ('CALCULA', 'CALCULA_Y_REVISA', 'SOLO_REVISA')
# CALCULA          = calcula y listo, sin aviso.
# CALCULA_Y_REVISA = calcula igual y el día queda en «Días por revisar» (triángulo).
# SOLO_REVISA      = no calcula (anomalía) hasta que una persona lo resuelva.

OPCIONES_REVISION = ('AGREGAR_ENTRADA', 'AGREGAR_SALIDA', 'RECLASIFICAR', 'CONFIRMAR')

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
    if accion not in ACCIONES:
        return "Qué hace el sistema: valor desconocido."
    if not isinstance(opciones, list) or len(set(opciones)) != len(opciones):
        return "Las opciones de revisión vienen repetidas o mal formadas."
    for op in opciones:
        if op not in OPCIONES_REVISION:
            return f"Opción de revisión desconocida: {op}."
    if regla.get('avisa_fuera_de_ciclo') not in (None, 0, 1, True, False):
        return "Avisar si no calza con ningún ciclo: valor desconocido."
    if len(sec) == 1 and lectura != 'NINGUNA':
        return "Con una sola marca no se puede calcular: la lectura debe ser «no leer»."
    if lectura == 'NINGUNA' and accion != 'SOLO_REVISA':
        return "Si las marcas no se leen, el día solo puede quedar en revisión."
    if accion == 'CALCULA' and opciones:
        return "Si el día se calcula sin aviso, no corresponden opciones de revisión."
    if accion != 'CALCULA' and not opciones:
        return "Si el día va a revisión, elija al menos una opción para quien revisa."
    return ''


def grupo_de_secuencia(sec: str) -> str:
    """Familia de una secuencia, para agrupar en la pantalla."""
    if len(sec) == 1:
        return 'Una sola marca'
    if re.fullmatch(r'(ES)+', sec):
        return 'Bien marcadas'
    if any(sec[i] == sec[i + 1] for i in range(len(sec) - 1)):
        return 'Se repite un tipo'
    return 'Falta una marca'

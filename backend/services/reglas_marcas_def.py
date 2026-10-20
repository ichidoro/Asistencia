"""
Reglas de marcaciones: definiciones puras (sin base de datos).

Una regla dice, para una SECUENCIA exacta de marcas de una jornada (E = Entrada,
S = Salida, con el tipo ya corregido por overrides y con los dobles toques ya
quitados), cómo debe leerla el motor y qué se le ofrece a la persona que revisa.

Las reglas pertenecen al TIPO de horario (tipo_programacion de `turnos`), nunca
a un turno ni a un área. Hoy solo se siembran reglas para CICLO_INTELIGENTE;
BOLSA_FLEXIBLE queda sin reglas y conserva su lógica actual.

IMPORTANTE (etapa 1): estas reglas todavía NO las usa el motor de cálculo.
Nacen todas con activa = 0. En la etapa siguiente, el botón «Correr esta regla»
las irá encendiendo una a una, recalculando solo los días del tramo abierto
(y de las áreas cuyo tramo esté abierto). Los períodos cerrados no se tocan.
"""
import json
import re

TIPOS_HORARIO_CON_REGLAS = ('CICLO_INTELIGENTE',)

LECTURAS = ('RELOJ', 'EXTREMOS', 'NINGUNA')
# RELOJ    = leer las marcas tal como las rotuló el reloj (con sus correcciones).
# EXTREMOS = la primera marca es la Entrada del día y la última la Salida; las del
#            medio solo valen como pausa si son una Salida seguida de una Entrada.
# NINGUNA  = no leer: el día queda en anomalía hasta que una persona lo resuelva.

COLACIONES = ('TURNO', 'MEDIDA', 'NINGUNA')
# TURNO  = se descuenta la colación automática del turno asignado.
# MEDIDA = se mide con las marcas de la pausa; sin pausa completa rige la del turno.
#          (El descuento siempre es el mayor entre la pactada y la medida.)
# NINGUNA = no se descuenta colación.

ACCIONES = ('CALCULA', 'CALCULA_Y_REVISA', 'SOLO_REVISA')
# CALCULA          = calcula y listo, sin aviso.
# CALCULA_Y_REVISA = calcula igual y el día queda en «Días por revisar» (triángulo).
# SOLO_REVISA      = no calcula (anomalía) hasta que una persona lo resuelva.

OPCIONES_REVISION = ('AGREGAR_ENTRADA', 'AGREGAR_SALIDA', 'RECLASIFICAR', 'CONFIRMAR')

# Notas frecuentes de la pestaña: el diagnóstico de qué le pasó a las marcas.
# La pantalla las ofrece en una lista desplegable (más «Otra (escribir)», que
# abre el texto libre). Son solo informativas: no cambian cómo se calcula el día,
# y la nota guardada sigue siendo texto (una nota antigua que no calce con
# ninguna se muestra como «Otra» con su texto tal cual).
NOTAS_FRECUENTES = (
    'Día bien marcado: entrada, salida y pausas completas.',
    'Falta la Entrada.',
    'Falta la Salida.',
    'Falta una marca de la colación (la de ir o la de volver).',
    'Marca mal rotulada: una Entrada que era Salida, o al revés.',
    'Marca repetida (doble toque).',
    'Dos pausas: una es la colación, la otra un permiso.',
    'Caso raro: revisar siempre.',
)

_RE_SECUENCIA = re.compile(r'^[ES]{1,12}$')

# Marcador estable que el motor escribe en las observaciones de un día cuya regla
# lo manda a revisión. La lista «Días por revisar», el triángulo de la grilla y el
# bloqueo del cierre lo buscan tal cual; no cambiarlo sin recalcular el tramo abierto.
MARCA_REVISION_REGLA = 'Revisar las marcas (regla '
_RE_MARCADOR = re.compile(re.escape(MARCA_REVISION_REGLA) + r'([ES](?: · [ES]){0,11})\)')


def secuencia_en_revision(observaciones) -> str:
    """Si las observaciones de un día traen el marcador de revisión, devuelve su
    secuencia ('SSES'); si no, ''."""
    m = _RE_MARCADOR.search(observaciones or '')
    return m.group(1).replace(' · ', '') if m else ''


def firma_marcas(marcas_consumidas_ids) -> str:
    """Firma estable del conjunto de marcas que usó un día (ids ordenados, separados
    por coma). Una confirmación de revisión vale mientras la firma no cambie: si al
    día le llegan marcas nuevas, la firma cambia y el día vuelve a la lista."""
    import json
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
        return "La secuencia solo puede tener letras E y S (hasta 12 marcas)."
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
    if len(sec) == 1 and lectura != 'NINGUNA':
        return "Con una sola marca no se puede calcular: la lectura debe ser «no leer»."
    if lectura == 'NINGUNA' and accion != 'SOLO_REVISA':
        return "Si las marcas no se leen, el día solo puede quedar en revisión."
    if accion == 'CALCULA' and opciones:
        return "Si el día se calcula sin aviso, no corresponden opciones de revisión."
    if accion != 'CALCULA' and not opciones:
        return "Si el día va a revisión, elija al menos una opción para quien revisa."
    return ''


# ─────────────────────────────────────────────────────────────────────────────
# Semilla: las 28 secuencias encontradas en la base real (26-04 → 19-10-2026,
# jornadas de Ciclo Inteligente con marcas del reloj) más la 'S' sola, con los
# valores que decidió el dueño el 20-10-2026. Todas nacen APAGADAS (activa = 0).
# La siembra usa INSERT OR IGNORE: lo que el dueño edite nunca se pisa.
# ─────────────────────────────────────────────────────────────────────────────
def _r(sec, lectura, colacion, accion, opciones, nota):
    return {
        'tipo_horario': 'CICLO_INTELIGENTE',
        'secuencia': sec,
        'lectura': lectura,
        'colacion': colacion,
        'accion': accion,
        'opciones_revision': opciones,
        'activa': 0,
        'nota': nota,
    }


REGLAS_SEMILLA = [
    # ── Una sola marca ──
    _r('E', 'NINGUNA', 'TURNO', 'SOLO_REVISA', ['AGREGAR_SALIDA'],
       'Una sola marca: falta la Salida. Anomalía hasta que se agregue.'),
    _r('S', 'NINGUNA', 'TURNO', 'SOLO_REVISA', ['AGREGAR_ENTRADA'],
       'Una sola marca: falta la Entrada. Anomalía hasta que se agregue.'),
    # ── Bien marcadas ──
    _r('ES', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Entrada y salida sin marcas de colación: colación automática del turno.'),
    _r('ESES', 'RELOJ', 'MEDIDA', 'CALCULA', [],
       'Día completo: la pausa del medio es la colación medida.'),
    _r('ESESES', 'RELOJ', 'MEDIDA', 'CALCULA', [],
       'Dos pausas: la más parecida a la colación del turno es la colación; la otra, permiso.'),
    # ── Se repite un tipo: una marca quedó mal rotulada → extremos ──
    _r('EE', 'EXTREMOS', 'TURNO', 'CALCULA_Y_REVISA', ['RECLASIFICAR', 'CONFIRMAR'],
       'Dos Entradas: la última es la salida mal rotulada. Revisar y corregir.'),
    _r('SS', 'EXTREMOS', 'TURNO', 'CALCULA_Y_REVISA', ['RECLASIFICAR', 'CONFIRMAR'],
       'Dos Salidas: la primera es la entrada mal rotulada. Revisar y corregir.'),
    _r('EEE', 'EXTREMOS', 'TURNO', 'CALCULA_Y_REVISA', ['RECLASIFICAR', 'CONFIRMAR'],
       'Tres Entradas: rótulos malos. Revisar y corregir.'),
    _r('SSSS', 'EXTREMOS', 'TURNO', 'CALCULA_Y_REVISA', ['RECLASIFICAR', 'CONFIRMAR'],
       'Cuatro Salidas: jornada completa con todos los rótulos malos. Revisar y corregir.'),
    _r('ESS', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Falta la Entrada del regreso de colación: extremos y colación del turno.'),
    _r('EES', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Falta la Salida de ir a colación: extremos y colación del turno.'),
    _r('ESSS', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Salidas repetidas: extremos y colación del turno.'),
    _r('EEES', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Entradas repetidas: extremos y colación del turno.'),
    _r('SSES', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Primera marca mal rotulada; la pausa del medio es la colación medida.'),
    _r('ESEE', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Última marca mal rotulada; la pausa del medio es la colación medida.'),
    _r('EESS', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Pausa con los rótulos al revés: extremos y colación del turno.'),
    _r('SSEE', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Extremos mal rotulados; la pausa del medio es la colación medida.'),
    _r('ESESS', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Una salida repetida al final; colación medida con la pausa.'),
    _r('EESES', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Una entrada repetida al inicio; colación medida con la pausa.'),
    _r('ESEES', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Una entrada repetida al medio; colación medida con la pausa.'),
    _r('ESSES', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Una salida repetida al medio; colación medida con la pausa.'),
    _r('EESSS', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Marcas repetidas en ambos extremos: extremos y colación del turno.'),
    _r('ESSSS', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Salidas repetidas: extremos y colación del turno.'),
    _r('EEEEES', 'EXTREMOS', 'TURNO', 'CALCULA', [],
       'Entradas repetidas: extremos y colación del turno.'),
    _r('ESEEES', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Entradas repetidas tras la pausa; colación medida con la pausa.'),
    _r('ESESSS', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Salidas repetidas al final; colación medida con la pausa.'),
    _r('SSESES', 'EXTREMOS', 'MEDIDA', 'CALCULA', [],
       'Primera marca mal rotulada; pausas medidas.'),
    # ── Falta una marca (alternan pero son impares) ──
    _r('ESE', 'EXTREMOS', 'TURNO', 'CALCULA_Y_REVISA', ['AGREGAR_SALIDA', 'CONFIRMAR'],
       'Termina en Entrada: falta la Salida final. Se calcula con extremos y se revisa.'),
    _r('SES', 'EXTREMOS', 'TURNO', 'CALCULA_Y_REVISA', ['RECLASIFICAR', 'AGREGAR_ENTRADA', 'CONFIRMAR'],
       'Parte con Salida: probable entrada mal rotulada, o falta la Entrada.'),
]


def filas_semilla():
    """Filas listas para INSERT (opciones como JSON)."""
    return [
        (r['tipo_horario'], r['secuencia'], r['lectura'], r['colacion'], r['accion'],
         json.dumps(r['opciones_revision']), r['activa'], r['nota'])
        for r in REGLAS_SEMILLA
    ]


def grupo_de_secuencia(sec: str) -> str:
    """Familia de una secuencia, para agrupar en la pantalla."""
    if len(sec) == 1:
        return 'Una sola marca'
    if re.fullmatch(r'(ES)+', sec):
        return 'Bien marcadas'
    if any(sec[i] == sec[i + 1] for i in range(len(sec) - 1)):
        return 'Se repite un tipo'
    return 'Falta una marca'

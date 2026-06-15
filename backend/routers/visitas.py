"""
Router Control de Visitas — Portería
Escaneo de cédula chilena (PDF417 + QR) vía Keyboard Wedge
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger
import re

from backend.core.database import get_db, Database
from backend.core.security import SecurityContext, get_current_user, RequirePermission

router = APIRouter(
    prefix="/visitas",
    tags=["Control de Visitas"]
)


# ============================================
# INICIALIZACIÓN DE TABLA
# ============================================
async def _ensure_table(db: Database):
    """Crea la tabla si no existe. Índice solo en PK para max velocidad de escritura."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS visitas_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT NOT NULL,
            nombre TEXT DEFAULT '',
            empresa TEXT DEFAULT '',
            motivo TEXT DEFAULT '',
            area_destino TEXT DEFAULT '',
            persona_contacto TEXT DEFAULT '',
            raw_scan TEXT DEFAULT '',
            tipo_documento TEXT DEFAULT 'MANUAL',
            tipo_marca TEXT NOT NULL DEFAULT 'E',
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            registrado_por_id INTEGER,
            registrado_por_nombre TEXT DEFAULT '',
            patente_vehiculo TEXT DEFAULT '',
            observaciones TEXT DEFAULT '',
            parse_ok INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Solo idx_visitas_rut_fecha: necesario para E/S toggle y consulta diaria
    # Compuesto = 1 índice, no 2, minimiza overhead de escritura en Turso
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_visitas_rut_fecha ON visitas_registros(rut, fecha)"
    )


# ============================================
# PARSER DE RUN CHILENO
# ============================================

def _limpiar_rut(rut_raw: str) -> str:
    """Limpia un RUT de puntos, guiones, espacios. Retorna formato XXXXXXXX-X."""
    rut = rut_raw.strip().upper()
    # Remover todo excepto dígitos, K, guion
    rut = re.sub(r'[^0-9Kk-]', '', rut)
    # Si no tiene guión, insertarlo antes del último caracter
    if '-' not in rut and len(rut) >= 2:
        rut = rut[:-1] + '-' + rut[-1]
    return rut.upper()


def _validar_rut(rut: str) -> bool:
    """Valida un RUT chileno con algoritmo módulo 11."""
    if not rut or '-' not in rut:
        return False
    try:
        cuerpo, dv = rut.split('-')
        cuerpo = cuerpo.replace('.', '').strip()
        dv = dv.strip().upper()
        if not cuerpo.isdigit() or len(cuerpo) < 6:
            return False
        # Módulo 11
        suma = 0
        mul = 2
        for d in reversed(cuerpo):
            suma += int(d) * mul
            mul = mul + 1 if mul < 7 else 2
        resto = suma % 11
        dv_calculado = str(11 - resto) if (11 - resto) < 10 else ('K' if (11 - resto) == 10 else '0')
        return dv == dv_calculado
    except Exception:
        return False


def _calcular_dv(cuerpo: str) -> str:
    """Calcula el dígito verificador de un RUT chileno."""
    try:
        cuerpo = cuerpo.replace('.', '').strip()
        suma = 0
        mul = 2
        for d in reversed(cuerpo):
            suma += int(d) * mul
            mul = mul + 1 if mul < 7 else 2
        resto = suma % 11
        dv = 11 - resto
        if dv == 11:
            return '0'
        elif dv == 10:
            return 'K'
        return str(dv)
    except Exception:
        return '0'


def parsear_cedula(raw_string: str) -> Dict[str, Any]:
    """
    Parser inteligente para cédula chilena.
    Detecta formato (PDF417/QR/directo) y extrae RUT.
    
    Retorna: { rut, nombre, tipo_documento, parse_ok, raw_clean }
    """
    raw = raw_string.strip()
    resultado = {
        'rut': '',
        'nombre': '',
        'tipo_documento': 'DESCONOCIDO',
        'parse_ok': False,
        'raw_clean': raw
    }

    if not raw:
        return resultado

    # ═══════════════════════════════════════════
    # ESTRATEGIA 1: RUT directo (input manual o teclado)
    # Formato: 12.345.678-9 o 12345678-9 o 123456789
    # ═══════════════════════════════════════════
    rut_directo = re.search(
        r'\b(\d{1,2}\.?\d{3}\.?\d{3}-?[0-9kK])\b', raw
    )
    if rut_directo and len(raw) < 20:
        rut = _limpiar_rut(rut_directo.group(1))
        if _validar_rut(rut):
            resultado['rut'] = rut
            resultado['tipo_documento'] = 'MANUAL'
            resultado['parse_ok'] = True
            return resultado

    # ═══════════════════════════════════════════
    # ESTRATEGIA 2: QR de cédula nueva
    # Contiene URL de validación del Registro Civil
    # Formato típico: https://portal.sidiv.registrocivil.cl/...
    # o cadena con hash criptográfico largo
    # ═══════════════════════════════════════════
    if 'registrocivil' in raw.lower() or 'sidiv' in raw.lower() or 'https://' in raw:
        resultado['tipo_documento'] = 'QR'
        # Patrón 1: parámetro Run= en la URL (con o sin DV)
        run_param = re.search(r'[Rr]un=(\d{7,8})(?:-?([0-9kK]))?', raw)
        if run_param:
            cuerpo = run_param.group(1)
            dv = run_param.group(2) or ''
            if dv:
                rut_candidato = f"{cuerpo}-{dv}"
            else:
                # Calcular DV si no viene
                rut_candidato = f"{cuerpo}-{_calcular_dv(cuerpo)}"
            rut_limpio = _limpiar_rut(rut_candidato)
            if _validar_rut(rut_limpio):
                resultado['rut'] = rut_limpio
                resultado['parse_ok'] = True
                return resultado
        # Patrón 2: RUT completo en cualquier parte del string
        rut_match = re.search(r'(\d{7,8})-?([0-9kK])', raw)
        if rut_match:
            rut_candidato = f"{rut_match.group(1)}-{rut_match.group(2)}"
            rut_limpio = _limpiar_rut(rut_candidato)
            if _validar_rut(rut_limpio):
                resultado['rut'] = rut_limpio
                resultado['parse_ok'] = True
                return resultado
        # Patrón 3: buscar todos los posibles
        todos_ruts = re.findall(r'(\d{7,8})[- ]?([0-9kK])', raw)
        for cuerpo, dv in todos_ruts:
            candidato = _limpiar_rut(f"{cuerpo}-{dv}")
            if _validar_rut(candidato):
                resultado['rut'] = candidato
                resultado['parse_ok'] = True
                return resultado
        # QR sin RUT parseable
        resultado['parse_ok'] = False
        return resultado

    # ═══════════════════════════════════════════
    # ESTRATEGIA 3: PDF417 de cédula antigua
    # El raw string contiene campos delimitados.
    # Patrones conocidos (reverse-engineered):
    #   - Delimitadores: \x1c \x1d \x1e | tabuladores | pipes
    #   - Campos: RUN, Apellidos, Nombres, FechaNac, Sexo, Nacionalidad
    #   - A veces el RUN aparece con puntos y guión
    # ═══════════════════════════════════════════
    # Detectar si parece PDF417 (multi-campo con delimitadores o largo > 30)
    has_delimiters = any(c in raw for c in ['\x1c', '\x1d', '\x1e', '\t', '|'])
    is_long_string = len(raw) > 30

    if has_delimiters or is_long_string:
        resultado['tipo_documento'] = 'PDF417'

        # Intentar splitear por delimitadores comunes
        for delim in ['\x1d', '\x1c', '\x1e', '|', '\t']:
            if delim in raw:
                campos = [c.strip() for c in raw.split(delim) if c.strip()]
                # Buscar RUT en cada campo
                for campo in campos:
                    rut_match = re.search(r'(\d{1,2}\.?\d{3}\.?\d{3})-?([0-9kK])', campo)
                    if rut_match:
                        candidato = _limpiar_rut(rut_match.group(0))
                        if _validar_rut(candidato):
                            resultado['rut'] = candidato
                            resultado['parse_ok'] = True
                            # Intentar extraer nombre del campo siguiente o anterior
                            idx = campos.index(campo)
                            if idx + 1 < len(campos):
                                posible_nombre = campos[idx + 1]
                                if re.match(r'^[A-ZÁÉÍÓÚÑ\s]+$', posible_nombre):
                                    resultado['nombre'] = posible_nombre.title()
                            return resultado
                break

        # Fallback: buscar cualquier patrón de RUT en todo el string
        todos_ruts = re.findall(r'(\d{1,2}\.?\d{3}\.?\d{3})-?([0-9kK])', raw)
        for cuerpo_raw, dv in todos_ruts:
            candidato = _limpiar_rut(f"{cuerpo_raw}-{dv}")
            if _validar_rut(candidato):
                resultado['rut'] = candidato
                resultado['parse_ok'] = True
                return resultado

        # PDF417 no parseable
        resultado['parse_ok'] = False
        return resultado

    # ═══════════════════════════════════════════
    # ESTRATEGIA 4: Fallback — buscar RUT en cualquier texto
    # ═══════════════════════════════════════════
    todos_ruts = re.findall(r'(\d{7,8})[.-]?([0-9kK])', raw)
    for cuerpo, dv in todos_ruts:
        candidato = _limpiar_rut(f"{cuerpo}-{dv}")
        if _validar_rut(candidato):
            resultado['rut'] = candidato
            resultado['tipo_documento'] = 'AUTO'
            resultado['parse_ok'] = True
            return resultado

    # Nada funcionó
    resultado['parse_ok'] = False
    return resultado


# ============================================
# ENDPOINTS
# ============================================

@router.post("/parsear/")
async def parsear_scan(
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.visitas"))
):
    """
    Solo parsea el raw_scan sin registrar. 
    Si el RUT ya visitó antes, auto-completa nombre/empresa del historial.
    """
    await _ensure_table(db)
    raw_scan = (data.get('raw_scan') or '').strip()
    if not raw_scan:
        raise HTTPException(status_code=400, detail="raw_scan vacío")

    parsed = parsear_cedula(raw_scan)
    nombre = parsed['nombre']
    empresa = ''
    motivo = ''
    area_destino = ''
    persona_contacto = ''
    visitas_previas = 0

    # Si tenemos RUT, buscar en historial para auto-completar
    if parsed['rut'] and parsed['parse_ok']:
        previo = await db.fetch_one(
            """SELECT nombre, empresa, motivo, area_destino, persona_contacto, 
                      COUNT(*) as total_visitas
               FROM visitas_registros 
               WHERE rut = ? AND nombre != '' AND nombre IS NOT NULL
               GROUP BY rut
               ORDER BY created_at DESC LIMIT 1""",
            (parsed['rut'],)
        )
        if previo:
            p = dict(previo)
            nombre = nombre or p.get('nombre', '')
            empresa = p.get('empresa', '')
            motivo = p.get('motivo', '')
            area_destino = p.get('area_destino', '')
            persona_contacto = p.get('persona_contacto', '')
            visitas_previas = p.get('total_visitas', 0)

    return {
        "rut": parsed['rut'],
        "nombre": nombre,
        "empresa": empresa,
        "motivo": motivo,
        "area_destino": area_destino,
        "persona_contacto": persona_contacto,
        "tipo_documento": parsed['tipo_documento'],
        "parse_ok": parsed['parse_ok'],
        "raw_scan": raw_scan,
        "visitante_conocido": visitas_previas > 0,
        "visitas_previas": visitas_previas
    }

@router.post("/registrar/")
async def registrar_visita(
    data: Dict[str, Any],
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.visitas"))
):
    """
    Registra una visita. Recibe raw_scan del Keyboard Wedge.
    Auto-detecta formato, parsea RUT, registra E/S.
    
    Body: {
        raw_scan: str,          // String del scanner (requerido si no hay rut)
        rut: str,               // RUT manual (si no viene raw_scan)
        nombre: str,
        empresa: str,
        motivo: str,
        area_destino: str,
        persona_contacto: str,
        patente_vehiculo: str,
        observaciones: str
    }
    """
    await _ensure_table(db)

    raw_scan = (data.get('raw_scan') or '').strip()
    rut_manual = (data.get('rut') or '').strip()
    nombre = (data.get('nombre') or '').strip()
    empresa = (data.get('empresa') or '').strip()
    motivo = (data.get('motivo') or '').strip()
    area_destino = (data.get('area_destino') or '').strip()
    persona_contacto = (data.get('persona_contacto') or '').strip()
    patente = (data.get('patente_vehiculo') or '').strip()
    observaciones = (data.get('observaciones') or '').strip()

    # Parser de cédula
    if raw_scan:
        parsed = parsear_cedula(raw_scan)
        rut = parsed['rut']
        tipo_doc = parsed['tipo_documento']
        parse_ok = parsed['parse_ok']
        if parsed['nombre'] and not nombre:
            nombre = parsed['nombre']
    elif rut_manual:
        rut = _limpiar_rut(rut_manual)
        tipo_doc = 'MANUAL'
        parse_ok = _validar_rut(rut)
    else:
        raise HTTPException(status_code=400, detail="Se requiere raw_scan o rut")

    if not rut and not raw_scan:
        raise HTTPException(status_code=400, detail="No se pudo extraer RUT. Ingrese manualmente.")

    # Si no tenemos RUT pero sí raw_scan, guardar con flag
    if not rut:
        rut = 'PENDIENTE'
        parse_ok = False

    # Fecha y hora
    now = datetime.now()
    fecha_hoy = now.strftime("%Y-%m-%d")
    hora_actual = now.strftime("%H:%M:%S")

    # Auto-detectar E/S: última marca de este RUT hoy
    if rut != 'PENDIENTE':
        ultima = await db.fetch_one(
            "SELECT tipo_marca FROM visitas_registros WHERE rut = ? AND fecha = ? ORDER BY hora DESC LIMIT 1",
            (rut, fecha_hoy)
        )
        tipo_marca = 'E' if (not ultima or ultima['tipo_marca'] == 'S') else 'S'
    else:
        tipo_marca = 'E'

    # Registrador
    registrador = getattr(current_user, 'nombre_completo', None) or getattr(current_user, 'username', 'Sistema')
    reg_id = getattr(current_user, 'user_id', None)

    await db.execute(
        """INSERT INTO visitas_registros 
           (rut, nombre, empresa, motivo, area_destino, persona_contacto,
            raw_scan, tipo_documento, tipo_marca, fecha, hora,
            registrado_por_id, registrado_por_nombre, patente_vehiculo,
            observaciones, parse_ok)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rut, nombre, empresa, motivo, area_destino, persona_contacto,
         raw_scan, tipo_doc, tipo_marca, fecha_hoy, hora_actual,
         reg_id, registrador, patente, observaciones, 1 if parse_ok else 0)
    )

    tipo_label = "ENTRADA" if tipo_marca == 'E' else "SALIDA"
    logger.info(f"[VISITA] {tipo_label}: RUT={rut} | {nombre} | {empresa} | {tipo_doc} | parse_ok={parse_ok}")

    return {
        "ok": True,
        "tipo_marca": tipo_marca,
        "tipo_label": tipo_label,
        "rut": rut,
        "nombre": nombre,
        "tipo_documento": tipo_doc,
        "parse_ok": parse_ok,
        "hora": hora_actual,
        "requiere_manual": not parse_ok
    }


@router.get("/estado-dia/")
async def get_estado_dia(
    fecha: Optional[str] = Query(None),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.visitas"))
):
    """Visitas del día actual con estado E/S."""
    await _ensure_table(db)
    if not fecha:
        fecha = datetime.now().strftime("%Y-%m-%d")

    rows = await db.fetch_all(
        """SELECT rut, nombre, empresa, motivo, area_destino, persona_contacto,
                  tipo_documento, tipo_marca, hora, patente_vehiculo, parse_ok
           FROM visitas_registros
           WHERE fecha = ?
           ORDER BY hora DESC""",
        (fecha,)
    )

    # Agrupar por RUT para estado actual
    visitantes = {}
    for r in rows:
        row = dict(r)
        rut = row['rut']
        if rut not in visitantes:
            visitantes[rut] = {
                'rut': rut,
                'nombre': row['nombre'],
                'empresa': row['empresa'],
                'motivo': row['motivo'],
                'area_destino': row['area_destino'],
                'persona_contacto': row['persona_contacto'],
                'tipo_documento': row['tipo_documento'],
                'patente': row.get('patente_vehiculo', ''),
                'parse_ok': row['parse_ok'],
                'marcas': [],
                'estado': 'en_planta'  # default
            }
        visitantes[rut]['marcas'].append({
            'hora': row['hora'],
            'tipo': row['tipo_marca']
        })

    # Calcular estado por visitante
    for rut, v in visitantes.items():
        # Ordenar marcas cronológicamente
        v['marcas'].sort(key=lambda m: m['hora'])
        ultima = v['marcas'][-1]
        v['estado'] = 'en_planta' if ultima['tipo'] == 'E' else 'fuera'
        v['primera_entrada'] = v['marcas'][0]['hora'] if v['marcas'] else None
        v['ultima_marca'] = ultima['hora']
        v['total_marcas'] = len(v['marcas'])

    lista = sorted(visitantes.values(), key=lambda v: v.get('ultima_marca', ''), reverse=True)

    en_planta = sum(1 for v in lista if v['estado'] == 'en_planta')

    return {
        "fecha": fecha,
        "stats": {
            "total_visitas": len(lista),
            "en_planta": en_planta,
            "salieron": len(lista) - en_planta
        },
        "visitantes": lista
    }


@router.get("/historial/")
async def get_historial(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: SecurityContext = Depends(get_current_user),
    _perm = Depends(RequirePermission("porteria.visitas"))
):
    """Historial de visitas con filtros."""
    await _ensure_table(db)
    if not hasta:
        hasta = datetime.now().strftime("%Y-%m-%d")
    if not desde:
        desde = (datetime.strptime(hasta, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

    count_row = await db.fetch_one(
        "SELECT COUNT(DISTINCT rut || fecha) as total FROM visitas_registros WHERE fecha BETWEEN ? AND ?",
        (desde, hasta)
    )
    total = count_row['total'] if count_row else 0

    offset = (page - 1) * limit
    rows = await db.fetch_all(
        """SELECT rut, nombre, empresa, area_destino, fecha,
                  MIN(CASE WHEN tipo_marca='E' THEN hora END) as primera_entrada,
                  MAX(CASE WHEN tipo_marca='S' THEN hora END) as ultima_salida,
                  COUNT(*) as total_marcas,
                  tipo_documento
           FROM visitas_registros
           WHERE fecha BETWEEN ? AND ?
           GROUP BY rut, fecha
           ORDER BY fecha DESC, primera_entrada DESC
           LIMIT ? OFFSET ?""",
        (desde, hasta, limit, offset)
    )

    return {
        "desde": desde,
        "hasta": hasta,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "registros": [dict(r) for r in rows]
    }

"""Deshacer un registro de Portería recién hecho (aviso «Listo» con Deshacer, diseño A aprobado por el dueño el 03-11-2026).

El registro no se borra sin rastro: pasa completo a `registros_anulados` (con quién lo anuló y cuándo) y queda en el
registro de cambios. Al salir de su tabla, ninguna pantalla, informe ni cálculo lo vuelve a contar. Solo se puede deshacer:
- dentro del plazo del ajuste `porteria_deshacer_segundos` (Configuración › Sistema › Portería; 0 = sin Deshacer);
- quien hizo el registro (o un administrador);
- si después no se registró otro movimiento del mismo sujeto (la persona, la llave, la visita del día o el vehículo).
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Qué se puede deshacer: tabla, permiso de la acción, campos que identifican al sujeto, campo del tipo y cómo se nombra
REGISTROS: Dict[str, Dict[str, Any]] = {
    "art22": {"tabla": "articulo22_registros", "permiso": "porteria.art22", "sujeto": ("empleado_id",), "tipo": "tipo",
              "nombre": ("SELECT apellido_paterno, apellido_materno, nombre FROM empleados WHERE id = ?", "empleado_id")},
    "llave": {"tabla": "llaves_registros", "permiso": "porteria.llaves", "sujeto": ("llave_id",), "tipo": "tipo",
              "nombre": ("SELECT nombre FROM llaves_maestro WHERE id = ?", "llave_id")},
    "visita": {"tabla": "visitas_registros", "permiso": "porteria.visitas", "sujeto": ("rut", "fecha"), "tipo": "tipo_marca",
               "nombre": None},
    "flota": {"tabla": "flota_registros", "permiso": "porteria.flota", "sujeto": ("flota_id",), "tipo": "tipo",
              "nombre": ("SELECT patente AS nombre FROM flota_aguacol WHERE id = ?", "flota_id")},
}
AJUSTE_SEGUNDOS = "porteria_deshacer_segundos"
# Tiempo que tarda el pedido en llegar desde el aviso hasta el servidor (red y túnel): no es una regla del negocio,
# evita rechazar un Deshacer apretado en el último instante de la barra.
MARGEN_RED_SEGUNDOS = 3


async def asegurar_tabla(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS registros_anulados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tabla TEXT NOT NULL,
            registro_id INTEGER NOT NULL,
            datos TEXT NOT NULL,
            anulado_por_id INTEGER,
            anulado_por_nombre TEXT,
            anulado_en TEXT DEFAULT (datetime('now'))
        )
    """)


async def segundos_para_deshacer(db) -> int:
    """Plazo del ajuste; sin ajuste o con un valor que no se entiende, no hay Deshacer (0)."""
    try:
        fila = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (AJUSTE_SEGUNDOS,))
        return max(0, int(float(fila["valor"]))) if fila else 0
    except Exception:
        return 0


def permiso_deshacer(tipo: str, registro_id: Optional[int], segundos: int) -> Optional[Dict[str, Any]]:
    """Lo que la respuesta de un registro le dice al aviso para ofrecer Deshacer (None si no corresponde)."""
    if not registro_id or segundos <= 0:
        return None
    return {"tipo": tipo, "id": int(registro_id), "segundos": segundos}


def palabra(tipo: Any) -> str:
    t = str(tipo or "").upper()
    return {"E": "ENTRADA", "S": "SALIDA", "DEVOLUCION": "DEVOLUCIÓN"}.get(t, t)


def _leer_utc(valor: Any) -> Optional[datetime]:
    """created_at se guarda en UTC (texto «aaaa-mm-dd hh:mm:ss» o fecha y hora del motor)."""
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).replace(tzinfo=None) if valor.tzinfo else valor
    try:
        return datetime.fromisoformat(str(valor)[:19].replace("T", " "))
    except (TypeError, ValueError):
        return None


def motivo_no_se_puede(reg: Optional[Dict[str, Any]], ultimo_id: Any, usuario_id: Any, es_admin: bool,
                       ahora_utc: datetime, segundos: int) -> Optional[str]:
    """None si se puede deshacer; si no, el motivo en palabras para el aviso."""
    if segundos <= 0:
        return "Deshacer está apagado en Configuración."
    if not reg:
        return "Ese registro ya no existe: quizás ya se deshizo."
    if not es_admin and str(reg.get("registrado_por_id")) != str(usuario_id):
        return "Solo quien hizo el registro puede deshacerlo."
    if ultimo_id is not None and str(ultimo_id) != str(reg.get("id")):
        return "Después se registró otro movimiento: este ya no se puede deshacer."
    creado = _leer_utc(reg.get("created_at"))
    if creado is None or (ahora_utc - creado).total_seconds() > segundos + MARGEN_RED_SEGUNDOS:
        return "Ya pasó el plazo para deshacer. Si hay un error, corríjalo con un nuevo registro."
    return None


async def _nombre_sujeto(db, cfg: Dict[str, Any], reg: Dict[str, Any]) -> str:
    if cfg["nombre"] is None:
        return str(reg.get("nombre") or reg.get("rut") or "")
    sql, campo = cfg["nombre"]
    try:
        f = await db.fetch_one(sql, (reg.get(campo),))
    except Exception:
        f = None
    if not f:
        return ""
    return " ".join(str(f.get(k) or "").strip() for k in ("apellido_paterno", "apellido_materno", "nombre") if f.get(k)).upper()


async def deshacer(db, tipo: str, registro_id: int, usuario, segundos: int,
                   ahora_utc: Optional[datetime] = None) -> Dict[str, Any]:
    cfg = REGISTROS[tipo]
    tabla = cfg["tabla"]
    reg = await db.fetch_one(f"SELECT * FROM {tabla} WHERE id = ?", (registro_id,))
    ultimo = None
    if reg:
        cond = " AND ".join(f"{c} = ?" for c in cfg["sujeto"])
        fila = await db.fetch_one(f"SELECT max(id) AS ultimo FROM {tabla} WHERE {cond}", tuple(reg.get(c) for c in cfg["sujeto"]))
        ultimo = fila.get("ultimo") if fila else None
    ahora = ahora_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    motivo = motivo_no_se_puede(reg, ultimo, usuario.user_id, bool(getattr(usuario, "is_superuser", False)), ahora, segundos)
    if motivo:
        return {"ok": False, "motivo": motivo}

    que = palabra(reg.get(cfg["tipo"]))
    hora = str(reg.get("hora") or "")[:5]
    quien = await _nombre_sujeto(db, cfg, reg)
    detalle = (f"Deshecho desde el aviso de Portería: {que} de las {hora}" + (f" · {quien}" if quien else "")
               + f" (registro {registro_id} de {tabla}). El registro completo quedó en registros_anulados.")
    await asegurar_tabla(db)
    async with db.transaction():
        await db.execute(
            "INSERT INTO registros_anulados (tabla, registro_id, datos, anulado_por_id, anulado_por_nombre) VALUES (?, ?, ?, ?, ?)",
            (tabla, registro_id, json.dumps(reg, default=str, ensure_ascii=False), usuario.user_id, usuario.username))
        await db.execute(f"DELETE FROM {tabla} WHERE id = ?", (registro_id,))
        await db.execute(
            "INSERT INTO logs_auditoria (usuario_id, username, accion, modulo, detalle) VALUES (?, ?, ?, ?, ?)",
            (usuario.user_id, usuario.username, "DESHACER_REGISTRO_PORTERIA", "Portería", detalle))
    return {"ok": True, "mensaje": f"{que} de las {hora} anulada.", "tipo": tipo, "id": registro_id}

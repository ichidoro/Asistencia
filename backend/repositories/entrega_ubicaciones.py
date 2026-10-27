from typing import Any, Dict, List

from loguru import logger

from backend.core.database import Database
from backend.services.gps_nexacol import consolidar_ubicacion


class EntregaUbicacionesRepository:
    """Dónde paró el camión cuando entregó a cada cliente y dirección. Cuando dos días distintos coinciden a menos de 120 m, esa es la ubicación del cliente:
    la próxima vez la entrega se mide en metros contra las paradas (en vez de comparar nombres de calle)."""

    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self) -> None:
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS entrega_ubicaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT NOT NULL,
                fecha TEXT NOT NULL,
                cliente TEXT,
                calle TEXT,
                comuna TEXT,
                patente TEXT,
                la REAL NOT NULL,
                lo REAL NOT NULL,
                duracion_min INTEGER,
                UNIQUE (clave, fecha)
            )
        """)
        await self.db.execute("CREATE INDEX IF NOT EXISTS idx_entrega_ubicaciones_clave ON entrega_ubicaciones (clave)")

    async def guardar(self, observaciones: List[Dict[str, Any]]) -> None:
        for o in observaciones:
            await self.db.execute(
                "INSERT INTO entrega_ubicaciones (clave, fecha, cliente, calle, comuna, patente, la, lo, duracion_min) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (clave, fecha) DO UPDATE SET la = excluded.la, lo = excluded.lo, duracion_min = excluded.duracion_min",
                (o["clave"], o["fecha"], o.get("cliente"), o.get("calle"), o.get("comuna"), o.get("patente"), o["la"], o["lo"], o.get("min")),
            )

    async def aprendidas(self, claves: List[str]) -> Dict[str, Dict[str, Any]]:
        """clave -> {"la", "lo", "n"} para las que ya tienen una ubicación confirmada por 2 o más días."""
        claves = sorted({c for c in claves if c})
        if not claves:
            return {}
        filas = await self.db.fetch_all(
            f"SELECT clave, fecha, la, lo FROM entrega_ubicaciones WHERE clave IN ({', '.join('?' for _ in claves)})", tuple(claves))
        por_clave: Dict[str, List[Dict[str, Any]]] = {}
        for f in filas:
            por_clave.setdefault(f["clave"], []).append({"fecha": f["fecha"], "la": float(f["la"]), "lo": float(f["lo"])})
        out: Dict[str, Dict[str, Any]] = {}
        for clave, obs in por_clave.items():
            u = consolidar_ubicacion(obs)
            if u:
                out[clave] = u
        if out:
            logger.debug(f"📍 ubicaciones aprendidas usadas: {len(out)} de {len(claves)} direcciones")
        return out

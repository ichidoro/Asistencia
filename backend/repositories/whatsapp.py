from typing import Any, Dict, List

from backend.core.database import Database


class WhatsappRepository:
    """Qué avisos automáticos están encendidos y a qué chats (grupos o celulares) va cada uno."""

    def __init__(self, db: Database):
        self.db = db

    async def init_tables(self) -> None:
        # Se mira el catálogo primero: repetir CREATE TABLE IF NOT EXISTS en cada petición pide bloqueos sin necesidad.
        if not await self.db.table_exists("whatsapp_avisos"):
            await self.db.execute("CREATE TABLE IF NOT EXISTS whatsapp_avisos (aviso TEXT PRIMARY KEY, activo INTEGER NOT NULL DEFAULT 0)")
        if not await self.db.table_exists("whatsapp_destinos"):
            await self.db.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_destinos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aviso TEXT NOT NULL,
                    destino TEXT NOT NULL,
                    etiqueta TEXT,
                    UNIQUE (aviso, destino)
                )
            """)

        if not await self.db.table_exists("whatsapp_filtros"):
            await self.db.execute("CREATE TABLE IF NOT EXISTS whatsapp_filtros (aviso TEXT NOT NULL, tipo TEXT NOT NULL, valor TEXT NOT NULL, PRIMARY KEY (aviso, tipo, valor))")
        if not await self.db.table_exists("whatsapp_persona_destino"):
            await self.db.execute("CREATE TABLE IF NOT EXISTS whatsapp_persona_destino (emp_id INTEGER PRIMARY KEY, destino TEXT NOT NULL, etiqueta TEXT)")

    async def filtros(self, aviso: str = "") -> Dict[str, Dict[str, List[str]]]:
        """Áreas y cargos a los que se limita cada aviso (lista vacía = todos). {aviso: {areas: [...], cargos: [...]}}"""
        filas = await self.db.fetch_all("SELECT aviso, tipo, valor FROM whatsapp_filtros" + (" WHERE aviso = ?" if aviso else "") + " ORDER BY valor", (aviso,) if aviso else None)
        out: Dict[str, Dict[str, List[str]]] = {}
        for r in filas:
            out.setdefault(r["aviso"], {"areas": [], "cargos": []})["areas" if r["tipo"] == "area" else "cargos"].append(r["valor"])
        return out

    async def fijar_filtros(self, aviso: str, areas: List[str], cargos: List[str]) -> None:
        await self.db.execute("DELETE FROM whatsapp_filtros WHERE aviso = ?", (aviso,))
        for tipo, valores in (("area", areas), ("cargo", cargos)):
            for v in dict.fromkeys(x.strip() for x in valores if x and x.strip()):
                await self.db.execute("INSERT INTO whatsapp_filtros (aviso, tipo, valor) VALUES (?, ?, ?)", (aviso, tipo, v))

    async def opciones_filtro(self) -> Dict[str, List[str]]:
        """Áreas y cargos que existen entre las personas activas, para ofrecerlos como filtro."""
        filas = await self.db.fetch_all("SELECT a.nombre AS area, e.cargo AS cargo, COUNT(*) AS n FROM empleados e LEFT JOIN areas a ON a.id = e.area_id WHERE e.activo = 1 GROUP BY a.nombre, e.cargo")
        # `pares` (personas por área y cargo) deja que la pantalla encadene los dos filtros sin volver al servidor.
        pares = [{"area": str(r["area"] or "").strip(), "cargo": str(r["cargo"] or "").strip(), "n": int(r["n"])} for r in filas]
        areas = sorted({p["area"] for p in pares if p["area"]}, key=str.lower)
        cargos = sorted({p["cargo"] for p in pares if p["cargo"]}, key=str.lower)
        return {"areas": areas, "cargos": cargos, "pares": pares}

    async def destinos_personas(self) -> Dict[int, Dict[str, Any]]:
        """Contacto o número elegido a mano para cada persona (manda sobre la búsqueda por nombre)."""
        return {int(r["emp_id"]): r for r in await self.db.fetch_all("SELECT emp_id, destino, etiqueta FROM whatsapp_persona_destino")}

    async def fijar_persona(self, emp_id: int, destino: str, etiqueta: str) -> None:
        await self.db.execute(
            "INSERT INTO whatsapp_persona_destino (emp_id, destino, etiqueta) VALUES (?, ?, ?) ON CONFLICT (emp_id) DO UPDATE SET destino = excluded.destino, etiqueta = excluded.etiqueta",
            (emp_id, destino, etiqueta),
        )

    async def quitar_persona(self, emp_id: int) -> None:
        await self.db.execute("DELETE FROM whatsapp_persona_destino WHERE emp_id = ?", (emp_id,))

    async def avisos_activos(self) -> Dict[str, bool]:
        return {r["aviso"]: bool(r["activo"]) for r in await self.db.fetch_all("SELECT aviso, activo FROM whatsapp_avisos")}

    async def poner_activo(self, aviso: str, activo: bool) -> None:
        await self.db.execute(
            "INSERT INTO whatsapp_avisos (aviso, activo) VALUES (?, ?) ON CONFLICT (aviso) DO UPDATE SET activo = excluded.activo",
            (aviso, 1 if activo else 0),
        )

    async def destinos(self, aviso: str = "") -> List[Dict[str, Any]]:
        if aviso:
            return await self.db.fetch_all("SELECT id, aviso, destino, etiqueta FROM whatsapp_destinos WHERE aviso = ? ORDER BY id", (aviso,))
        return await self.db.fetch_all("SELECT id, aviso, destino, etiqueta FROM whatsapp_destinos ORDER BY aviso, id")

    async def agregar_destino(self, aviso: str, destino: str, etiqueta: str) -> None:
        await self.db.execute(
            "INSERT INTO whatsapp_destinos (aviso, destino, etiqueta) VALUES (?, ?, ?) ON CONFLICT (aviso, destino) DO UPDATE SET etiqueta = excluded.etiqueta",
            (aviso, destino, etiqueta),
        )

    async def quitar_destino(self, destino_id: int) -> None:
        await self.db.execute("DELETE FROM whatsapp_destinos WHERE id = ?", (destino_id,))

    async def empleados_activos(self) -> List[Dict[str, Any]]:
        """Personas activas de Asistencia, para asignarles un aviso a chats."""
        return await self.db.fetch_all("SELECT e.id, e.nombre, e.apellido_paterno, e.apellido_materno, e.cargo, a.nombre AS area FROM empleados e LEFT JOIN areas a ON a.id = e.area_id WHERE e.activo = 1 ORDER BY e.nombre, e.apellido_paterno")

    async def empleado(self, emp_id: int) -> Dict[str, Any] | None:
        return await self.db.fetch_one("SELECT nombre, apellido_paterno, apellido_materno FROM empleados WHERE id = ?", (emp_id,))

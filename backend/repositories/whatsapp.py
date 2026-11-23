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

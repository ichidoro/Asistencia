"""
Carga en memoria las Reglas de marcaciones ENCENDIDAS para el motor de cálculo.

El motor (quantum_matrix_engine) es síncrono y no consulta la base: lee los
globales REGLAS_MARCAS_ACTIVAS y REGLAS_MARCAS_REBOTE de su propio módulo.
Esta función los refresca al arrancar y después de cada cambio en la pestaña
(guardar una regla, guardar el rebote, correr o apagar una regla).

Si la carga falla, se conserva lo que ya estaba en memoria y se deja aviso:
nunca se apagan reglas por un error de lectura.
"""
from loguru import logger

from backend.services import quantum_matrix_engine as qme
from backend.repositories.reglas_marcas import CLAVE_REBOTE


async def cargar(db) -> int:
    """Refresca las reglas encendidas y el rebote. Devuelve cuántas reglas quedaron activas, o -1 si falló."""
    try:
        rows = await db.fetch_all(
            "SELECT secuencia, lectura, colacion, accion, COALESCE(avisa_fuera_de_ciclo, 0) AS avisa_fuera_de_ciclo "
            "FROM reglas_marcas WHERE tipo_horario = ? AND activa = 1",
            ('CICLO_INTELIGENTE',)
        )
        activas = {str(r['secuencia']): dict(r) for r in rows}
        rebote = None
        try:
            r = await db.fetch_one("SELECT valor FROM ajustes WHERE clave = ?", (CLAVE_REBOTE,))
            if r and r.get('valor') is not None:
                rebote = float(r['valor'])
        except Exception as e_r:
            logger.warning(f"Reglas de marcaciones: no se pudo leer el rebote ({e_r}); se mantiene el actual.")
            rebote = qme.REGLAS_MARCAS_REBOTE
        qme.REGLAS_MARCAS_ACTIVAS = activas
        qme.REGLAS_MARCAS_REBOTE = rebote
        logger.info(f"⚙️ Reglas de marcaciones en memoria: {len(activas)} encendidas"
                    f"{' (' + ', '.join(sorted(activas)) + ')' if activas else ''}; rebote {rebote or 180:.0f} s.")
        return len(activas)
    except Exception as e:
        logger.error(f"Reglas de marcaciones: falló la carga ({e}); el motor conserva las que ya tenía.")
        return -1

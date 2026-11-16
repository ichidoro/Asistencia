"""Red de seguridad con la copia de práctica encendida (auditoría del 15-11-2026, etapa 3).

1. Araña de consultas: llama cada endpoint GET como administrador; ninguno puede caerse (500) ni quedarse sin responder.
2. Araña de SQL: cada consulta escrita como texto fijo en el servidor se le pasa a la base de práctica para que la
   PREPARE (no la ejecuta): ninguna puede nombrar tablas o columnas que no existen.

Se salta sola si no está definida PANTALLAS_URL, igual que test_pantallas.py, y se corre junto a ella antes de subir
(ver cómo en test_pantallas.py). Solo lee: la araña de SQL abre la base en modo solo lectura y nunca toca una base que
no sea de este PC.
"""
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts"))
URL = os.environ.get("PANTALLAS_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not URL, reason="Defina PANTALLAS_URL (y PANTALLAS_CLAVE) con la copia de práctica encendida")

LOCALES = {"127.0.0.1", "localhost", "::1"}


def test_ninguna_consulta_se_cae():
    import arana_consultas as arana
    import test_pantallas as tp
    assert urlparse(URL).hostname in LOCALES, "la araña solo se corre contra la copia de práctica de este PC"
    resultados = arana.recorrer(URL, tp._sesion()["access_token"])
    assert len(resultados) > 100, f"la araña encontró muy pocos endpoints ({len(resultados)}): revisar efecto_domino"
    fallas = [f"{r['estado']} {r['ruta']} ({r['archivo']}:{r['funcion']}) {r['detalle'][:120]}"
              for r in resultados if arana.es_falla(r)]
    assert fallas == [], "consultas que se caen:\n" + "\n".join(fallas)


def test_ninguna_consulta_nombra_tablas_o_columnas_que_no_existen():
    import revisar_sql
    url = revisar_sql.url_local()
    if not url or urlparse(url).hostname not in LOCALES:
        pytest.skip("la araña de SQL solo se corre contra una base de este PC")
    todas, revisables, fallas = asyncio.run(revisar_sql.revisar(url))
    assert len(revisables) > 300, f"muy pocas consultas revisables ({len(revisables)}): revisar el lector"
    assert fallas == [], "consultas que la base rechaza:\n" + "\n".join(f"{a}:{l} {t} | {m}" for a, l, t, m in fallas)

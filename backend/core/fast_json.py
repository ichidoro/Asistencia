"""
Serializacion JSON rapida para respuestas grandes.

FastAPI pasa cada valor devuelto por `jsonable_encoder` (recursivo, en Python puro): para la matriz de
marcaciones (~125.000 valores) eso costaba ~330 ms de ~470 ms. Devolviendo la respuesta ya serializada
con orjson (Rust) se salta ese paso. Usar solo en endpoints con payload grande.
"""
import decimal
import enum

import orjson
from fastapi import Response


def _default(o):
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    if isinstance(o, enum.Enum):
        return o.value
    if hasattr(o, "model_dump"):      # pydantic v2
        return o.model_dump()
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    return str(o)


def fast_json(data, status_code: int = 200) -> Response:
    return Response(
        content=orjson.dumps(data, default=_default,
                             option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY),
        status_code=status_code,
        media_type="application/json",
    )

"""StaticFiles con caché, minificado en caliente y paquetes de CSS (ver static_minify)."""
from pathlib import Path

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles


class CachedStaticFiles(StaticFiles):
    """StaticFiles con Cache-Control: las URLs versionadas (?v=<startup_id>, que cambia en cada
    deploy) se cachean un año; fuentes/imagenes 7 dias; el resto se revalida por ETag (304)."""
    _LONG = (".woff2", ".woff", ".ttf", ".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp", ".mp3")
    # Librerías de terceros que no llevan ?v= (cambian solo al actualizar la librería, y ahí se cambia el archivo):
    # 30 días en vez de revalidar contra el servidor en cada visita.
    _VENDOR_SUFIJOS = (".min.js", ".min.css")
    _VENDOR_NOMBRES = ("chart.js", "bootstrap-icons.css", "all.min.css")

    # Paquetes de CSS propios (un solo pedido en vez de varios). Se arman en caliente, en este orden.
    _BUNDLES = {
        "css/bundle-base.css": ["css/styles.css", "css/responsive.css"],
        "css/bundle-tema.css": [
            "css/fuentes.css", "css/aguacol-theme.css", "css/mobile-ui.css", "css/pages-refresh.css",
            "css/modales-modernos.css", "css/sidebar-riel.css", "css/tooltip-celda.css",
            "css/estados-grilla.css", "css/grilla-capas.css", "css/estados-circulo.css",
        ],
    }

    def _respuesta_minificada(self, datos, ruta, request_headers):
        import hashlib
        etag = '"' + hashlib.md5(datos).hexdigest() + '"'
        tipo = "text/css; charset=utf-8" if ruta.endswith(".css") else "text/javascript; charset=utf-8"
        if request_headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(datos, media_type=tipo, headers={"ETag": etag})

    async def get_response(self, path, scope):
        from starlette.requests import Request as _Req
        from backend.services import static_minify as _sm
        resp = None
        try:
            rel = path.replace("\\", "/")
            hdrs = _Req(scope).headers
            if rel in self._BUNDLES:
                datos = _sm.bundle_css(Path(self.directory), self._BUNDLES[rel])
                if datos is not None:
                    resp = self._respuesta_minificada(datos, rel, hdrs)
            elif _sm.HABILITADO and _sm._es_minificable(rel):
                datos = _sm.contenido_minificado(Path(self.directory) / rel, rel)
                if datos is not None:
                    resp = self._respuesta_minificada(datos, rel, hdrs)
        except Exception:
            resp = None
        if resp is None:
            resp = await super().get_response(path, scope)
        if resp.status_code in (200, 304):
            if b"v=" in scope.get("query_string", b""):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path.lower().endswith((".woff2", ".woff")):
                # Fuentes: el nombre incluye el peso/versión; 30 días sin revalidar
                resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
            elif path.lower().endswith(self._LONG):
                resp.headers["Cache-Control"] = "public, max-age=604800"
            elif path.lower().endswith(self._VENDOR_SUFIJOS) or path.rsplit("/", 1)[-1].lower() in self._VENDOR_NOMBRES or path.lower().startswith("js/libs/"):
                resp.headers["Cache-Control"] = "public, max-age=2592000"
            else:
                resp.headers["Cache-Control"] = "no-cache"
        return resp

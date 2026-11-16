"""Toda ruta de la aplicación pide iniciar sesión, salvo las públicas de esta lista, cada una con su motivo
(auditoría, 16-11-2026: el historial de sincronizaciones respondía sin sesión). Una ruta nueva sin sesión hace
fallar esta prueba: o se le agrega el permiso o se anota aquí por qué es pública."""
from fastapi.routing import APIRoute

from backend.main import app

PUBLICAS = {
    # Páginas y archivos que el navegador pide antes de ingresar
    "GET /": "página de inicio (redirige al ingreso)",
    "GET /index.html": "la aplicación; los datos los pide después con sesión",
    "GET /login": "pantalla de ingreso",
    "GET /login.html": "pantalla de ingreso",
    "GET /manifest.json": "datos de la app instalable",
    "GET /sw.js": "service worker",
    "GET /favicon.ico": "ícono",
    "GET /cancion.mp3": "sonido de la pantalla de ingreso",
    "GET /huevo.jpg": "imagen de la pantalla de ingreso",
    "GET /huevo_{n}.jpg": "imagen de la pantalla de ingreso",
    "GET /.well-known/appspecific/com.chrome.devtools.json": "consulta automática de Chrome",
    "GET /manual-180h": "manual impreso para choferes",
    "GET /manual-choferes": "manual impreso para choferes",
    # Ingreso y estado
    "POST /api/auth/login/": "el ingreso mismo",
    "GET /ping": "prueba de vida del servidor",
    "GET /health": "prueba de vida del servidor (Docker)",
    "GET /api/version": "versión publicada",
    "GET /config": "configuración pública, sin datos sensibles",
    "GET /api/startup/status": "estado de arranque que mira la pantalla de ingreso",
    "GET /api/sync/health/": "estado de la base y de las marcaciones (sin datos de personas)",
    # Con su propia protección
    "POST /api/sync/cron/": "lo llama el cron del servidor con una clave secreta",
    "GET /api/porteria/fotos/{nombre}": "nombre aleatorio no adivinable, como un enlace de Drive",
}
DEPENDENCIAS_DE_SESION = {"get_current_user", "RequirePermission", "RequireAnyPermission"}


def _dependencias(dependant, out):
    for d in dependant.dependencies:
        out.add(getattr(d.call, "__name__", ""))
        out.add(type(d.call).__name__)
        _dependencias(d, out)
    return out


def rutas_sin_sesion():
    sin = set()
    for r in app.routes:
        if isinstance(r, APIRoute) and not (_dependencias(r.dependant, set()) & DEPENDENCIAS_DE_SESION):
            sin.update(f"{m} {r.path}" for m in r.methods)
    return sin


def test_el_historial_y_la_prueba_de_conexion_piden_sesion():
    abiertas = rutas_sin_sesion()
    assert "GET /api/sync/logs/" not in abiertas
    assert "GET /api/sync/test/" not in abiertas


def test_no_hay_rutas_nuevas_sin_sesion():
    nuevas = sorted(rutas_sin_sesion() - set(PUBLICAS))
    assert nuevas == [], "rutas que responden sin iniciar sesión (agregar el permiso o anotarlas en PUBLICAS):\n" + "\n".join(nuevas)


def test_la_lista_de_publicas_no_tiene_rutas_que_ya_no_existen():
    existentes = {f"{m} {r.path}" for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    sobran = sorted(set(PUBLICAS) - existentes)
    assert sobran == [], f"rutas en PUBLICAS que ya no existen: {sobran}"

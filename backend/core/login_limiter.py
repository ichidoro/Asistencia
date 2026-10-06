"""Límite de intentos de inicio de sesión (en memoria).

Reglas:
  - Cuenta solo los intentos FALLIDOS (usuario inexistente o contraseña incorrecta). Un ingreso correcto no suma y
    borra el contador de ese usuario en esa IP.
  - Bloquea por (IP real, usuario): 5 fallos en 5 minutos. Así un usuario que se equivoca no deja fuera a los demás.
  - Además un tope por IP (30 fallos en 5 minutos, cualquier usuario) para frenar a quien prueba muchos usuarios.
  - IP real: la app corre detrás de un túnel de Cloudflare, así que el servidor ve siempre la IP privada del túnel.
    Solo si el origen directo es una IP privada o local se usa CF-Connecting-IP / X-Forwarded-For; desde una IP
    pública esas cabeceras se ignoran (se podrían falsificar para evitar el bloqueo).
El estado vive en el proceso: reiniciar el contenedor lo limpia.
"""
import ipaddress
import math
import time

MAX_FALLOS_USUARIO = 5
MAX_FALLOS_IP = 30
VENTANA_SEG = 300

_fallos_usuario: dict = {}   # {(ip, usuario): [timestamps]}
_fallos_ip: dict = {}        # {ip: [timestamps]}


class LoginBloqueado(Exception):
    def __init__(self, segundos: int):
        super().__init__(f"Bloqueado {segundos}s")
        self.segundos = max(1, int(segundos))

    @property
    def minutos(self) -> int:
        return max(1, math.ceil(self.segundos / 60))


def _ahora() -> float:
    return time.time()


def _es_ip(texto: str) -> bool:
    try:
        ipaddress.ip_address(texto)
        return True
    except ValueError:
        return False


def ip_cliente(request) -> str:
    """IP real del cliente (ver nota del módulo)."""
    peer = request.client.host if getattr(request, "client", None) else "unknown"
    try:
        dir_peer = ipaddress.ip_address(peer)
        viene_de_proxy = dir_peer.is_private or dir_peer.is_loopback or dir_peer.is_link_local
    except ValueError:
        viene_de_proxy = False
    if viene_de_proxy:
        for cabecera in ("cf-connecting-ip", "x-forwarded-for"):
            valor = request.headers.get(cabecera)
            if valor:
                candidato = valor.split(",")[0].strip()
                if _es_ip(candidato):
                    return candidato
    return peer


def _clave_usuario(usuario: str) -> str:
    return (usuario or "").strip().lower()[:100]


def _podar(lista: list, ahora: float) -> list:
    corte = ahora - VENTANA_SEG
    return [t for t in lista if t > corte]


def _segundos_restantes(lista: list, ahora: float, maximo: int) -> int:
    # El bloqueo termina cuando el fallo más antiguo que cuenta sale de la ventana.
    relevantes = sorted(lista)[-maximo:]
    return int(math.ceil(relevantes[0] + VENTANA_SEG - ahora))


def verificar(ip: str, usuario: str) -> None:
    """Lanza LoginBloqueado si esa IP/usuario ya superó el máximo de fallos."""
    ahora = _ahora()
    k = (ip, _clave_usuario(usuario))
    if k in _fallos_usuario:
        _fallos_usuario[k] = _podar(_fallos_usuario[k], ahora)
        if not _fallos_usuario[k]:
            del _fallos_usuario[k]
    if ip in _fallos_ip:
        _fallos_ip[ip] = _podar(_fallos_ip[ip], ahora)
        if not _fallos_ip[ip]:
            del _fallos_ip[ip]
    f_usuario = _fallos_usuario.get(k, [])
    if len(f_usuario) >= MAX_FALLOS_USUARIO:
        raise LoginBloqueado(_segundos_restantes(f_usuario, ahora, MAX_FALLOS_USUARIO))
    f_ip = _fallos_ip.get(ip, [])
    if len(f_ip) >= MAX_FALLOS_IP:
        raise LoginBloqueado(_segundos_restantes(f_ip, ahora, MAX_FALLOS_IP))


def registrar_fallo(ip: str, usuario: str) -> None:
    ahora = _ahora()
    _fallos_usuario.setdefault((ip, _clave_usuario(usuario)), []).append(ahora)
    _fallos_ip.setdefault(ip, []).append(ahora)
    # Evita que el diccionario crezca sin límite si alguien prueba miles de usuarios distintos.
    if len(_fallos_usuario) > 5000:
        for k in list(_fallos_usuario):
            _fallos_usuario[k] = _podar(_fallos_usuario[k], ahora)
            if not _fallos_usuario[k]:
                del _fallos_usuario[k]


def limpiar(ip: str, usuario: str) -> None:
    """Ingreso correcto: se borra el contador de ese usuario en esa IP."""
    _fallos_usuario.pop((ip, _clave_usuario(usuario)), None)


def reiniciar_todo() -> None:
    _fallos_usuario.clear()
    _fallos_ip.clear()

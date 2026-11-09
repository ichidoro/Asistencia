"""
Plantilla «Banda azul» de los correos de Asistencia (decisión del dueño, 09-11-2026).

Una sola plantilla para todos los correos: encabezado azul de la app con el logo (adjunto como imagen, cid
«logo_aguacol»), título y frase de qué pasó, datos en filas, «Qué hacer» cuando corresponde, botón a la app y pie.
HTML apto para correo: tablas, estilos en línea, 600 px, sin emojis; fechas dd-mm-aaaa y horas HH:MM:SS.
"""
import os
from datetime import date, datetime
from html import escape
from typing import Any, Dict, List, Sequence

from backend.core.config import settings

NAVY, INK, INK2, LINE, LINE2 = '#1b2f8f', '#1a2233', '#4a5468', '#d9deea', '#eef1f7'
GRIS = '#7a8296'
FONT = "Barlow,'Segoe UI',Arial,sans-serif"
TONOS = {  # (color, fondo)
    'navy': (NAVY, '#e9edfb'), 'ok': ('#16673b', '#e5f3ea'), 'rojo': ('#b42318', '#fdecea'),
    'ds': ('#c0267a', '#fce7ef'), 'he': ('#16673b', '#e5f3ea'), 'nu': (INK2, LINE2), 'gris': (INK2, LINE2), 'al': ('#9a4a08', '#fdf0e1'),
}
URL_APP = 'https://asistencia.aguacol.cl'
CID_LOGO = 'logo_aguacol'


def ruta_logo() -> str:
    """El logo de la app (el mismo de la pantalla y del informe PDF)."""
    return os.path.join(str(settings.BASE_DIR), 'frontend', 'assets', 'img', 'logo-aguacol.png')


def imagenes() -> List[dict]:
    p = ruta_logo()
    return [{'cid': CID_LOGO, 'path': p}] if os.path.exists(p) else []


def fecha(v: Any) -> str:
    """dd-mm-aaaa desde ISO (2026-05-04), dd/mm/aaaa o fecha; si no se reconoce, tal cual."""
    if isinstance(v, (date, datetime)):
        return v.strftime('%d-%m-%Y')
    s = str(v or '').strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return f'{s[8:10]}-{s[5:7]}-{s[0:4]}'
    return s.replace('/', '-')


def e(v: Any) -> str:
    return escape(str(v if v is not None else ''))


def filas(rows: Sequence[Any], ancho_k: str = '60%', tam: int = 14) -> str:
    """rows: (texto, valor) | (texto, valor, clase) | (texto, valor, clase, %) o dicts {t, v, c, q}.
    Clase 'tot' = total con raya arriba; 'base' = negrita; 'det' = detalle más chico; tonos de TONOS colorean el valor."""
    out = ''
    for r in rows:
        if isinstance(r, dict):
            k, v, c, q = r.get('t'), r.get('v'), r.get('c', ''), r.get('q', '')
        else:
            k, v = r[0], r[1]
            c = r[2] if len(r) > 2 else ''
            q = r[3] if len(r) > 3 else ''
        t = tam - 1 if c == 'det' else tam
        peso = '700' if c in ('tot', 'base') else '500'
        bt = f'border-top:1px solid {INK};' if c == 'tot' else ''
        color = TONOS[c][0] if c in TONOS else (INK2 if c in ('det', 'menos') else INK)
        sangria = 'padding-left:14px;' if c == 'det' else ''
        out += (f'<tr><td style="{bt}{sangria}padding-top:6px;padding-bottom:6px;border-bottom:1px solid {LINE2};font:400 {t}px/1.4 {FONT};color:{INK2};width:{ancho_k}">{e(k)}</td>'
                f'<td align="right" style="{bt}padding:6px 10px 6px 0;border-bottom:1px solid {LINE2};font:400 {t - 1}px/1.4 {FONT};color:{GRIS};white-space:nowrap">{e(q)}</td>'
                f'<td align="right" style="{bt}padding:6px 0;border-bottom:1px solid {LINE2};font:{peso} {t}px/1.4 {FONT};color:{color};white-space:nowrap">{e(v)}</td></tr>')
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{out}</table>'


def subtitulo(texto: str) -> str:
    return f'<div style="font:600 13px {FONT};color:{INK2};padding:14px 0 2px">{e(texto)}</div>'


def destacados(items: Sequence[Dict[str, str]]) -> str:
    """[{t, v, n, q, c}] → recuadros de color lado a lado (lo que se carga)."""
    celdas = []
    for d in items:
        col, bg = TONOS.get(d.get('c', ''), (INK, LINE2))
        sub = ' · '.join(x for x in (d.get('n'), d.get('q')) if x)
        celdas.append(f'<td valign="top" style="background:{bg};border-radius:10px;padding:12px 14px">'
                      f'<div style="font:600 12px {FONT};color:{col}">{e(d.get("t"))}</div>'
                      f'<div style="font:700 24px/1.15 {FONT};color:{col};padding:2px 0">{e(d.get("v"))}</div>'
                      f'<div style="font:400 12px {FONT};color:{INK2}">{e(sub)}</div></td>')
    return ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
            + '<td style="width:10px"></td>'.join(celdas) + '</tr></table>')


def persona(nombre: str, rut: str = '', detalle: str = '') -> str:
    ini = (nombre or '?').strip()[:1].upper()
    linea = ' · '.join(x for x in (f'RUT {rut}' if rut else '', detalle) if x)
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6fb;border-radius:10px"><tr>'
            f'<td width="44" style="padding:12px 0 12px 14px"><div style="width:40px;height:40px;border-radius:20px;background:{NAVY};color:#fff;'
            f'font:700 17px/40px {FONT};text-align:center">{e(ini)}</div></td>'
            f'<td style="padding:12px 14px"><div style="font:700 15px {FONT};color:{INK}">{e(nombre)}</div>'
            f'<div style="font:400 13px {FONT};color:{INK2}">{e(linea)}</div></td></tr></table>')


def pasos(lista: Sequence[str], tono: str = 'navy', titulo: str = 'Qué hacer') -> str:
    if not lista:
        return ''
    col, bg = TONOS[tono]
    li = ''.join(f'<tr><td valign="top" style="padding:3px 8px 3px 0;font:700 13px {FONT};color:{NAVY}">{i}.</td>'
                 f'<td style="padding:3px 0;font:400 14px/1.45 {FONT};color:{INK}">{e(p)}</td></tr>' for i, p in enumerate(lista, 1))
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px;background:{bg};border-radius:10px">'
            f'<tr><td style="padding:14px 16px"><div style="font:700 14px {FONT};color:{col};padding-bottom:6px">{e(titulo)}</div>'
            f'<table role="presentation" cellspacing="0" cellpadding="0">{li}</table></td></tr></table>')


def lista_nombres(titulo: str, rows: Sequence[Dict[str, str]], tono: str) -> str:
    if not rows:
        return ''
    col = TONOS.get(tono, (INK, ''))[0]
    tr = ''.join(f'<tr><td style="padding:3px 0;font:400 13px {FONT};color:{INK}">{e(r["t"])}</td>'
                 f'<td align="right" style="padding:3px 0;font:600 13px {FONT};color:{col};white-space:nowrap">{e(r["v"])}</td></tr>' for r in rows)
    return subtitulo(f'{titulo} ({len(rows)})') + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{tr}</table>'


def caja(contenido: str) -> str:
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px;border:1px solid {LINE};border-radius:12px">'
            f'<tr><td style="padding:14px 16px">{contenido}</td></tr></table>')


def boton(texto: str, url: str = URL_APP) -> str:
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:20px"><tr><td style="background:{NAVY};border-radius:8px">'
            f'<a href="{e(url)}" style="display:inline-block;padding:11px 20px;font:600 14px {FONT};color:#fff;text-decoration:none">{e(texto)}</a></td></tr></table>')


def correo(etiqueta: str, tono: str, titulo: str, intro: str, cuerpo: str, previa: str = '', pie_extra: str = '') -> str:
    """El correo completo con la plantilla «Banda azul»."""
    col, bg = TONOS.get(tono, TONOS['navy'])
    pie = 'Correo automático de Asistencia Aguacol. No responda a este mensaje.' + (f' {pie_extra}' if pie_extra else '')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{e(titulo)}</title></head>
<body style="margin:0;padding:0;background:#eef0f5">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{e(previa or intro)}</span>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef0f5"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:600px;max-width:100%;background:#ffffff;border-radius:12px">
<tr><td style="background:{NAVY};border-radius:12px 12px 0 0;padding:20px 28px 22px">
 <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
  <td><table role="presentation" cellspacing="0" cellpadding="0"><tr><td style="background:#ffffff;border-radius:8px;padding:6px 10px">
   <img src="cid:{CID_LOGO}" width="104" alt="Aguacol" style="display:block;border:0"></td></tr></table></td>
  <td align="right"><span style="display:inline-block;background:{bg};color:{col};border-radius:999px;padding:4px 12px;font:700 12px {FONT}">{e(etiqueta)}</span></td>
 </tr></table>
 <h1 style="margin:18px 0 6px;font:700 23px/1.25 {FONT};color:#ffffff">{e(titulo)}</h1>
 <p style="margin:0;font:400 15px/1.5 {FONT};color:#d6dcf3">{e(intro)}</p>
</td></tr>
<tr><td style="padding:22px 28px">{cuerpo}</td></tr>
<tr><td style="padding:4px 28px 22px;font:400 12px/1.5 {FONT};color:{GRIS}">{e(pie)}</td></tr>
</table></td></tr></table></body></html>"""


def bloque_resumen(r: Dict[str, Any]) -> str:
    """Un tipo de horario del resumen de cierre (informe_cierre_pdf.resumen_tipo) dentro del correo."""
    c = f'<div style="font:700 16px {FONT};color:{NAVY};padding-bottom:10px">{e(r["titulo"])} · {r["personas"]} personas</div>'
    c += destacados(r['cargar'])
    c += subtitulo('Balance de horas') + filas(r['balance'])
    for g in r.get('de_donde') or []:
        c += subtitulo(g['t']) + filas(g['filas'])
    c += subtitulo('Jornadas (días)') + filas(r['jornadas'])
    for q in r.get('quienes') or []:
        c += lista_nombres(q['t'], q['filas'], q['c'])
    return caja(c)


def adjuntos_html(nombres: Sequence[str]) -> str:
    if not nombres:
        return ''
    tr = ''.join(f'<tr><td style="padding:3px 0;font:500 13px {FONT};color:{INK}">{"PDF" if n.lower().endswith(".pdf") else "Archivo"} · {e(n)}</td></tr>' for n in nombres)
    return subtitulo('Adjuntos') + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{tr}</table>'

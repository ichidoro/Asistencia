"""Botón «Preinforme» de la grilla con dos opciones (pedido de la persona dueña, 21-11-2026): ver el PDF dentro de la
aplicación (un visor, con una pestaña por tipo de horario) o descargarlo como antes."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JS = (RAIZ / "frontend" / "js" / "marcaciones_ui.js").read_text(encoding="utf-8")
RT = (RAIZ / "backend" / "routers" / "cierre.py").read_text(encoding="utf-8")


def test_el_boton_abre_un_menu_con_ver_y_descargar():
    i = JS.index("<i class=\"bi bi-file-earmark-pdf text-danger\"></i> Preinforme")
    menu = JS[i:i + 900]
    assert 'onclick="window.verPreinformeGrilla(this)"' in menu and "Ver en la aplicación" in menu
    assert 'onclick="window.descargarPreinformeGrilla(this)"' in menu and "Descargar PDF" in menu
    assert 'data-bs-toggle="dropdown"' in JS[i - 400:i]


def test_el_visor_muestra_el_pdf_en_la_aplicacion():
    f = JS[JS.index("window.verInformeCierre = async function"):]
    f = f[:f.index("\n};")]
    assert "/api/cierre/informe-pdf/archivo?" in f and "'&ver=true'" in f and "<iframe id=\"vi-pdf\"" in f
    assert "vn-pdf-tabs" in f and "vi-descargar" in f        # una pestaña por tipo y el botón Descargar
    assert "createObjectURL" not in f                       # lo entrega el servidor, sin armar archivos en memoria
    # pantalla completa y el PDF ajustado al ancho, sin miniaturas (21-11-2026: en ventana mediana se veía chico)
    assert 'modal-dialog modal-fullscreen"' in f and "#view=FitH&navpanes=0" in f


def test_el_servidor_lo_entrega_para_verlo_o_para_descargarlo():
    assert 'ver: bool = Query(False' in RT and '"inline" if ver else "attachment"' in RT

import pandas as pd
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import List, Dict, Any
from loguru import logger
from backend.services.asistencia_service import AsistenciaService

class ReportService:
    def __init__(self, asistencia_service: AsistenciaService):
        self.asistencia_service = asistencia_service

    def _format_hhmm(self, minutos) -> str:
        if not minutos or minutos == 0:
            return "00:00"
        signo = "-" if minutos < 0 else ""
        m = abs(minutos)
        h = int(m // 60)
        mn = int(m % 60)
        return f"{signo}{h:02d}:{mn:02d}"

    def _get_saldo(self, extras_aprobados: int, deuda: int) -> str:
        saldo = (extras_aprobados or 0) - (deuda or 0)
        signo = "+" if saldo > 0 else ("-" if saldo < 0 else "")
        return f"{signo}{self._format_hhmm(abs(saldo))}"

    async def generate_excel_report(self, fecha_inicio: str, fecha_fin: str, area: str = None, turno_id: int = None) -> BytesIO:
        """
        Genera un reporte Excel multi-hoja con la Matriz de Asistencia (réplica UI).
        """
        try:
            # Rango de fechas para las columnas
            f_ini = date.fromisoformat(fecha_inicio)
            f_fin = date.fromisoformat(fecha_fin)
            rango_dias = [(f_ini + timedelta(days=i)) for i in range((f_fin - f_ini).days + 1)]
            cols_dias = [d.day for d in rango_dias]
            
            # Pasar Año, Mes y Área/Turno explícitos al AsistenciaService
            matrix_data = await self.asistencia_service.get_matrix_data_with_projections(
                f_ini.month, f_ini.year, area=area, turno_id=turno_id
            )
            empleados = matrix_data.get("empleados", [])
            
            # --- EVALUAR BONOS DESDE EL BACKEND ---
            from backend.services.bono_service import BonoService
            bono_srv = BonoService(self.asistencia_service.repository.db)
            bonos_eval = await bono_srv.evaluar_bonos_directo(
                empleados, 
                matrix_data.get("data", []), 
                matrix_data.get("justificaciones", []), 
                matrix_data.get("matrix", {})
            )
            
            # --- MATRIZ REAL DE DIAS POR EMPLEADO ---
            # La llave primaria es str(empleado_id), y dentro otra llave str "YYYY-MM-DD"
            emp_matrix = matrix_data.get("matrix", {})

            # 2. Construir DataFrames Base para cada Pestaña (Hoja)
            
            # Preparar arreglos para recolectar las filas
            matriz_rows = []
            reales_rows = []
            extras_rows = []
            acumulado_rows = []
            
            # Descubrir dinámicamente qué bonos existen
            todos_bonos = set()
            for emp_bonos in bonos_eval.values():
                todos_bonos.update(emp_bonos.keys())
            lista_bonos = sorted(list(todos_bonos))

            for emp in empleados:
                emp_id = emp['id']
                nom_completo = f"{emp['apellido_paterno']} {emp.get('apellido_materno', '')} {emp['nombre']}".strip().replace('  ', ' ')
                rut = emp.get('rut', '')
                activo_str = "SÍ" if emp.get('activo', 1) else "NO"
                
                # Base del diccionario para este empleado (Información estática)
                base_info = {'Identificador': emp_id, 'RUT': rut, 'Empleado': nom_completo, 'Activo': activo_str}
                
                # Variables sumatorias para la hoja de Conceptos (mensual)
                min_deuda = 0
                min_extra_bruto = 0
                min_extra_aprobado = 0
                min_jornadas_especiales = 0
                
                # En Python, el objeto de fechas viene en matrix[emp_id]
                dias_dict = emp_matrix.get(str(emp_id), {})
                if not dias_dict and emp_id in emp_matrix:
                     dias_dict = emp_matrix[emp_id]
                
                # 1. Pimer recorrido para calcular totales del empleado
                for d in rango_dias:
                    f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                    dia_data = dias_dict.get(f_str)
                    if dia_data:
                        min_deuda += dia_data.get("minutos_deuda", 0)
                        
                        if dia_data.get("estado") in ('JORNADA_ESPECIAL', 'EXTRA'):
                            min_jornadas_especiales += dia_data.get("minutos_extra_bruto", 0)
                        else:
                            min_extra_bruto += dia_data.get("minutos_extra_bruto", 0)
                            
                        if dia_data.get("estado_he") == "APROBADO":
                             min_extra_aprobado += (dia_data.get("minutos_extra_autorizados") or 0)
                
                # 2. Rellenar columnas de totales
                base_info["HE Totales"] = self._format_hhmm(min_extra_bruto)
                base_info["Jornadas Especiales"] = self._format_hhmm(min_jornadas_especiales)
                base_info["Deuda Acum."] = f"-{self._format_hhmm(min_deuda)}" if min_deuda > 0 else "00:00"
                base_info["Saldo a Pagar"] = self._get_saldo(min_extra_aprobado, min_deuda)
                
                # 3. Evaluar Bonos
                bonos_empleado = bonos_eval.get(emp_id) or bonos_eval.get(str(emp_id), {})
                for bx in lista_bonos:
                    info_bx = bonos_empleado.get(bx)
                    if not info_bx or info_bx.get("aplica") is False:
                         base_info[bx] = "-"
                    else:
                         base_info[bx] = "SÍ" if info_bx.get("califica") else "NO"

                # Clonar el diccionario base para cada "Hoja"
                f_matriz = dict(base_info)
                f_reales = dict(base_info)
                f_extras = dict(base_info)
                f_acumulado = dict(base_info)

                # Variables para acumulados (Hoja 4)
                acum_semanal = 0
                acum_bolsa = 0
                es_bolsa = any(dia.get('tipo_programacion') == 'FLEXIBLE_BOLSA' for dia in dias_dict.values()) if dias_dict else False

                # 4. Segundo recorrido para rellenar la matriz de días
                for d in rango_dias:
                    num_dia = d.day
                    f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                    dia_data = dias_dict.get(f_str)
                    
                    if d.weekday() == 0: # Lunes: Reset semanal
                        acum_semanal = 0

                    if not dia_data:
                        f_matriz[num_dia] = ""
                        f_reales[num_dia] = ""
                        f_extras[num_dia] = ""
                        f_acumulado[num_dia] = ""
                        continue
                     
                    # Mapeos de columnas según la hoja
                    
                    # Hoja 1: Matriz (Siglas y estados)
                    estado_bruto = dia_data.get("estado", "")
                    
                    sigla = estado_bruto
                    if estado_bruto == 'OK': sigla = 'OK'
                    elif estado_bruto == 'ATRASO': sigla = 'ATR'
                    elif estado_bruto == 'SALIDA_ADELANTADA': sigla = 'SAD'
                    elif estado_bruto == 'ATR_SAD': sigla = 'ATR-SAD'
                    elif estado_bruto and ('FALTA' in estado_bruto or estado_bruto == 'INASISTENCIA'): sigla = 'INA'
                    elif estado_bruto == 'LIBRE': sigla = 'LIB'
                    elif estado_bruto == 'FERIADO': sigla = 'FES'
                    elif estado_bruto == 'VACACIONES': sigla = 'VAC'
                    elif estado_bruto == 'LICENCIA': sigla = 'LIC'
                    elif estado_bruto == 'LICENCIA COMUN': sigla = 'LCM'
                    elif estado_bruto == 'LICENCIA MUTUAL': sigla = 'LMU'
                    elif estado_bruto == 'CUMPLEAÑOS': sigla = 'CUM'
                    elif estado_bruto == 'DUELO PADRES / HERMANOS': sigla = 'DUE'
                    elif estado_bruto == 'ANOMALIA': sigla = 'ANO'
                    elif estado_bruto == 'EN_CURSO': sigla = 'CUR'
                    elif estado_bruto == 'JORNADA_ESPECIAL': sigla = 'ESP'
                    elif estado_bruto == 'EXTRA': sigla = 'EXTRA'
                    elif estado_bruto == 'NO_ACTIVO': sigla = '---'
                    elif dia_data.get('es_fin_de_semana') and not estado_bruto: sigla = '---'
                    
                    if not sigla:
                        sigla = "---"
                    
                    f_matriz[num_dia] = sigla
                    
                    # Hoja 2: Reales (Cantidad de Horas Trabajadas HH:MM)
                    estados_con_horas = ['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'JORNADA_ESPECIAL', 'EXTRA', 'EN_CURSO']
                    min_trabajados = 0
                    if estado_bruto in estados_con_horas:
                        if estado_bruto == 'EN_CURSO':
                            f_reales[num_dia] = ">>"
                        else:
                            horas_dec = dia_data.get('horas_trabajadas', 0)
                            if horas_dec:
                                min_trabajados = int(round(horas_dec * 60))
                                h_int = min_trabajados // 60
                                m_int = min_trabajados % 60
                                f_reales[num_dia] = f"{h_int:02d}:{m_int:02d}"
                            else:
                                f_reales[num_dia] = "00:00"
                    else:
                        f_reales[num_dia] = ""
                    
                    # Hoja 3: Extras (HE Brutas, Atrasos, Deuda)
                    d_mins = dia_data.get("minutos_deuda", 0)
                    h_mins = dia_data.get("minutos_extra_bruto", 0)
                    texto_extra = ""
                    if h_mins and h_mins > 0: texto_extra += f"+{self._format_hhmm(h_mins)} "
                    if d_mins and d_mins > 0: texto_extra += f"-{self._format_hhmm(d_mins)}"
                    f_extras[num_dia] = texto_extra.strip()

                    # Hoja 4: Acumulado
                    acum_semanal += min_trabajados
                    acum_bolsa += min_trabajados
                    if es_bolsa:
                        f_acumulado[num_dia] = self._format_hhmm(acum_bolsa)
                    else:
                        f_acumulado[num_dia] = self._format_hhmm(acum_semanal)
                
                # Agregar las filas
                matriz_rows.append(f_matriz)
                reales_rows.append(f_reales)
                extras_rows.append(f_extras)
                acumulado_rows.append(f_acumulado)

            # 3. Crear DataFrames
            df_matriz = pd.DataFrame(matriz_rows)
            df_reales = pd.DataFrame(reales_rows)
            df_extras = pd.DataFrame(extras_rows)
            df_acumulado = pd.DataFrame(acumulado_rows)
            
            # Ordenar columnas numéricas (días al final)
            orden_base = ['Identificador', 'RUT', 'Empleado', 'Activo', 'HE Totales', 'Jornadas Especiales', 'Deuda Acum.', 'Saldo a Pagar'] + lista_bonos
            orden_dias = [c for c in df_matriz.columns if isinstance(c, int)]
            orden_completo_grilla = orden_base + sorted(orden_dias)
            
            df_matriz = df_matriz[orden_completo_grilla]
            df_reales = df_reales[orden_completo_grilla]
            df_extras = df_extras[orden_completo_grilla]
            df_acumulado = df_acumulado[orden_completo_grilla]
            
            # ---- MAQUETACIÓN VISUAL EXACTA (ESPEJO DE LA UI) ----
            dias_espanol = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            rename_mapping = {
                'HE Totales': 'HE Totales\n(HH:MM)',
                'Jornadas Especiales': 'Jornadas Especiales\n(HH:MM)',
                'Deuda Acum.': 'Deuda Acum.\n(HH:MM)',
                'Saldo a Pagar': 'Saldo a Pagar\n(Saldo)'
            }
            # Bonos
            for b in lista_bonos:
                rename_mapping[b] = f"{b}\n(Califica)"
            # Días
            for d in rango_dias:
                fecha_str = f"{d.day:02d}-{d.month:02d}-{d.year}"
                dia_semana_str = dias_espanol[d.weekday()]
                rename_mapping[d.day] = f"{fecha_str}\n{dia_semana_str}"
                
            df_matriz = df_matriz.rename(columns=rename_mapping)
            df_reales = df_reales.rename(columns=rename_mapping)
            df_extras = df_extras.rename(columns=rename_mapping)
            df_acumulado = df_acumulado.rename(columns=rename_mapping)

            # 4. Generar Excel Multi-Hoja
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Escribir cada Dataframe en su respectiva pestaña (Empezar en Fila 6, index=5)
                df_matriz.to_excel(writer, index=False, sheet_name='Conceptos', startrow=5)
                df_reales.to_excel(writer, index=False, sheet_name='Horas Reales', startrow=5)
                df_extras.to_excel(writer, index=False, sheet_name='Horas Extras', startrow=5)
                df_acumulado.to_excel(writer, index=False, sheet_name='Acumulado', startrow=5)

                
                # Ajustar formatos visuales (Ancho de columnas centrados y saltos de línea)
                from openpyxl.styles import Alignment, Font, Border, Side
                from openpyxl.drawing.image import Image
                from openpyxl.cell.rich_text import TextBlock, CellRichText
                from openpyxl.cell.text import InlineFont
                
                # Paleta de colores para fuentes
                COLOR_OK = Font(color="00B050", bold=True)       # Verde
                COLOR_ATR = Font(color="FD7E14", bold=True)      # Naranja
                COLOR_SAD = Font(color="6F42C1", bold=True)      # Morado
                COLOR_INA = Font(color="DC3545", bold=True)      # Rojo
                COLOR_FES = Font(color="FFC107", bold=True)      # Amarillo
                COLOR_VAC_LIC = Font(color="0D6EFD", bold=True)  # Azul
                COLOR_LIB = Font(color="6C757D")                 # Gris
                COLOR_DEFAULT = Font(color="000000")
                
                borde_fino = Border(
                    left=Side(style='thin', color="DDDDDD"), 
                    right=Side(style='thin', color="DDDDDD"), 
                    top=Side(style='thin', color="DDDDDD"), 
                    bottom=Side(style='thin', color="DDDDDD")
                )
                
                # Fuentes en línea para RichText (colores múltiples por celda)
                g_font = InlineFont(color="00B050", b=True)
                r_font = InlineFont(color="DC3545", b=True)
                
                # Fuentes para ATR y SAD combinados en RichText
                o_font = InlineFont(color="FD7E14", b=True)
                p_font = InlineFont(color="6F42C1", b=True)
                black_font = InlineFont(color="000000", b=True)
                
                logo_path = 'c:/Users/danie/Desarrollo/Asistencia/frontend/assets/img/logo.jpg'
                
                for s_name in writer.sheets:
                    ws = writer.sheets[s_name]
                    
                    # Quitar líneas de cuadrícula y fondo por defecto
                    ws.sheet_view.showGridLines = False
                    
                    # --- Agregar Membrete Corporativo ---
                    try:
                        img_header = Image(logo_path)
                        img_header.height = 75
                        img_header.width = 170
                        ws.add_image(img_header, 'A1')
                    except Exception as e:
                        pass # si el logo no se carga, ignora
                    
                    # Título del reporte en cabecera
                    ws.merge_cells('C2:H2')
                    title_cell = ws['C2']
                    # Asegurar de que no diga redundantemente "ASISTENCIA - ASISTENCIA SIGLAS", solo el nombre de la hoja
                    title_cell.value = f"REPORTE OFICIAL DE ASISTENCIA - {s_name.upper()}"
                    title_cell.font = Font(size=14, bold=True, color="003366")
                    title_cell.alignment = Alignment(horizontal='center', vertical='center')
                    
                    # Subtítulo (Departamento)
                    ws.merge_cells('C3:H3')
                    sub_cell = ws['C3']
                    sub_cell.value = "DEPARTAMENTO DE RECURSOS HUMANOS"
                    sub_cell.font = Font(size=11, bold=True, color="666666")
                    sub_cell.alignment = Alignment(horizontal='center', vertical='top')
                    
                    # Panel derecho de información ejecutiva (Período y Generación)
                    # Tomaremos las columnas I y J
                    ws['I1'] = "Fecha Emisión:"
                    ws['I1'].font = Font(bold=True, size=10, color="555555")
                    ws['I1'].alignment = Alignment(horizontal='right')
                    ws['J1'] = datetime.now().strftime('%d/%m/%Y %H:%M')
                    ws['J1'].font = Font(size=10, color="333333")
                    ws['J1'].alignment = Alignment(horizontal='left')
                    
                    ws['I2'] = "Período Reportado:"
                    ws['I2'].font = Font(bold=True, size=10, color="555555")
                    ws['I2'].alignment = Alignment(horizontal='right')
                    ws['J2'] = f"{f_ini.month:02d}/{f_ini.year}"
                    ws['J2'].font = Font(size=10, color="333333")
                    ws['J2'].alignment = Alignment(horizontal='left')
                    
                    ws['I3'] = "Sistema:"
                    ws['I3'].font = Font(bold=True, size=10, color="555555")
                    ws['I3'].alignment = Alignment(horizontal='right')
                    ws['J3'] = "Aguacol Asistencia"
                    ws['J3'].font = Font(size=10, color="333333")
                    ws['J3'].alignment = Alignment(horizontal='left')
                    
                    ws['I4'] = "Área Reportada:"
                    ws['I4'].font = Font(bold=True, size=10, color="555555")
                    ws['I4'].alignment = Alignment(horizontal='right')
                    ws['J4'] = str(area).upper() if area else "TODAS LAS ÁREAS"
                    ws['J4'].font = Font(size=10, color="333333")
                    ws['J4'].alignment = Alignment(horizontal='left')
                    
                    # Dar estilo a la fila de cabecera de datos (Fila 6, fila de encabezados)
                    for cell in ws[6]:
                        cell.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
                        cell.border = borde_fino
                        cell.font = Font(bold=True)
                    ws.row_dimensions[6].height = 30
                    
                    ws.freeze_panes = 'E7' # Congelar columnas A,B,C,D y filas 1 a 6
                    
                    # La lógica de ancho manual anterior fue reemplazada
                    # por auto-ajuste dinámico al final del bucle.
                        
                    # Aplicar bordes, centrado y color de fuente a los datos
                    for row in ws.iter_rows(min_row=7, min_col=1, max_col=ws.max_column):
                        for cell in row:
                            cell.border = borde_fino
                            
                            # A partir de la columna E, centramos
                            if cell.column >= 5:
                                cell.alignment = Alignment(horizontal='center', vertical='center')
                            
                            val = str(cell.value)
                            
                            # Colorear siglas en la hoja de matriz
                            if s_name == 'Conceptos':
                                if val == 'OK': cell.font = COLOR_OK
                                elif val == 'ATR': cell.font = COLOR_ATR
                                elif val == 'SAD': cell.font = COLOR_SAD
                                elif val == 'ATR-SAD': 
                                    cell.value = CellRichText(
                                        TextBlock(o_font, 'ATR'),
                                        TextBlock(black_font, '-'),
                                        TextBlock(p_font, 'SAD')
                                    )
                                elif val == 'INA': cell.font = COLOR_INA
                                elif val == 'FES': cell.font = COLOR_FES
                                elif val in ['VAC', 'LIC', 'LCM', 'LMU', 'CUM', 'DUE']: cell.font = COLOR_VAC_LIC
                                elif val == 'LIB': cell.font = COLOR_LIB
                            
                            # Colorear saldos/horas positivas y negativas en celda (RichText)
                            elif s_name in ['Horas Extras', 'Horas Reales', 'Conceptos', 'Acumulado']:
                                if '+' in val and '-' in val:
                                    parts = val.split(' ')
                                    rt_blocks = []
                                    for idx, p in enumerate(parts):
                                        suffix = ' ' if idx < len(parts) - 1 else ''
                                        if '+' in p: 
                                            rt_blocks.append(TextBlock(g_font, p + suffix))
                                        elif '-' in p: 
                                            rt_blocks.append(TextBlock(r_font, p + suffix))
                                        else:
                                            rt_blocks.append(TextBlock(InlineFont(), p + suffix))
                                    cell.value = CellRichText(*rt_blocks)
                                elif '+' in val:
                                    cell.font = COLOR_OK
                                elif '-' in val and val != '-': # ignorar guiones solitarios
                                    cell.font = COLOR_INA
                            
                    # --- Agregar Pie de Página Corporativo ---
                    foot_start = ws.max_row + 2
                    
                    # Nota de Privacidad
                    ws.merge_cells(f"B{foot_start}:J{foot_start}")
                    priv_cell = ws.cell(row=foot_start, column=2, value="AVISO DE CONFIDENCIALIDAD: Este documento y su contenido son de uso estrictamente interno y confidencial.")
                    priv_cell.font = Font(size=9, bold=True, color="AA0000")
                    priv_cell.alignment = Alignment(horizontal='left', vertical='center')
                    
                    # Firma
                    foot_start += 1
                    ws.merge_cells(f"B{foot_start}:J{foot_start}")
                    foot_cell = ws.cell(row=foot_start, column=2, value=f"Generado automáticamente por el Sistema de Asistencia de Aguacol S.A. - {datetime.now().strftime('%d/%m/%Y')}")
                    foot_cell.font = Font(size=9, italic=True, color="888888")
                    foot_cell.alignment = Alignment(horizontal='left', vertical='center')
                            
                    # --- Agregar Leyenda Horizontal al final de la hoja ---
                    if s_name == 'Conceptos':
                        legend_start = foot_start + 3
                        
                        leyenda = [
                            ("OK", "PRESENTE", COLOR_OK),
                            ("ATR", "ATRASO", COLOR_ATR),
                            ("SAD", "SALIDA ADELANTADA", COLOR_SAD),
                            ("INA", "INASISTENCIA", COLOR_INA),
                            ("LIB", "LIBRE", COLOR_LIB),
                            ("FES", "FERIADO", COLOR_FES),
                            ("VAC", "VACACIONES", COLOR_VAC_LIC),
                            ("LCM", "LICENCIA COMÚN", COLOR_VAC_LIC),
                            ("LMU", "LICENCIA MUTUAL", COLOR_VAC_LIC),
                            ("CUM", "CUMPLEAÑOS", COLOR_VAC_LIC),
                            ("DUE", "DUELO", COLOR_VAC_LIC),
                            ("ANO", "ANOMALÍA", COLOR_DEFAULT),
                            ("ESP", "J. ESPECIAL", COLOR_DEFAULT),
                        ]
                        
                        # Título Membrete
                        cell_titulo = ws.cell(row=legend_start, column=2, value="Glosario de Nomenclaturas:")
                        cell_titulo.font = Font(bold=True, italic=True)
                        
                        # Disposición Horizontal Distribuida (4 pares por fila)
                        col_offset = 2
                        current_row = legend_start + 1
                        for sigla, desc, color in leyenda:
                            cell_sigla = ws.cell(row=current_row, column=col_offset, value=sigla)
                            cell_desc = ws.cell(row=current_row, column=col_offset + 1, value=desc)
                            
                            cell_sigla.font = color
                            cell_sigla.alignment = Alignment(horizontal='right')
                            cell_desc.alignment = Alignment(horizontal='left')
                            cell_desc.font = Font(italic=True, color="666666")
                            
                            col_offset += 2
                            if col_offset > 8: # Mover a la siguiente línea al llegar a la columna 8
                                col_offset = 2
                                current_row += 1
                                
                    # Autoajustar el ancho de las columnas
                    for col in ws.columns:
                        max_length = 0
                        column_letter = col[0].column_letter
                        
                        for cell in col:
                            # Ignorar las celdas de la leyenda para el cálculo de ancho
                            if cell.row > ws.max_row - 10 and cell.column < 10 and s_name == 'Conceptos':
                                continue
                            try:
                                if cell.value:
                                    # Considerar saltos de línea en cabeceras
                                    lines = str(cell.value).split('\n')
                                    longest_line = max(len(l) for l in lines)
                                    if longest_line > max_length:
                                        max_length = longest_line
                            except:
                                pass
                        
                        adjusted_width = (max_length + 2)
                        if adjusted_width < 6: adjusted_width = 8
                        if adjusted_width > 45: adjusted_width = 45 # tope
                        
                        ws.column_dimensions[column_letter].width = adjusted_width
            
            output.seek(0)
            return output

        except Exception as e:
            logger.error(f"Error generando reporte Excel Multi-hoja: {e}")
            raise

    async def generate_excel_custom_range(self, fecha_inicio: str, fecha_fin: str, area: str = None, turno_id: int = None) -> BytesIO:
        """
        Genera un reporte Excel multi-hoja con la Matriz de Asistencia (réplica UI).
        """
        try:
            # Rango de fechas para las columnas
            f_ini = date.fromisoformat(fecha_inicio)
            f_fin = date.fromisoformat(fecha_fin)
            rango_dias = [(f_ini + timedelta(days=i)) for i in range((f_fin - f_ini).days + 1)]
            cols_dias = [d.day for d in rango_dias]
            
            # Pasar Año, Mes y Área explícitos al AsistenciaService
            # Pasar fechas string explicitas al nuevo motor por rango
            matrix_data = await self.asistencia_service.get_matrix_data_by_range(
                fecha_inicio, fecha_fin, area=area, turno_id=turno_id
            )
            empleados = matrix_data.get("empleados", [])
            
            # --- EVALUAR BONOS DESDE EL BACKEND ---
            from backend.services.bono_service import BonoService
            bono_srv = BonoService(self.asistencia_service.repository.db)
            bonos_eval = await bono_srv.evaluar_bonos_directo(
                empleados, 
                matrix_data.get("data", []), 
                matrix_data.get("justificaciones", []), 
                matrix_data.get("matrix", {})
            )
            
            # --- MATRIZ REAL DE DIAS POR EMPLEADO ---
            # La llave primaria es str(empleado_id), y dentro otra llave str "YYYY-MM-DD"
            emp_matrix = matrix_data.get("matrix", {})

            # 2. Construir DataFrames Base para cada Pestaña (Hoja)
            
            # Preparar arreglos para recolectar las filas
            matriz_rows = []
            reales_rows = []
            extras_rows = []
            acumulado_rows = []
            
            # Descubrir dinámicamente qué bonos existen
            todos_bonos = set()
            for emp_bonos in bonos_eval.values():
                todos_bonos.update(emp_bonos.keys())
            lista_bonos = sorted(list(todos_bonos))

            for emp in empleados:
                emp_id = emp['id']
                nom_completo = f"{emp['apellido_paterno']} {emp.get('apellido_materno', '')} {emp['nombre']}".strip().replace('  ', ' ')
                rut = emp.get('rut', '')
                activo_str = "SÍ" if emp.get('activo', 1) else "NO"
                
                # Base del diccionario para este empleado (Información estática)
                base_info = {'Identificador': emp_id, 'RUT': rut, 'Empleado': nom_completo, 'Activo': activo_str}
                
                # Variables sumatorias para la hoja de Conceptos (mensual)
                min_deuda = 0
                min_extra_bruto = 0
                min_extra_aprobado = 0
                
                # En Python, el objeto de fechas viene en matrix[emp_id]
                dias_dict = emp_matrix.get(str(emp_id), {})
                if not dias_dict and emp_id in emp_matrix:
                     dias_dict = emp_matrix[emp_id]
                
                # 1. Pimer recorrido para calcular totales del empleado
                for d in rango_dias:
                    f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                    dia_data = dias_dict.get(f_str)
                    if dia_data:
                        min_deuda += dia_data.get("minutos_deuda", 0)
                        min_extra_bruto += dia_data.get("minutos_extra_bruto", 0)
                        if dia_data.get("estado_he") == "APROBADO":
                             min_extra_aprobado += (dia_data.get("minutos_extra_autorizados") or 0)
                
                # 2. Rellenar columnas de totales
                base_info["HE Totales"] = self._format_hhmm(min_extra_bruto)
                base_info["Deuda Acum."] = f"-{self._format_hhmm(min_deuda)}" if min_deuda > 0 else "00:00"
                base_info["Saldo a Pagar"] = self._get_saldo(min_extra_aprobado, min_deuda)
                
                # 3. Evaluar Bonos
                bonos_empleado = bonos_eval.get(emp_id) or bonos_eval.get(str(emp_id), {})
                for bx in lista_bonos:
                    info_bx = bonos_empleado.get(bx)
                    if not info_bx or info_bx.get("aplica") is False:
                         base_info[bx] = "-"
                    else:
                         base_info[bx] = "SÍ" if info_bx.get("califica") else "NO"

                # Clonar el diccionario base para cada "Hoja"
                f_matriz = dict(base_info)
                f_reales = dict(base_info)
                f_extras = dict(base_info)
                f_acumulado = dict(base_info)

                # Variables para acumulados (Hoja 4)
                acum_semanal = 0
                acum_bolsa = 0
                es_bolsa = any(dia.get('tipo_programacion') == 'FLEXIBLE_BOLSA' for dia in dias_dict.values()) if dias_dict else False

                # 4. Segundo recorrido para rellenar la matriz de días
                for d in rango_dias:
                    f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                    dia_data = dias_dict.get(f_str)
                    
                    if d.weekday() == 0: # Lunes: Reset semanal
                        acum_semanal = 0

                    if not dia_data:
                        f_matriz[f_str] = ""
                        f_reales[f_str] = ""
                        f_extras[f_str] = ""
                        f_acumulado[f_str] = ""
                        continue
                     
                    # Mapeos de columnas según la hoja
                    
                    # Hoja 1: Matriz (Siglas y estados)
                    estado_bruto = dia_data.get("estado", "")
                    
                    sigla = estado_bruto
                    if estado_bruto == 'OK': sigla = 'OK'
                    elif estado_bruto == 'ATRASO': sigla = 'ATR'
                    elif estado_bruto == 'SALIDA_ADELANTADA': sigla = 'SAD'
                    elif estado_bruto == 'ATR_SAD': sigla = 'ATR-SAD'
                    elif estado_bruto and ('FALTA' in estado_bruto or estado_bruto == 'INASISTENCIA'): sigla = 'INA'
                    elif estado_bruto == 'LIBRE': sigla = 'LIB'
                    elif estado_bruto == 'FERIADO': sigla = 'FES'
                    elif estado_bruto == 'VACACIONES': sigla = 'VAC'
                    elif estado_bruto == 'LICENCIA': sigla = 'LIC'
                    elif estado_bruto == 'LICENCIA COMUN': sigla = 'LCM'
                    elif estado_bruto == 'LICENCIA MUTUAL': sigla = 'LMU'
                    elif estado_bruto == 'CUMPLEAÑOS': sigla = 'CUM'
                    elif estado_bruto == 'DUELO PADRES / HERMANOS': sigla = 'DUE'
                    elif estado_bruto == 'ANOMALIA': sigla = 'ANO'
                    elif estado_bruto == 'EN_CURSO': sigla = 'CUR'
                    elif estado_bruto == 'JORNADA_ESPECIAL': sigla = 'ESP'
                    elif estado_bruto == 'EXTRA': sigla = 'EXTRA'
                    elif estado_bruto == 'NO_ACTIVO': sigla = '---'
                    elif dia_data.get('es_fin_de_semana') and not estado_bruto: sigla = '---'
                    
                    if not sigla:
                        sigla = "---"
                    
                    f_matriz[f_str] = sigla
                    
                    # Hoja 2: Reales (Cantidad de Horas Trabajadas HH:MM)
                    estados_con_horas = ['OK', 'ATRASO', 'SALIDA_ADELANTADA', 'ATR_SAD', 'JORNADA_ESPECIAL', 'EXTRA', 'EN_CURSO']
                    min_trabajados = 0
                    if estado_bruto in estados_con_horas:
                        if estado_bruto == 'EN_CURSO':
                            f_reales[f_str] = ">>"
                        else:
                            horas_dec = dia_data.get('horas_trabajadas', 0)
                            if horas_dec:
                                min_trabajados = int(round(horas_dec * 60))
                                h_int = min_trabajados // 60
                                m_int = min_trabajados % 60
                                f_reales[f_str] = f"{h_int:02d}:{m_int:02d}"
                            else:
                                f_reales[f_str] = "00:00"
                    else:
                        f_reales[f_str] = ""
                    
                    # Hoja 3: Extras (HE Brutas, Atrasos, Deuda)
                    d_mins = dia_data.get("minutos_deuda", 0)
                    h_mins = dia_data.get("minutos_extra_bruto", 0)
                    texto_extra = ""
                    if h_mins and h_mins > 0: texto_extra += f"+{self._format_hhmm(h_mins)} "
                    if d_mins and d_mins > 0: texto_extra += f"-{self._format_hhmm(d_mins)}"
                    f_extras[f_str] = texto_extra.strip()

                    # Hoja 4: Acumulado
                    acum_semanal += min_trabajados
                    acum_bolsa += min_trabajados
                    if es_bolsa:
                        f_acumulado[f_str] = self._format_hhmm(acum_bolsa)
                    else:
                        f_acumulado[f_str] = self._format_hhmm(acum_semanal)
                
                # Agregar las filas
                matriz_rows.append(f_matriz)
                reales_rows.append(f_reales)
                extras_rows.append(f_extras)
                acumulado_rows.append(f_acumulado)

            # 3. Crear DataFrames
            df_matriz = pd.DataFrame(matriz_rows)
            df_reales = pd.DataFrame(reales_rows)
            df_extras = pd.DataFrame(extras_rows)
            df_acumulado = pd.DataFrame(acumulado_rows)
            
            # Ordenar columnas numéricas (días al final)
            orden_base = ['Identificador', 'RUT', 'Empleado', 'Activo', 'HE Totales', 'Deuda Acum.', 'Saldo a Pagar'] + lista_bonos
            orden_dias = [f"{d.year}-{d.month:02d}-{d.day:02d}" for d in rango_dias]
            orden_completo_grilla = orden_base + orden_dias
            
            df_matriz = df_matriz[orden_completo_grilla]
            df_reales = df_reales[orden_completo_grilla]
            df_extras = df_extras[orden_completo_grilla]
            df_acumulado = df_acumulado[orden_completo_grilla]
            
            # ---- MAQUETACIÓN VISUAL EXACTA (ESPEJO DE LA UI) ----
            dias_espanol = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            rename_mapping = {
                'HE Totales': 'HE Totales\n(HH:MM)',
                'Deuda Acum.': 'Deuda Acum.\n(HH:MM)',
                'Saldo a Pagar': 'Saldo a Pagar\n(Saldo)'
            }
            # Bonos
            for b in lista_bonos:
                rename_mapping[b] = f"{b}\n(Califica)"
            # Días
            for d in rango_dias:
                fecha_str = f"{d.day:02d}-{d.month:02d}-{d.year}"
                f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                dia_semana_str = dias_espanol[d.weekday()]
                rename_mapping[f_str] = f"{fecha_str}\n{dia_semana_str}"
                
            df_matriz = df_matriz.rename(columns=rename_mapping)
            df_reales = df_reales.rename(columns=rename_mapping)
            df_extras = df_extras.rename(columns=rename_mapping)
            df_acumulado = df_acumulado.rename(columns=rename_mapping)

            # 4. Generar Excel Multi-Hoja
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Escribir cada Dataframe en su respectiva pestaña (Empezar en Fila 6, index=5)
                df_matriz.to_excel(writer, index=False, sheet_name='Conceptos', startrow=5)
                df_reales.to_excel(writer, index=False, sheet_name='Horas Reales', startrow=5)
                df_extras.to_excel(writer, index=False, sheet_name='Horas Extras', startrow=5)
                df_acumulado.to_excel(writer, index=False, sheet_name='Acumulado', startrow=5)

                
                # Ajustar formatos visuales (Ancho de columnas centrados y saltos de línea)
                from openpyxl.styles import Alignment, Font, Border, Side
                from openpyxl.drawing.image import Image
                from openpyxl.cell.rich_text import TextBlock, CellRichText
                from openpyxl.cell.text import InlineFont
                
                # Paleta de colores para fuentes
                COLOR_OK = Font(color="00B050", bold=True)       # Verde
                COLOR_ATR = Font(color="FD7E14", bold=True)      # Naranja
                COLOR_SAD = Font(color="6F42C1", bold=True)      # Morado
                COLOR_INA = Font(color="DC3545", bold=True)      # Rojo
                COLOR_FES = Font(color="FFC107", bold=True)      # Amarillo
                COLOR_VAC_LIC = Font(color="0D6EFD", bold=True)  # Azul
                COLOR_LIB = Font(color="6C757D")                 # Gris
                COLOR_DEFAULT = Font(color="000000")
                
                borde_fino = Border(
                    left=Side(style='thin', color="DDDDDD"), 
                    right=Side(style='thin', color="DDDDDD"), 
                    top=Side(style='thin', color="DDDDDD"), 
                    bottom=Side(style='thin', color="DDDDDD")
                )
                
                # Fuentes en línea para RichText (colores múltiples por celda)
                g_font = InlineFont(color="00B050", b=True)
                r_font = InlineFont(color="DC3545", b=True)
                
                # Fuentes para ATR y SAD combinados en RichText
                o_font = InlineFont(color="FD7E14", b=True)
                p_font = InlineFont(color="6F42C1", b=True)
                black_font = InlineFont(color="000000", b=True)
                
                logo_path = 'c:/Users/danie/Desarrollo/Asistencia/frontend/assets/img/logo.jpg'
                
                for s_name in writer.sheets:
                    ws = writer.sheets[s_name]
                    
                    # Quitar líneas de cuadrícula y fondo por defecto
                    ws.sheet_view.showGridLines = False
                    
                    # --- Agregar Membrete Corporativo ---
                    try:
                        img_header = Image(logo_path)
                        img_header.height = 75
                        img_header.width = 170
                        ws.add_image(img_header, 'A1')
                    except Exception as e:
                        pass # si el logo no se carga, ignora
                    
                    # Título del reporte en cabecera
                    ws.merge_cells('C2:H2')
                    title_cell = ws['C2']
                    # Asegurar de que no diga redundantemente "ASISTENCIA - ASISTENCIA SIGLAS", solo el nombre de la hoja
                    title_cell.value = f"REPORTE OFICIAL DE ASISTENCIA - {s_name.upper()}"
                    title_cell.font = Font(size=14, bold=True, color="003366")
                    title_cell.alignment = Alignment(horizontal='center', vertical='center')
                    
                    # Subtítulo (Departamento)
                    ws.merge_cells('C3:H3')
                    sub_cell = ws['C3']
                    sub_cell.value = "DEPARTAMENTO DE RECURSOS HUMANOS"
                    sub_cell.font = Font(size=11, bold=True, color="666666")
                    sub_cell.alignment = Alignment(horizontal='center', vertical='top')
                    
                    # Panel derecho de información ejecutiva (Período y Generación)
                    # Tomaremos las columnas I y J
                    ws['I1'] = "Fecha Emisión:"
                    ws['I1'].font = Font(bold=True, size=10, color="555555")
                    ws['I1'].alignment = Alignment(horizontal='right')
                    ws['J1'] = datetime.now().strftime('%d/%m/%Y %H:%M')
                    ws['J1'].font = Font(size=10, color="333333")
                    ws['J1'].alignment = Alignment(horizontal='left')
                    
                    ws['I2'] = "Período Reportado:"
                    ws['I2'].font = Font(bold=True, size=10, color="555555")
                    ws['I2'].alignment = Alignment(horizontal='right')
                    ws['J2'] = f"{f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}"
                    ws['J2'].font = Font(size=10, color="333333")
                    ws['J2'].alignment = Alignment(horizontal='left')
                    
                    ws['I3'] = "Sistema:"
                    ws['I3'].font = Font(bold=True, size=10, color="555555")
                    ws['I3'].alignment = Alignment(horizontal='right')
                    ws['J3'] = "Aguacol Asistencia"
                    ws['J3'].font = Font(size=10, color="333333")
                    ws['J3'].alignment = Alignment(horizontal='left')
                    
                    ws['I4'] = "Área Reportada:"
                    ws['I4'].font = Font(bold=True, size=10, color="555555")
                    ws['I4'].alignment = Alignment(horizontal='right')
                    ws['J4'] = str(area).upper() if area else "TODAS LAS ÁREAS"
                    ws['J4'].font = Font(size=10, color="333333")
                    ws['J4'].alignment = Alignment(horizontal='left')
                    
                    # Dar estilo a la fila de cabecera de datos (Fila 6, fila de encabezados)
                    for cell in ws[6]:
                        cell.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
                        cell.border = borde_fino
                        cell.font = Font(bold=True)
                    ws.row_dimensions[6].height = 30
                    
                    ws.freeze_panes = 'E7' # Congelar columnas A,B,C,D y filas 1 a 6
                    
                    # La lógica de ancho manual anterior fue reemplazada
                    # por auto-ajuste dinámico al final del bucle.
                        
                    # Aplicar bordes, centrado y color de fuente a los datos
                    for row in ws.iter_rows(min_row=7, min_col=1, max_col=ws.max_column):
                        for cell in row:
                            cell.border = borde_fino
                            
                            # A partir de la columna E, centramos
                            if cell.column >= 5:
                                cell.alignment = Alignment(horizontal='center', vertical='center')
                            
                            val = str(cell.value)
                            
                            # Colorear siglas en la hoja de matriz
                            if s_name == 'Conceptos':
                                if val == 'OK': cell.font = COLOR_OK
                                elif val == 'ATR': cell.font = COLOR_ATR
                                elif val == 'SAD': cell.font = COLOR_SAD
                                elif val == 'ATR-SAD': 
                                    cell.value = CellRichText(
                                        TextBlock(o_font, 'ATR'),
                                        TextBlock(black_font, '-'),
                                        TextBlock(p_font, 'SAD')
                                    )
                                elif val == 'INA': cell.font = COLOR_INA
                                elif val == 'FES': cell.font = COLOR_FES
                                elif val in ['VAC', 'LIC', 'LCM', 'LMU', 'CUM', 'DUE']: cell.font = COLOR_VAC_LIC
                                elif val == 'LIB': cell.font = COLOR_LIB
                            
                            # Colorear saldos/horas positivas y negativas en celda (RichText)
                            elif s_name in ['Horas Extras', 'Horas Reales', 'Conceptos', 'Acumulado']:
                                if '+' in val and '-' in val:
                                    parts = val.split(' ')
                                    rt_blocks = []
                                    for idx, p in enumerate(parts):
                                        suffix = ' ' if idx < len(parts) - 1 else ''
                                        if '+' in p: 
                                            rt_blocks.append(TextBlock(g_font, p + suffix))
                                        elif '-' in p: 
                                            rt_blocks.append(TextBlock(r_font, p + suffix))
                                        else:
                                            rt_blocks.append(TextBlock(InlineFont(), p + suffix))
                                    cell.value = CellRichText(*rt_blocks)
                                elif '+' in val:
                                    cell.font = COLOR_OK
                                elif '-' in val and val != '-': # ignorar guiones solitarios
                                    cell.font = COLOR_INA
                            
                    # --- Agregar Pie de Página Corporativo ---
                    foot_start = ws.max_row + 2
                    
                    # Nota de Privacidad
                    ws.merge_cells(f"B{foot_start}:J{foot_start}")
                    priv_cell = ws.cell(row=foot_start, column=2, value="AVISO DE CONFIDENCIALIDAD: Este documento y su contenido son de uso estrictamente interno y confidencial.")
                    priv_cell.font = Font(size=9, bold=True, color="AA0000")
                    priv_cell.alignment = Alignment(horizontal='left', vertical='center')
                    
                    # Firma
                    foot_start += 1
                    ws.merge_cells(f"B{foot_start}:J{foot_start}")
                    foot_cell = ws.cell(row=foot_start, column=2, value=f"Generado automáticamente por el Sistema de Asistencia de Aguacol S.A. - {datetime.now().strftime('%d/%m/%Y')}")
                    foot_cell.font = Font(size=9, italic=True, color="888888")
                    foot_cell.alignment = Alignment(horizontal='left', vertical='center')
                            
                    # --- Agregar Leyenda Horizontal al final de la hoja ---
                    if s_name == 'Conceptos':
                        legend_start = foot_start + 3
                        
                        leyenda = [
                            ("OK", "PRESENTE", COLOR_OK),
                            ("ATR", "ATRASO", COLOR_ATR),
                            ("SAD", "SALIDA ADELANTADA", COLOR_SAD),
                            ("INA", "INASISTENCIA", COLOR_INA),
                            ("LIB", "LIBRE", COLOR_LIB),
                            ("FES", "FERIADO", COLOR_FES),
                            ("VAC", "VACACIONES", COLOR_VAC_LIC),
                            ("LCM", "LICENCIA COMÚN", COLOR_VAC_LIC),
                            ("LMU", "LICENCIA MUTUAL", COLOR_VAC_LIC),
                            ("CUM", "CUMPLEAÑOS", COLOR_VAC_LIC),
                            ("DUE", "DUELO", COLOR_VAC_LIC),
                            ("ANO", "ANOMALÍA", COLOR_DEFAULT),
                            ("ESP", "J. ESPECIAL", COLOR_DEFAULT),
                        ]
                        
                        # Título Membrete
                        cell_titulo = ws.cell(row=legend_start, column=2, value="Glosario de Nomenclaturas:")
                        cell_titulo.font = Font(bold=True, italic=True)
                        
                        # Disposición Horizontal Distribuida (4 pares por fila)
                        col_offset = 2
                        current_row = legend_start + 1
                        for sigla, desc, color in leyenda:
                            cell_sigla = ws.cell(row=current_row, column=col_offset, value=sigla)
                            cell_desc = ws.cell(row=current_row, column=col_offset + 1, value=desc)
                            
                            cell_sigla.font = color
                            cell_sigla.alignment = Alignment(horizontal='right')
                            cell_desc.alignment = Alignment(horizontal='left')
                            cell_desc.font = Font(italic=True, color="666666")
                            
                            col_offset += 2
                            if col_offset > 8: # Mover a la siguiente línea al llegar a la columna 8
                                col_offset = 2
                                current_row += 1
                                
                    # Autoajustar el ancho de las columnas
                    for col in ws.columns:
                        max_length = 0
                        column_letter = col[0].column_letter
                        
                        for cell in col:
                            # Ignorar las celdas de la leyenda para el cálculo de ancho
                            if cell.row > ws.max_row - 10 and cell.column < 10 and s_name == 'Conceptos':
                                continue
                            try:
                                if cell.value:
                                    # Considerar saltos de línea en cabeceras
                                    lines = str(cell.value).split('\n')
                                    longest_line = max(len(l) for l in lines)
                                    if longest_line > max_length:
                                        max_length = longest_line
                            except:
                                pass
                        
                        adjusted_width = (max_length + 2)
                        if adjusted_width < 6: adjusted_width = 8
                        if adjusted_width > 45: adjusted_width = 45 # tope
                        
                        ws.column_dimensions[column_letter].width = adjusted_width
            
            output.seek(0)
            return output

        except Exception as e:
            logger.error(f"Error generando reporte Excel Multi-hoja: {e}")
            raise


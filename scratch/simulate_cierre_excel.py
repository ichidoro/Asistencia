import sys
import os
import asyncio
from pathlib import Path

# Agregar el directorio raíz al path para importar los módulos del backend
base_path = Path("c:/Users/danie/Proyectos_Python/Asistencia")
sys.path.append(str(base_path))

from backend.core.database import Database
from backend.repositories.asistencia import AsistenciaRepository
from backend.services.asistencia_service import AsistenciaService
from backend.repositories.configuracion import ConfiguracionRepository
from backend.services.configuracion_service import ConfiguracionService
from backend.services.bono_service import BonoService

def format_hhmmss(minutos) -> str:
    if minutos is None:
        return "-"
    if minutos == 0:
        return "00:00:00"
    signo = "-" if minutos < 0 else ""
    total_secs = round(abs(minutos) * 60)
    h = total_secs // 3600
    m = (total_secs % 3600) // 60
    s = total_secs % 60
    return f"{signo}{h:02d}:{m:02d}:{s:02d}"

def get_saldo(extras_aprobados: int, deuda: int) -> str:
    saldo = (extras_aprobados or 0) - (deuda or 0)
    signo = "+" if saldo > 0 else ("-" if saldo < 0 else "")
    return f"{signo}{format_hhmmss(abs(saldo))}"

async def simulate():
    print("[SIMULACION] Iniciando Simulacion de Calculos Excel...")
    
    # 1. Inicializar base de datos y repositorios
    db = Database()
    asistencia_repo = AsistenciaRepository(db)
    asistencia_service = AsistenciaService(asistencia_repo)
    config_repo = ConfiguracionRepository(db)
    config_service = ConfiguracionService(config_repo)
    bono_srv = BonoService(db)
    
    # 2. Buscar el periodo activo para la prueba
    periodo_activo = await config_service.get_periodo_rrhh_activo()
    if not periodo_activo:
        print("[INFO] No hay ningun periodo RRHH activo. Buscando en la tabla periodos_rrhh...")
        periodos = await config_service.get_all_periodos_rrhh()
        if periodos:
            periodo_activo = periodos[0]
            print(f"[INFO] Usando periodo: {periodo_activo['mes_cierre']}")
        else:
            print("[ERROR] No se encontraron periodos en la base de datos.")
            return

    fecha_inicio = periodo_activo["fecha_inicio"]
    fecha_fin = periodo_activo["fecha_fin"]
    print(f"[INFO] Rango del Periodo: {fecha_inicio} al {fecha_fin}")
    
    # 3. Obtener los datos de la matriz
    from datetime import date, timedelta
    f_ini = date.fromisoformat(fecha_inicio)
    f_fin = date.fromisoformat(fecha_fin)
    rango_dias = [(f_ini + timedelta(days=i)) for i in range((f_fin - f_ini).days + 1)]
    
    print("[INFO] Cargando datos de matriz desde AsistenciaService...")
    matrix_data = await asistencia_service.get_matrix_data_with_projections(
        f_ini.month, f_ini.year, fecha_inicio_override=fecha_inicio, fecha_fin_override=fecha_fin
    )
    
    empleados = matrix_data.get("empleados", [])
    emp_matrix = matrix_data.get("matrix", {})
    feriados = matrix_data.get("feriados", [])
    feriados_set = {f['fecha'] for f in feriados}
    
    print(f"[INFO] Empleados cargados: {len(empleados)}")
    print(f"[INFO] Feriados en el periodo: {len(feriados)}")
    
    # Evaluar bonos
    bonos_eval = await bono_srv.evaluar_bonos_directo(
        empleados, 
        matrix_data.get("data", []), 
        matrix_data.get("justificaciones", []), 
        matrix_data.get("matrix", {})
    )
    
    # Descubrir qué bonos aplican
    todos_bonos = set()
    for emp_bonos in bonos_eval.values():
        todos_bonos.update(emp_bonos.keys())
    lista_bonos = sorted(list(todos_bonos))
    print(f"[INFO] Tipos de Bonos encontrados: {lista_bonos}")
    
    # 4. Simulación de los cálculos por empleado
    rows_calc = []
    hay_bolsa = False
    
    for emp in empleados:
        emp_id = emp['id']
        nom_completo = emp['nombre_completo']
        dias_dict = emp_matrix.get(str(emp_id), {})
        if not dias_dict and emp_id in emp_matrix:
            dias_dict = emp_matrix[emp_id]
            
        es_bolsa = emp.get('tipo_programacion') == 'FLEXIBLE_BOLSA'
        if es_bolsa:
            hay_bolsa = True
            
        he_bruto = 0
        he_apr = 0
        he_rec = 0
        he_pend = 0
        d_tot = 0
        min_atr = 0
        min_sad = 0
        min_col = 0
        min_per = 0
        
        cnt_atr = 0
        cnt_sad = 0
        cnt_inas = 0
        cnt_esp = 0
        cnt_per = 0
        cnt_efectivos = 0
        
        acum_bolsa = 0
        excedido = False
        meta_min = 0
        
        if es_bolsa:
            meta_original = emp.get("meta_mensual_minutos")
            if not meta_original:
                meta_original = round((emp.get("meta_horas_semanales") or 0.0) * 60)
            
            dias_programados = 0
            dias_justificados = 0
            
            for d in rango_dias:
                f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
                is_fer = f_str in feriados_set
                di_check = dias_dict.get(f_str, {})
                
                day_db = d.weekday()
                turno_dias = emp.get("turno_dias", {})
                day_info = turno_dias.get(day_db, {})
                is_structurally_libre = day_info.get("es_libre") == 1
                
                is_descanso = is_fer or is_structurally_libre or (di_check.get("estado") == 'LIBRE')
                
                if not is_descanso:
                    dias_programados += 1
                    estados_justificados = ['VACACIONES', 'LICENCIA', 'LIC_COMUN', 'LIC_MUTUAL', 'CUMPLEAÑOS', 'DUELO', 'PERMISO']
                    di_estado = di_check.get("estado", "") or ""
                    is_justificado = di_estado == 'JORNADA_ESPECIAL' or any(ej in di_estado.upper() for ej in estados_justificados)
                    
                    if is_justificado:
                        dias_justificados += 1
                        
            # Evitar división por cero
            if dias_programados > 0:
                if dias_justificados > 0:
                    valor_turno_min = meta_original / dias_programados
                    meta_min = round(meta_original - (valor_turno_min * dias_justificados))
                else:
                    meta_min = meta_original
            else:
                meta_min = meta_original
                
            if emp.get("meta_ajustada_minutos_descuento") and dias_justificados == 0:
                meta_min = max(0, meta_min - emp.get("meta_ajustada_minutos_descuento"))
        
        acum_semanal = 0
        start_day_db = emp.get("primer_dia_semana_turno", 0)
        
        for d in rango_dias:
            if d.weekday() == start_day_db:
                acum_semanal = 0
                
            f_str = f"{d.year}-{d.month:02d}-{d.day:02d}"
            di = dias_dict.get(f_str)
            if not di:
                continue
                
            trab = round((di.get("horas_trabajadas") or 0.0) * 60)
            di_estado = di.get("estado") or ""
            is_esp = di_estado in ['JORNADA_ESPECIAL', 'EXTRA', 'FERIADO Y JORNADA EXTRA', 'DÍA LIBRE Y JORNADA EXTRA']
            
            if not es_bolsa and not is_esp:
                acum_semanal += trab
                
            di["_acumuladoSemanalSnap"] = acum_semanal
            
            if not is_esp and not es_bolsa:
                tiene_condonacion = (di.get("deuda_condonada") or 0) > 0
                net_deuda = 0 if tiene_condonacion else (di.get("minutos_deuda") or 0)
                
                raw_col = di.get("minutos_exceso_colacion") or 0
                raw_per = di.get("minutos_permiso_personal_deuda") or 0
                raw_atr = 0 if tiene_condonacion else (di.get("minutos_atraso") or 0)
                raw_sad = 0 if tiene_condonacion else (di.get("minutos_salida_adelantada") or 0)
                
                raw_total = raw_col + raw_per + raw_atr + raw_sad
                
                day_col = 0
                day_per = 0
                day_atr = 0
                day_sad = 0
                
                if net_deuda > 0 and raw_total > 0:
                    if net_deuda >= raw_total:
                        day_col = raw_col
                        day_per = raw_per
                        day_atr = raw_atr
                        day_sad = raw_sad
                    else:
                        factor = net_deuda / raw_total
                        day_col = raw_col * factor
                        day_per = raw_per * factor
                        day_atr = raw_atr * factor
                        day_sad = raw_sad * factor
                        
                d_tot += net_deuda
                min_col += day_col
                min_per += day_per
                min_atr += day_atr
                min_sad += day_sad
                
                if (di.get("minutos_atraso") or 0) > 0 and not tiene_condonacion:
                    cnt_atr += 1
                if (di.get("minutos_salida_adelantada") or 0) > 0 and not tiene_condonacion:
                    cnt_sad += 1
                if di.get("tiene_permiso_hora") or di.get("permiso_activo"):
                    cnt_per += 1
                    
            if di_estado == 'INASISTENCIA':
                cnt_inas += 1
            if is_esp:
                cnt_esp += 1
            if di.get("hora_entrada_real") and not is_esp and di_estado not in ['LIBRE', 'FERIADO', 'INASISTENCIA']:
                cnt_efectivos += 1
                
            # HE calculations
            if not is_esp:
                if es_bolsa:
                    snap_antes = acum_bolsa
                    acum_bolsa += trab
                    di["_acumuladoBolsaSnapPrev"] = snap_antes
                    di["_acumuladoBolsaSnap"] = acum_bolsa
                    di["_metaMinBolsa"] = meta_min
                    
                    if excedido:
                        he_bruto += trab
                    elif acum_bolsa > meta_min and trab > 0:
                        he_bruto += (acum_bolsa - meta_min)
                        excedido = True
                else:
                    he_bruto += (di.get("minutos_extra_bruto") or 0)
            elif es_bolsa:
                di["_acumuladoBolsaSnapPrev"] = acum_bolsa
                di["_acumuladoBolsaSnap"] = acum_bolsa
                di["_metaMinBolsa"] = meta_min
                
            if not is_esp:
                if di.get("estado_he") == 'APROBADO':
                    he_apr += (di.get("minutos_extra_autorizados") or 0)
                elif di.get("estado_he") == 'RECHAZADO':
                    he_rec += (di.get("minutos_extra_bruto") or 0)
                elif (di.get("minutos_extra_bruto") or 0) > 0:
                    he_pend += (di.get("minutos_extra_bruto") or 0)
                    
        he_bruto = round(he_bruto)
        he_apr = round(he_apr)
        he_rec = round(he_rec)
        he_pend = round(he_pend)
        
        saldo = he_apr - d_tot
        saldo_meta = (acum_bolsa - meta_min) if es_bolsa else None
        
        rows_calc.append({
            "emp_id": emp_id,
            "nombre": nom_completo,
            "esBolsa": es_bolsa,
            "he_bruto": he_bruto,
            "he_apr": he_apr,
            "he_rec": he_rec,
            "he_pend": he_pend,
            "d_tot": d_tot,
            "min_col": round(min_col),
            "min_per": round(min_per),
            "min_atr": round(min_atr),
            "min_sad": round(min_sad),
            "cnt_atr": cnt_atr,
            "cnt_sad": cnt_sad,
            "cnt_inas": cnt_inas,
            "cnt_esp": cnt_esp,
            "cnt_per": cnt_per,
            "cnt_efectivos": cnt_efectivos,
            "saldo": saldo,
            "metaMin": meta_min,
            "acumBolsa": acum_bolsa,
            "saldoMeta": saldo_meta
        })
        
    print("\n[RESULTADOS] Muestra de Resultados de la Simulacion:")
    print("-" * 120)
    print(f"{'Empleado':<30} | {'HE Apr':<10} | {'Deuda':<10} | {'Saldo Neto':<12} | {'Incid':<6} | {'Bolsa (Meta/Acum/Bal)':<25}")
    print("-" * 120)
    
    for r in rows_calc[:10]: # Mostrar los primeros 10 empleados
        he_apr_str = format_hhmmss(r["he_apr"])
        d_tot_str = format_hhmmss(r["d_tot"])
        saldo_str = get_saldo(r["he_apr"], r["d_tot"])
        tot_incid = r["cnt_per"] + r["cnt_atr"] + r["cnt_sad"] + r["cnt_inas"] + r["cnt_esp"]
        
        if r["esBolsa"]:
            bolsa_str = f"{format_hhmmss(r['metaMin'])} / {format_hhmmss(r['acumBolsa'])} / {format_hhmmss(r['saldoMeta'])}"
        else:
            bolsa_str = "N/A"
            
        # Clean employee name encoding
        clean_name = r['nombre'].encode('ascii', errors='ignore').decode('ascii')
        print(f"{clean_name[:30]:<30} | {he_apr_str:<10} | {d_tot_str:<10} | {saldo_str:<12} | {tot_incid:<6} | {bolsa_str:<25}")
        
    print("-" * 120)
    print("[EXITO] Simulacion de Calculos completada sin errores logicos.")

if __name__ == "__main__":
    asyncio.run(simulate())

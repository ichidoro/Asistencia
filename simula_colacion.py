import asyncio
from datetime import datetime, timedelta

# Copia de la lógica actual en AsistenciaService._calculate_attendance
def simular_cálculo(hora_ent, hora_sal, minutos_colacion_auto):
    print(f"Simulando Entrada: {hora_ent.strftime('%H:%M')} | Salida: {hora_sal.strftime('%H:%M')}")
    print(f"Configuración de turno: Descuento Colación Automática activado ({minutos_colacion_auto} min)")
    
    r_ent = hora_ent
    r_sal = hora_sal
    
    # Horas trabajadas brutas
    horas_trabajadas = (r_sal - r_ent).total_seconds() / 3600.0
    print(f"  -> Horas trabajadas brutas: {horas_trabajadas:.2f} hrs")
    
    minutos_colacion = 0
    minutos_colacion_permitidos = minutos_colacion_auto
    
    # Lógica actual
    minutos_colacion = minutos_colacion_permitidos
    if minutos_colacion > 0:
        mitad_jornada = r_ent + (r_sal - r_ent) / 2
        inicio_colacion_auto = mitad_jornada - timedelta(minutes=minutos_colacion / 2)
        fin_colacion_auto = mitad_jornada + timedelta(minutes=minutos_colacion / 2)
        print(f"  -> Asigna horario colación adivinado: {inicio_colacion_auto.strftime('%H:%M')} a {fin_colacion_auto.strftime('%H:%M')}")
        
    horas_trabajadas -= (minutos_colacion) / 60.0
    horas_trabajadas = round(max(horas_trabajadas, 0), 4)
    print(f"  -> Horas trabajadas finales (tras descuento): {horas_trabajadas:.2f} hrs\n")
    return horas_trabajadas

# Simulando el propuesto (Alternativa 1)
def simular_cálculo_propuesto(hora_ent, hora_sal, minutos_colacion_auto, umbral_horas):
    print(f"Simulando (PROPUESTO) Entrada: {hora_ent.strftime('%H:%M')} | Salida: {hora_sal.strftime('%H:%M')}")
    print(f"Configuración de turno: Colación Auto ({minutos_colacion_auto} min) | Umbral: {umbral_horas} hrs")
    
    r_ent = hora_ent
    r_sal = hora_sal
    
    # Horas trabajadas brutas
    horas_trabajadas = (r_sal - r_ent).total_seconds() / 3600.0
    print(f"  -> Horas trabajadas brutas: {horas_trabajadas:.2f} hrs")
    
    minutos_colacion = 0
    minutos_colacion_permitidos = minutos_colacion_auto
    
    # Lógica con umbral
    if umbral_horas > 0 and horas_trabajadas < umbral_horas:
        print("  -> ¡UMBRAL NO ALCANZADO! Se omite el descuento automático de colación.")
        minutos_colacion = 0
    else:
        minutos_colacion = minutos_colacion_permitidos
        print("  -> Umbral alcanzado. Se descuenta colación.")
        
    horas_trabajadas -= (minutos_colacion) / 60.0
    horas_trabajadas = round(max(horas_trabajadas, 0), 4)
    print(f"  -> Horas trabajadas finales (tras descuento): {horas_trabajadas:.2f} hrs\n")

# Caso de prueba
t_entrada = datetime.strptime("2026-05-15 08:30", "%Y-%m-%d %H:%M")
t_salida = datetime.strptime("2026-05-15 11:00", "%Y-%m-%d %H:%M") # Se fue a las 2.5 horas

print("--- RESULTADO CÓDIGO ACTUAL ---")
simular_cálculo(t_entrada, t_salida, 60)

print("--- RESULTADO CÓDIGO CON PLAN (Umbral 5.0 hrs) ---")
simular_cálculo_propuesto(t_entrada, t_salida, 60, 5.0)


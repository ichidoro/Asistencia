from datetime import datetime, timedelta

first_log_dt = datetime.strptime('2026-05-06 14:57:42', '%Y-%m-%d %H:%M:%S')

configs = [
    {'hora_entrada': '23:00', 'hora_salida': '07:00', 'cruza_medianoche': 1},
    {'hora_entrada': '07:00', 'hora_salida': '15:00', 'cruza_medianoche': 0},
    {'hora_entrada': '15:00', 'hora_salida': '23:00', 'cruza_medianoche': 0}
]

winner_sem = 1
min_delta = None

for i, sem_config in enumerate(configs):
    ent_str = sem_config.get('hora_entrada')
    sal_str = sem_config.get('hora_salida')
    
    t_in_dt = datetime.strptime(f"{first_log_dt.strftime('%Y-%m-%d')} {ent_str}:00", "%Y-%m-%d %H:%M:%S")
    
    diff_seconds = abs((first_log_dt - t_in_dt).total_seconds())
    
    if min_delta is None or diff_seconds < min_delta:
        min_delta = diff_seconds
        winner_sem = i + 1

print('Winner:', winner_sem)

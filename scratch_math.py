from datetime import datetime, timedelta

first_assignment = '2026-04-26'
f_asig_dt_init = datetime.strptime(first_assignment, '%Y-%m-%d')
f_asig_dt_init = f_asig_dt_init - timedelta(days=f_asig_dt_init.weekday())
print(f"first_assignment={first_assignment}")
print(f"f_asig_dt_init normalizado={f_asig_dt_init.strftime('%Y-%m-%d')} (weekday={f_asig_dt_init.weekday()})")

tot_sems_init = 3

# Primer log de Emp1 = 27/04 06:36
first_log_fecha = '2026-04-27'
log_dt_init = datetime.strptime(first_log_fecha, '%Y-%m-%d')
d_diff_init = (log_dt_init - f_asig_dt_init).days
mat_sem_init = (d_diff_init // 7) % tot_sems_init + 1 if d_diff_init >= 0 else 1
print(f"\nPrimer log Emp1 fecha={first_log_fecha} (lunes, ds={log_dt_init.weekday()})")
print(f"  d_diff={d_diff_init}, mat_sem={mat_sem_init}")
print(f"  Configuracion Sem2 Lun: 07:00->15:00 (winner esperado=2)")
print(f"  offset = winner(2) - mat_sem({mat_sem_init}) = {2 - mat_sem_init}")

# Para el 26/04 (domingo) con offset calculado
fecha_26 = datetime.strptime('2026-04-26', '%Y-%m-%d')
d_diff_26 = (fecha_26 - f_asig_dt_init).days
mat_sem_26 = (d_diff_26 // 7) % tot_sems_init + 1 if d_diff_26 >= 0 else 1
offset = 2 - mat_sem_init
sem_real_26 = (mat_sem_26 + offset - 1) % tot_sems_init + 1
print(f"\nPara 26/04 (domingo, ds={fecha_26.weekday()}):")
print(f"  d_diff={d_diff_26}, mat_sem={mat_sem_26}, offset={offset}")
print(f"  sem_real = ({mat_sem_26} + {offset} - 1) % {tot_sems_init} + 1 = {sem_real_26}")
print(f"  Sem{sem_real_26} Domingo (ds=6): LIBRE (correcto!)")

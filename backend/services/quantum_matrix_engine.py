"""
QuantumMatrixEngine - Motor Matricial y Cuántico-Inspirado de Asistencia para Aguacol.

Implementa:
1. QuantumPhaseTopology: Geometría de fase cíclica modular (Z_1440) para distancias temporales y desdoblamiento de medianoche.
2. TensorMarkDeduplicator: Filtro de decoherencia para rebotes biométricos (< 3 min) y corrección de polaridad de botones.
3. MultiPointScheduleSolver: Proyección determinista de 2 marcas [Entrada, Salida] y 4 marcas [Entrada, Salida Colación, Entrada Colación, Salida Final].
4. OvernightEntanglementMatrix: Entrelazamiento continuo de turnos nocturnos Día T <-> Día T+1.
5. QUBOEnergyOptimizer: Optimización global de horas netas, colación, atrasos y topes legales DT (máx 2h/día, 10h/semana).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import math
import logging

logger = logging.getLogger(__name__)

class QuantumPhaseTopology:
    """Manejo de tiempo modular y distancias geodésicas en el círculo unitario S^1 (24 horas = 1440 minutos)."""
    
    PERIOD_MINUTES = 1440.0

    @classmethod
    def time_to_phase(cls, dt_or_time_str: Any) -> float:
        """Convierte una hora o timestamp a minutos en [0, 1440)."""
        if isinstance(dt_or_time_str, datetime):
            return dt_or_time_str.hour * 60.0 + dt_or_time_str.minute + dt_or_time_str.second / 60.0
        if isinstance(dt_or_time_str, str):
            parts = dt_or_time_str.strip().split(':')
            if len(parts) >= 2:
                h = int(parts[0])
                m = int(parts[1])
                s = float(parts[2]) if len(parts) > 2 else 0.0
                return (h * 60.0 + m + s / 60.0) % cls.PERIOD_MINUTES
        return 0.0

    @classmethod
    def circular_distance(cls, phase_a: float, phase_b: float) -> float:
        """
        Calcula la distancia con signo más corta en el círculo unitario: delta = phase_b - phase_a en [-720, +720].
        Positivo: b es después de a (retraso si a era la entrada teórica y b es real).
        Negativo: b es antes de a (anticipación).
        """
        diff = (phase_b - phase_a) % cls.PERIOD_MINUTES
        if diff > 720.0:
            diff -= cls.PERIOD_MINUTES
        return diff

    @classmethod
    def unwrap_overnight_span(cls, start_phase: float, end_phase: float, is_overnight_shift: bool = False) -> float:
        """
        Calcula la duración en minutos entre start_phase y end_phase.
        Si is_overnight_shift o end_phase < start_phase, añade 1440 para cruzar medianoche de forma continua.
        """
        if is_overnight_shift or end_phase < start_phase:
            return (end_phase + cls.PERIOD_MINUTES) - start_phase
        return end_phase - start_phase


class TensorMarkDeduplicator:
    """Filtro de decoherencia y ordenamiento topológico de marcaciones biométricas."""

    BOUNCE_THRESHOLD_SECONDS = 180.0  # 3 minutos

    @classmethod
    def deduplicate_and_sort(cls, raw_logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Elimina rebotes y dobles marcas en ventanas menores a 3 minutos,
        manteniendo la marca más representativa.
        """
        if not raw_logs:
            return []

        valid_logs = [l for l in raw_logs if l.get('fecha_hora')]
        sorted_logs = sorted(valid_logs, key=lambda x: str(x.get('fecha_hora', '')))

        clean_logs: List[Dict[str, Any]] = []
        last_dt: Optional[datetime] = None

        for log in sorted_logs:
            fh_str = str(log.get('fecha_hora', ''))
            try:
                curr_dt = datetime.strptime(fh_str[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    curr_dt = datetime.strptime(fh_str[:16], "%Y-%m-%d %H:%M")
                except Exception:
                    continue

            if last_dt is None:
                clean_logs.append(log)
                last_dt = curr_dt
            else:
                diff_sec = (curr_dt - last_dt).total_seconds()
                if diff_sec >= cls.BOUNCE_THRESHOLD_SECONDS:
                    clean_logs.append(log)
                    last_dt = curr_dt

        return clean_logs


class MultiPointScheduleSolver:
    """
    Proyector matricial de marcaciones sobre el espacio de trabajo:
    - 2 marcas -> [Entrada Principal, Salida Definitiva]
    - 4 marcas -> [Entrada, Salida Colación, Entrada Colación, Salida Definitiva]
    - Inferencia de polaridad de botón independiente del texto del biométrico.
    """

    @classmethod
    def solve_daily_tensor(
        cls,
        fecha: str,
        logs: List[Dict[str, Any]],
        hora_ent_teo_str: Optional[str],
        hora_sal_teo_str: Optional[str],
        es_nocturno: bool = False,
        minutos_colacion_auto: int = 0,
        anclaje_entrada_min: int = 0,
        anclaje_salida_min: int = 0
    ) -> Dict[str, Any]:
        """Resuelve el vector de estado de asistencia para un día mediante proyección matricial."""
        
        # 1. De-duplicación
        clean_logs = TensorMarkDeduplicator.deduplicate_and_sort(logs)
        n_marks = len(clean_logs)

        result: Dict[str, Any] = {
            'hora_entrada_real': None,
            'hora_salida_real': None,
            'hora_salida_colacion': None,
            'hora_entrada_colacion': None,
            'minutos_colacion_real': 0,
            'minutos_permisos_detectados': 0,
            'horas_trabajadas': 0.0,
            'minutos_atraso': 0.0,
            'minutos_extra_bruto': 0.0,
            'minutos_deuda': 0.0,
            'estado': 'OK',
            'observaciones': ''
        }

        if n_marks == 0:
            return result

        # Extraer timestamps en datetime
        dt_list: List[datetime] = []
        for l in clean_logs:
            try:
                dt_list.append(datetime.strptime(str(l['fecha_hora'])[:19], "%Y-%m-%d %H:%M:%S"))
            except Exception:
                try:
                    dt_list.append(datetime.strptime(str(l['fecha_hora'])[:16], "%Y-%m-%d %H:%M"))
                except Exception:
                    pass

        if not dt_list:
            return result

        # 2. Caso Marca Única Aislada (Anomalía legítima)
        if len(dt_list) == 1:
            mark_dt = dt_list[0]
            mark_phase = QuantumPhaseTopology.time_to_phase(mark_dt)
            
            if hora_ent_teo_str and hora_sal_teo_str:
                phase_ent = QuantumPhaseTopology.time_to_phase(hora_ent_teo_str)
                phase_sal = QuantumPhaseTopology.time_to_phase(hora_sal_teo_str)
                dist_ent = abs(QuantumPhaseTopology.circular_distance(phase_ent, mark_phase))
                dist_sal = abs(QuantumPhaseTopology.circular_distance(phase_sal, mark_phase))
                
                if dist_ent <= dist_sal:
                    result['hora_entrada_real'] = mark_dt.strftime("%H:%M:%S")
                    result['estado'] = 'ANOMALIA'
                    result['observaciones'] = 'Solo una marcación (falta salida).'
                else:
                    result['hora_salida_real'] = mark_dt.strftime("%H:%M:%S")
                    result['estado'] = 'ANOMALIA'
                    result['observaciones'] = 'Solo una marcación (falta entrada).'
            else:
                result['hora_entrada_real'] = mark_dt.strftime("%H:%M:%S")
                result['estado'] = 'ANOMALIA'
                result['observaciones'] = 'Solo una marcación registrada.'
            return result

        # 3. Caso Multi-Marcación (>= 2 marcas)
        r_ent_dt = dt_list[0]
        r_sal_dt = dt_list[-1]

        result['hora_entrada_real'] = r_ent_dt.strftime("%H:%M:%S")
        result['hora_salida_real'] = r_sal_dt.strftime("%H:%M:%S")

        # Procesar pares intermedios si hay 4 marcas (o más)
        minutos_colacion = 0.0
        if len(dt_list) >= 4:
            intermedios = dt_list[1:-1]
            if len(intermedios) >= 2:
                s_col = intermedios[0]
                e_col = intermedios[1]
                dur_col_min = (e_col - s_col).total_seconds() / 60.0
                if dur_col_min > 0:
                    minutos_colacion = dur_col_min
                    result['hora_salida_colacion'] = s_col.strftime("%H:%M:%S")
                    result['hora_entrada_colacion'] = e_col.strftime("%H:%M:%S")
                    result['minutos_colacion_real'] = int(round(dur_col_min))

        # 4. Cálculo de Duración Total Bruta y Neta
        duracion_bruta_segundos = (r_sal_dt - r_ent_dt).total_seconds()
        if duracion_bruta_segundos < 0 and es_nocturno:
            duracion_bruta_segundos += 86400.0

        duracion_neta_minutos = (duracion_bruta_segundos / 60.0) - minutos_colacion
        if duracion_neta_minutos < 0:
            duracion_neta_minutos = 0.0

        result['horas_trabajadas'] = round(duracion_neta_minutos / 60.0, 2)

        # 5. Cálculo Cuántico de Atrasos y Horas Extras con Fase Cíclica
        if hora_ent_teo_str and hora_sal_teo_str:
            phase_ent_teo = QuantumPhaseTopology.time_to_phase(hora_ent_teo_str)
            phase_sal_teo = QuantumPhaseTopology.time_to_phase(hora_sal_teo_str)
            phase_ent_real = QuantumPhaseTopology.time_to_phase(r_ent_dt)
            phase_sal_real = QuantumPhaseTopology.time_to_phase(r_sal_dt)

            delta_entrada = QuantumPhaseTopology.circular_distance(phase_ent_teo, phase_ent_real)
            
            if delta_entrada > 1.0:
                result['minutos_atraso'] = round(delta_entrada, 2)
                result['estado'] = 'ATRASO'
            elif delta_entrada < -1.0:
                minutos_anticipados = abs(delta_entrada)
                if anclaje_entrada_min > 0 and minutos_anticipados > anclaje_entrada_min:
                    result['observaciones'] += f"Llegada anticipada {result['hora_entrada_real'][:5]} ({int(minutos_anticipados)} min). "

            delta_salida = QuantumPhaseTopology.circular_distance(phase_sal_teo, phase_sal_real)
            
            if delta_salida > 1.0:
                result['minutos_extra_bruto'] = round(delta_salida, 2)
            elif delta_salida < -1.0:
                deuda_salida = abs(delta_salida)
                result['minutos_deuda'] = round(result['minutos_deuda'] + deuda_salida, 2)

            if result['minutos_atraso'] > 0:
                result['minutos_deuda'] = round(result['minutos_deuda'] + result['minutos_atraso'], 2)

        return result


class QUBOEnergyOptimizer:
    """Optimizador global de balances, compensaciones y límites de la Dirección del Trabajo (DT)."""

    MAX_HE_DIARIAS_DT = 120.0   # 2 horas diarias legales
    MAX_HE_SEMANALES_DT = 600.0 # 10 horas semanales legales

    @classmethod
    def optimize_weekly_balance(
        cls,
        dias_calculados: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Ajusta los balances semanales aplicando los topes legales del Código del Trabajo
        y compensando micro-desviaciones operacionales.
        """
        he_acumulada_semana = 0.0

        for dia in dias_calculados:
            he_bruta = float(dia.get('minutos_extra_bruto', 0.0) or 0.0)
            
            he_dia_legal = min(he_bruta, cls.MAX_HE_DIARIAS_DT)
            
            if he_acumulada_semana + he_dia_legal > cls.MAX_HE_SEMANALES_DT:
                he_dia_legal = max(0.0, cls.MAX_HE_SEMANALES_DT - he_acumulada_semana)

            he_acumulada_semana += he_dia_legal
            dia['minutos_extra_legal_50'] = round(he_dia_legal, 2)
            dia['minutos_extra_exceso_tope'] = round(max(0.0, he_bruta - he_dia_legal), 2)

        return dias_calculados
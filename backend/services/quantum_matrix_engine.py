"""
QuantumMatrixEngine v2.1 - Motor Matricial Cuántico Unificado de Asistencia para Aguacol.

Arquitectura Matemática Integral:
1. DynamicObservationHorizon & PhaseTopology: Geometría de fase cíclica modular (Z_1440) en S^1.
   Horizontes y ventanas temporales determinados dinámicamente a partir de los horarios asignados
   (hora_entrada, hora_salida, cruza_medianoche) y márgenes configurados en UI/DB, sin límites artificiales.
2. TensorMarkDeduplicator & OverrideFilter: Filtro de decoherencia para rebotes (parametrizado por UI/ajustes)
   y máscara de prioridad para [SOBREESCRITURA] manual.
3. MultiMarkResolver & MultiBlockTensorSolver: Particionador tensorial multi-marca (2, 4, 6 o más marcas):
   - Partición en intervalos efectivos de trabajo presencial: sum(S_i - E_i).
   - Discriminación cuántica de pausas intermedias: identificación de colación según target contractual
     y clasificación de permisos intermedios (con/sin goce o detectados en reloj).
   - Segmentación de bloques extras por gaps parametrizados desde la tabla 'ajustes' (Llamados de Emergencia y Jornada Adicional +2).
4. AutoMealOperator: Descuento de colación condicionado al umbral de horas trabajadas y tolerancias de exceso configuradas.
5. FlexibleBolsaDualClassifier: Soporte dual para Bolsa Flexible:
   - Clase A: Con Viajes Largos (horas de manejo/descanso reconocidas, marcas terminales consumidas, estado VIAJE_LARGO).
   - Clase B: Sin Viajes Largos (bolsa local presencial, horas efectivas de reloj, deuda diaria = 0).
6. SpecialWorkdayClassifier: Segregación estricta de JORNADA_ESPECIAL (minutos_extra_bruto = 0).
7. QUBOEnergyOptimizer: Aplicación de topes legales del Código del Trabajo (2h/día, 10h/semana).
"""

from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any, Set
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

    @classmethod
    def is_evening_or_night_shift(
        cls,
        hora_ent_teo_str: Optional[str],
        hora_sal_teo_str: Optional[Any] = None,
        cruza_medianoche: bool = False
    ) -> bool:
        """
        Determina si un turno cruza medianoche basándose estrictamente en su configuración:
        - Flag explícito cruza_medianoche == True.
        - hora_salida < hora_entrada (cuando ambas están definidas).
        - Si solo se define hora_entrada, si empieza tarde en la noche (>= 20:00).
        """
        if isinstance(hora_sal_teo_str, bool):
            cruza_medianoche = hora_sal_teo_str
            hora_sal_teo_str = None

        if cruza_medianoche:
            return True
        if hora_ent_teo_str and hora_sal_teo_str:
            p_in = cls.time_to_phase(hora_ent_teo_str)
            p_out = cls.time_to_phase(hora_sal_teo_str)
            if p_out < p_in:
                return True
            return False
        if hora_ent_teo_str:
            p_in = cls.time_to_phase(hora_ent_teo_str)
            return p_in >= 1200.0
        return False

    @classmethod
    def get_dynamic_observation_horizon(
        cls,
        fecha_str: str,
        hora_ent_teo_str: Optional[str],
        hora_sal_teo_str: Optional[str],
        cruza_medianoche: bool = False,
        anclaje_entrada_minutos: int = 0,
        anclaje_salida_minutos: int = 0,
        ventana_en_curso_minutos: int = 0
    ) -> Tuple[datetime, datetime]:
        """
        Calcula la ventana temporal de observación derivada del horario asignado y los anclajes de UI,
        sin imponer horas fijas arbitrarias en código.
        """
        dt_base = datetime.strptime(fecha_str, "%Y-%m-%d")
        
        # Holgura de entrada
        margen_in = max(120, anclaje_entrada_minutos + 60)
        if hora_ent_teo_str:
            p_in = cls.time_to_phase(hora_ent_teo_str)
            start_dt = dt_base + timedelta(minutes=p_in - margen_in)
        else:
            start_dt = dt_base

        # Holgura de salida
        margen_out = max(180, anclaje_salida_minutos + ventana_en_curso_minutos + 60)
        is_overnight = cls.is_evening_or_night_shift(hora_ent_teo_str, hora_sal_teo_str, cruza_medianoche)

        if hora_sal_teo_str:
            p_out = cls.time_to_phase(hora_sal_teo_str)
            if is_overnight:
                end_dt = dt_base + timedelta(days=1, minutes=p_out + margen_out)
            else:
                end_dt = dt_base + timedelta(minutes=p_out + margen_out)
        else:
            if is_overnight:
                end_dt = dt_base + timedelta(days=1, hours=12)
            else:
                end_dt = dt_base + timedelta(days=1, seconds=-1)

        return start_dt, end_dt


class TensorMarkDeduplicator:
    """Filtro de decoherencia, ordenamiento topológico y máscara de prioridad de sobreescritura."""

    @classmethod
    def deduplicate_and_sort(
        cls,
        raw_logs: List[Dict[str, Any]],
        bounce_seconds: float = 180.0
    ) -> List[Dict[str, Any]]:
        """
        Elimina rebotes biométricos en ventanas menores a bounce_seconds (definido por UI/ajustes),
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
                if diff_sec >= bounce_seconds:
                    clean_logs.append(log)
                    last_dt = curr_dt

        return clean_logs

    @classmethod
    def apply_override_mask(cls, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Si existen marcas manuales con la glosa [SOBREESCRITURA] o corrección humana explícita,
        estas adquieren peso unitario y suprimen marcas biométricas automáticas (manual=0)
        que entran en conflicto o duplican la entrada/salida corregida.
        """
        if not logs:
            return []

        override_logs = [
            l for l in logs 
            if l.get('manual') == 1 and '[SOBREESCRITURA]' in str(l.get('observaciones') or '').upper()
        ]

        if not override_logs:
            return logs

        has_manual_in = any(str(l.get('tipo', '')).strip().lower() in ('entrada', 'entry', 'e', 'in', '1') for l in override_logs)
        has_manual_out = any(str(l.get('tipo', '')).strip().lower() in ('salida', 'exit', 's', 'out', '2') for l in override_logs)

        if has_manual_in and has_manual_out:
            return sorted(override_logs, key=lambda x: str(x.get('fecha_hora', '')))

        filtered: List[Dict[str, Any]] = []
        for l in logs:
            l_tipo = str(l.get('tipo', '')).strip().lower()
            is_e = l_tipo in ('entrada', 'entry', 'e', 'in', '1')
            is_s = l_tipo in ('salida', 'exit', 's', 'out', '2')
            if l.get('manual') == 1:
                filtered.append(l)
            else:
                if is_e and has_manual_in:
                    continue
                if is_s and has_manual_out:
                    continue
                filtered.append(l)

        return sorted(filtered, key=lambda x: str(x.get('fecha_hora', '')))


class MultiBlockTensorSolver:
    """
    Particionador tensorial de bloques de trabajo:
    - Identifica colaciones internas vs. Jornadas Adicionales (+2 / Doble Turno) vs. Llamados de Emergencia.
    - Utiliza gaps configurados desde la tabla 'ajustes' y la interfaz, prohibiendo valores fijos en código.
    """

    @classmethod
    def parse_dt(cls, log_or_dt: Any) -> Optional[datetime]:
        if isinstance(log_or_dt, datetime):
            return log_or_dt
        if isinstance(log_or_dt, dict):
            s = str(log_or_dt.get('fecha_hora', ''))
        else:
            s = str(log_or_dt)
        if not s:
            return None
        try:
            return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
            except Exception:
                return None

    @classmethod
    def segment_blocks(
        cls,
        logs: List[Dict[str, Any]],
        gap_emergencia_horas: float = 4.0,
        limite_jornada_emergencia_horas: float = 3.0,
        bounce_seconds: float = 180.0
    ) -> Dict[str, Any]:
        """
        Segmenta cronológicamente las marcas del día en:
        - bloque_principal: Marcas destinadas al turno regular.
        - bloques_extras: Jornadas adicionales (+2) o emergencias según gap_emergencia_horas configurado.
        """
        result: Dict[str, Any] = {
            'bloque_principal': [],
            'bloques_extras': [],
            'jornada_adicional_minutos': 0,
            'jornada_adicional_obs': '',
            'emergencia_detectada': None,
            'marcas_consumidas_ids': []
        }

        if not logs:
            return result

        clean_logs = TensorMarkDeduplicator.deduplicate_and_sort(logs, bounce_seconds=bounce_seconds)
        clean_logs = TensorMarkDeduplicator.apply_override_mask(clean_logs)

        if not clean_logs:
            return result

        # Manejo de Salida residual en madrugada perteneciente al turno anterior
        primera_marca = clean_logs[0]
        p_tipo = str(primera_marca.get('tipo', '')).strip().lower()
        p_dt = cls.parse_dt(primera_marca)
        is_p_salida = p_tipo in ('salida', 'exit', 's', 'out', '2')

        if is_p_salida and p_dt and p_dt.hour < 6 and len(clean_logs) > 1:
            if primera_marca.get('id'):
                result['marcas_consumidas_ids'].append(primera_marca['id'])
            clean_logs = clean_logs[1:]

        if not clean_logs:
            return result

        bloques: List[List[Dict[str, Any]]] = []
        bloque_actual: List[Dict[str, Any]] = []

        for idx, item in enumerate(clean_logs):
            if idx == 0:
                bloque_actual.append(item)
                continue

            prev_item = clean_logs[idx - 1]
            prev_dt = cls.parse_dt(prev_item)
            curr_dt = cls.parse_dt(item)

            if prev_dt and curr_dt:
                gap_hours = (curr_dt - prev_dt).total_seconds() / 3600.0
                prev_tipo = str(prev_item.get('tipo', '')).strip().lower()
                curr_tipo = str(item.get('tipo', '')).strip().lower()
                is_prev_s = prev_tipo in ('salida', 'exit', 's', 'out', '2')
                is_curr_e = curr_tipo in ('entrada', 'entry', 'e', 'in', '1')

                # Si veníamos de Salida y ahora hay Entrada con brecha >= gap configurado
                if is_prev_s and is_curr_e and gap_hours >= gap_emergencia_horas:
                    bloques.append(bloque_actual)
                    bloque_actual = [item]
                    continue

            bloque_actual.append(item)

        if bloque_actual:
            bloques.append(bloque_actual)

        if not bloques:
            return result

        # El primer bloque es el Bloque Principal ordinario
        result['bloque_principal'] = bloques[0]
        for l in bloques[0]:
            if l.get('id'):
                result['marcas_consumidas_ids'].append(l['id'])

        # Bloques posteriores se evalúan como Jornada Adicional (+2) o Emergencias
        if len(bloques) > 1:
            for extra_blk in bloques[1:]:
                if len(extra_blk) >= 2:
                    ent_dt = cls.parse_dt(extra_blk[0])
                    sal_dt = cls.parse_dt(extra_blk[-1])
                    if ent_dt and sal_dt:
                        dur_min = int(round((sal_dt - ent_dt).total_seconds() / 60.0))
                        dur_hours = dur_min / 60.0

                        for l in extra_blk:
                            if l.get('id'):
                                result['marcas_consumidas_ids'].append(l['id'])

                        ent_str = ent_dt.strftime("%H:%M")
                        sal_str = sal_dt.strftime("%H:%M")

                        if dur_hours < limite_jornada_emergencia_horas:
                            result['emergencia_detectada'] = {
                                'minutos': dur_min,
                                'texto': f"[Llamado de Emergencia: {dur_min} min de {ent_str} a {sal_str}]"
                            }
                        else:
                            result['jornada_adicional_minutos'] += dur_min
                            result['jornada_adicional_obs'] += f"[Jornada Adicional (+2): {ent_str} - {sal_str}] "
                            result['bloques_extras'].append({
                                'hora_entrada': ent_str,
                                'hora_salida': sal_str,
                                'minutos_trabajados': dur_min,
                                'logs': extra_blk
                            })

        return result


# Alias retrocompatible
MultiPointScheduleSolver = MultiBlockTensorSolver


class AutoMealOperator:
    """Operador de colación automática y validación de descansos con umbrales."""

    @classmethod
    def apply_meal_deduction(
        cls,
        horas_brutas: float,
        minutos_colacion_real: float,
        descuento_colacion_auto: bool,
        minutos_colacion_auto: int,
        umbral_horas_colacion: float,
        tolerancia_exceso_minutos: int = 0
    ) -> Tuple[float, int, int]:
        """
        Devuelve: (horas_trabajadas_netas, minutos_colacion_aplicados, minutos_exceso_colacion)
        """
        minutos_colacion_aplicados = 0
        minutos_exceso = 0

        # Caso 1: Hay marcas reales intermedias de colación
        if minutos_colacion_real > 0:
            if descuento_colacion_auto and minutos_colacion_auto > 0:
                minutos_colacion_aplicados = minutos_colacion_auto
                if minutos_colacion_real > minutos_colacion_auto + tolerancia_exceso_minutos:
                    minutos_exceso = int(round(minutos_colacion_real - minutos_colacion_auto))
            else:
                minutos_colacion_aplicados = int(round(minutos_colacion_real))

        # Caso 2: No hay marcas de colación y aplica descuento automático
        elif descuento_colacion_auto and minutos_colacion_auto > 0:
            if umbral_horas_colacion > 0 and horas_brutas < umbral_horas_colacion:
                minutos_colacion_aplicados = 0
            else:
                minutos_colacion_aplicados = minutos_colacion_auto

        horas_netas = max(0.0, horas_brutas - (minutos_colacion_aplicados / 60.0))
        return round(horas_netas, 4), minutos_colacion_aplicados, minutos_exceso


class SpecialWorkdayClassifier:
    """Segregador estricto de Jornadas Especiales (días libres / feriados) vs Horas Extras Ordinarias."""

    @classmethod
    def evaluate(
        cls,
        empleado_id: int,
        fecha: str,
        is_holiday: bool,
        es_libre: bool,
        horas_trabajadas: float,
        hora_entrada_real: Optional[str],
        hora_salida_real: Optional[str],
        has_punches: bool,
        observaciones_previas: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Si es Día Libre o Feriado con asistencia real:
        - Retorna un dict para la tabla 'jornadas_especiales'.
        - Garantiza que en la asistencia regular minutos_extra_bruto sea 0.
        """
        if not (is_holiday or es_libre):
            return None

        if not has_punches or horas_trabajadas <= 0.0:
            return None

        minutos_trabajados = int(round(horas_trabajadas * 60.0))
        tag_origen = "Trabajo en feriado." if is_holiday else "Trabajo en día libre."
        obs = f"{tag_origen} {observaciones_previas}".strip()

        return {
            'empleado_id': empleado_id,
            'fecha': fecha,
            'hora_entrada': hora_entrada_real,
            'hora_salida': hora_salida_real,
            'minutos_trabajados': minutos_trabajados,
            'estado': 'EXTRA',
            'observaciones': obs
        }


class QuantumShiftWeekMatcher:
    """
    Resuelve la semana ganadora de un turno multi-semana (Ciclo Inteligente)
    mediante minimización de distancia de fase circular entre las marcas físicas y
    los bloques teóricos programados.
    """
    @classmethod
    def resolve_winner_week(
        cls,
        empleado_id: int,
        fecha_str: str,
        dt: datetime,
        dia_semana: int,
        logs: List[Dict[str, Any]],
        turnos_dict: Dict[int, Dict[int, Any]],
        total_sems: int,
        semana_inicio_cfg: Optional[int] = None,
        f_asig_ini: Optional[datetime] = None,
        last_matched_sem: Optional[int] = None,
    ) -> int:
        if total_sems <= 1:
            return 1

        # Si hay marcas candidatas para el día (ventana amplia de marcas)
        marcas_cand = [
            l for l in logs
            if l.get('fecha_hora', '')[:10] == fecha_str or
               (l.get('fecha_hora', '')[:10] == (dt + timedelta(days=1)).strftime("%Y-%m-%d") and int(l.get('fecha_hora', '')[11:13] or '99') < 12)
        ]

        if marcas_cand:
            min_phase_dist = float('inf')
            winner_sem = 1

            for sem_idx in range(1, total_sems + 1):
                cfg_sem = turnos_dict.get(sem_idx, {}).get(dia_semana, {})
                if not cfg_sem or cfg_sem.get('es_libre'):
                    continue

                h_ent_str = cfg_sem.get('hora_entrada')
                h_sal_str = cfg_sem.get('hora_salida')

                if not h_ent_str:
                    continue

                p_ent_teo = QuantumPhaseTopology.time_to_phase(h_ent_str)
                p_sal_teo = QuantumPhaseTopology.time_to_phase(h_sal_str) if h_sal_str else None

                dist_tot = 0.0
                eval_count = 0

                _TIPOS_E = {'entrada', 'entry', 'e', 'in', '1'}
                _TIPOS_S = {'salida', 'exit', 's', 'out', '2'}

                # Buscar primera entrada
                ent_m = next((m for m in marcas_cand if str(m.get('tipo', '')).strip().lower() in _TIPOS_E), None)
                if ent_m:
                    dt_m = MultiBlockTensorSolver.parse_dt(ent_m)
                    if dt_m:
                        p_m = QuantumPhaseTopology.time_to_phase(dt_m)
                        d_in = abs(QuantumPhaseTopology.circular_distance(p_ent_teo, p_m))
                        dist_tot += d_in
                        eval_count += 1

                # Buscar última salida
                sal_m = next((m for m in reversed(marcas_cand) if str(m.get('tipo', '')).strip().lower() in _TIPOS_S), None)
                if sal_m and p_sal_teo is not None:
                    dt_s = MultiBlockTensorSolver.parse_dt(sal_m)
                    if dt_s:
                        p_s = QuantumPhaseTopology.time_to_phase(dt_s)
                        d_out = abs(QuantumPhaseTopology.circular_distance(p_sal_teo, p_s))
                        dist_tot += d_out
                        eval_count += 1

                if eval_count > 0:
                    avg_dist = dist_tot / eval_count
                    if avg_dist < min_phase_dist:
                        min_phase_dist = avg_dist
                        winner_sem = sem_idx

            if min_phase_dist < float('inf'):
                return winner_sem

        # Si no hay marcas o no hubo match:
        if last_matched_sem is not None:
            return last_matched_sem

        if semana_inicio_cfg is not None and f_asig_ini:
            monday_dt = dt - timedelta(days=dt.weekday())
            monday_ini = f_asig_ini - timedelta(days=f_asig_ini.weekday())
            semanas_diff = (monday_dt - monday_ini).days // 7
            return ((int(semana_inicio_cfg) - 1 + semanas_diff) % total_sems) + 1

        return 1


class QuantumMatrixEngine:
    """
    Motor Matricial Cuántico Principal v2.1.
    Unifica la resolución multi-marca, dualidad de bolsa flexible y ausencia de umbrales en código.
    """

    @classmethod
    def solve_attendance_day(
        cls,
        fecha: str,
        empleado_id: int,
        logs: List[Dict[str, Any]],
        turno_config: Dict[str, Any],
        dia_config: Optional[Dict[str, Any]],
        is_holiday: bool = False,
        justificaciones: Optional[List[Dict[str, Any]]] = None,
        global_ajustes: Optional[Dict[str, Any]] = None,
        consumidas_previas: Optional[Set[int]] = None,
        viaje_largo_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Resuelve holísticamente el estado de asistencia de un empleado para una fecha dada."""
        
        # 1. Ajustes globales parametrizados (sin números mágicos hardcodeados)
        ajustes = global_ajustes or {}
        gap_emergencia = float(ajustes.get('asistencia_emergencia_gap_horas', 4.0))
        limite_emergencia = float(ajustes.get('asistencia_emergencia_jornada_limite_horas', 3.0))

        # 2. Configuración de turno y día
        t_cfg = turno_config or {}
        d_cfg = dia_config or {}

        tipo_prog = t_cfg.get('tipo_programacion', 'CICLO_INTELIGENTE')
        is_bolsa = (tipo_prog in ('BOLSA_FLEXIBLE', 'FLEXIBLE_BOLSA'))

        tolerancia_alerta = int(t_cfg.get('tolerancia_retraso_alerta', 0) or 0)
        tolerancia_descuento = int(t_cfg.get('tolerancia_retraso_descuento', 0) or 0)
        anclaje_entrada = int(t_cfg.get('anclaje_entrada_minutos', 0) or 0)
        anclaje_salida = int(t_cfg.get('anclaje_salida_minutos', 0) or 0)
        descuento_col_auto = bool(t_cfg.get('descuento_colacion_auto', False))
        minutos_col_auto = int(t_cfg.get('minutos_colacion_auto', 0) or 0)
        umbral_col = float(t_cfg.get('umbral_horas_colacion', 0.0) or 0.0)
        tolerancia_exceso_col = int(t_cfg.get('tolerancia_exceso_colacion_minutos', 0) or 0)
        redondeo_min = int(t_cfg.get('redondeo_minutos', 0) or 0)
        bounce_sec = max(60.0, float(redondeo_min * 60.0)) if redondeo_min > 0 else 180.0

        hora_limite_ficticia = t_cfg.get('hora_limite_ficticia')

        es_libre_dia = bool(d_cfg.get('es_libre', False))
        horas_teoricas = float(d_cfg.get('horas_teoricas', 0.0) or 0.0)
        hora_ent_teo = d_cfg.get('hora_entrada')
        hora_sal_teo = d_cfg.get('hora_salida')
        cruza_med = bool(d_cfg.get('cruza_medianoche', False))

        # Si es feriado o libre, horas teóricas exigibles = 0
        if is_holiday or es_libre_dia:
            horas_teoricas = 0.0

        # Parseo robusto de tiempos teóricos para delimitación de anclajes
        dt_ent_teo = None
        dt_sal_teo = None
        if hora_ent_teo:
            try:
                parts = str(hora_ent_teo).strip().split(':')
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0
                    dt_ent_teo = datetime.strptime(fecha, "%Y-%m-%d").replace(hour=h, minute=m, second=s)
            except Exception:
                pass

        if hora_sal_teo:
            try:
                parts = str(hora_sal_teo).strip().split(':')
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1])
                    s = int(parts[2]) if len(parts) > 2 else 0
                    f_sal = (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d") if cruza_med else fecha
                    dt_sal_teo = datetime.strptime(f_sal, "%Y-%m-%d").replace(hour=h, minute=m, second=s)
                    if dt_ent_teo and dt_sal_teo <= dt_ent_teo:
                        dt_sal_teo += timedelta(days=1)
            except Exception:
                pass

        # ─────────────────────────────────────────────────────────────────────
        # DUALIDAD BOLSA FLEXIBLE: CLASE A (CON VIAJE LARGO ACTIVO)
        # ─────────────────────────────────────────────────────────────────────
        if is_bolsa and viaje_largo_info:
            c_orig = viaje_largo_info.get('ciudad_origen', 'Planta Aguacol')
            c_dest = viaje_largo_info.get('ciudad_destino', '')
            h_man = viaje_largo_info.get('horas_manejo_efectivas', 0.0)
            h_desc = viaje_largo_info.get('horas_descanso', 0.0)
            h_tot = viaje_largo_info.get('horas_reconocidas_totales', 0.0)
            
            vl_entry_id = viaje_largo_info.get('log_entrada_id')
            vl_exit_id = viaje_largo_info.get('log_salida_id')
            m_ids = []
            if vl_entry_id: m_ids.append(vl_entry_id)
            if vl_exit_id: m_ids.append(vl_exit_id)

            obs = f"🚛 VIAJE LARGO ({c_orig} -> {c_dest}): {h_man}h manejo, {h_desc}h descanso."
            return {
                'empleado_id': empleado_id,
                'fecha': fecha,
                'hora_entrada_real': viaje_largo_info.get('hora_entrada_real'),
                'hora_salida_real': viaje_largo_info.get('hora_salida_real'),
                'hora_salida_colacion': None,
                'hora_entrada_colacion': None,
                'hora_inicio_permiso': None,
                'hora_termino_permiso': None,
                'horas_teoricas': 0.0,
                'horas_trabajadas': h_tot,
                'minutos_colacion': 0,
                'minutos_colacion_real': 0,
                'minutos_colacion_auto': 0,
                'minutos_exceso_colacion': 0,
                'minutos_permisos_detectados': 0,
                'minutos_permiso_personal_deuda': 0,
                'minutos_atraso': 0.0,
                'minutos_salida_adelantada': 0.0,
                'minutos_extra_bruto': 0.0,
                'minutos_deuda': 0.0,
                'tiene_atraso': 0,
                'tiene_salida_adelantada': 0,
                'tiene_permiso': 0,
                'alerta_atraso': False,
                'estado': 'VIAJE_LARGO',
                'observaciones': obs,
                'marcas_consumidas_ids': m_ids,
                '_jornada_especial': None,
                '_jornada_adicional': None
            }

        # 3. Filtrar marcas no consumidas por días anteriores
        consumidas_set = set(consumidas_previas or [])
        marcas_no_consumidas = [l for l in logs if l.get('id') not in consumidas_set]

        # 3.1. DYNAMIC OBSERVATION HORIZON & DÍA PREPONDERANTE (BOLSA FLEXIBLE):
        # Delimita la ventana temporal matemática para el turno de esta fecha específica.
        dt_fecha = datetime.strptime(fecha, "%Y-%m-%d")
        ayer_str = (dt_fecha - timedelta(days=1)).strftime("%Y-%m-%d")

        # Regla Día Preponderante (Bolsa Flexible):
        # A) Si ayer hubo una entrada tardía (>= 20:00) no consumida, hoy es el día preponderante
        marca_ayer_nocturna = None
        if is_bolsa:
            for l in marcas_no_consumidas:
                fh = str(l.get('fecha_hora', ''))
                if fh.startswith(ayer_str) and len(fh) >= 16 and fh[11:16] >= "20:00":
                    t_m = str(l.get('tipo', '') or '').strip().lower()
                    if t_m in {'entrada', 'entry', 'e', 'in', '1'}:
                        marca_ayer_nocturna = l
                        break

        # B) Si hoy solo hay una entrada nocturna tardía (>= 20:00) y ninguna marca diurna,
        # se reserva para mañana (día preponderante del chofer)
        marcas_hoy_cand = [l for l in marcas_no_consumidas if str(l.get('fecha_hora', '')).startswith(fecha)]
        marcas_hoy_diurnas = [l for l in marcas_hoy_cand if str(l.get('fecha_hora', ''))[11:16] < "20:00"]
        marcas_hoy_nocturnas = [l for l in marcas_hoy_cand if str(l.get('fecha_hora', ''))[11:16] >= "20:00"]

        postergar_nocturna_hoy = False
        if is_bolsa and not marcas_hoy_diurnas and marcas_hoy_nocturnas and not marca_ayer_nocturna:
            primer_noc = marcas_hoy_nocturnas[0]
            t_m = str(primer_noc.get('tipo', '') or '').strip().lower()
            if t_m in {'entrada', 'entry', 'e', 'in', '1'}:
                postergar_nocturna_hoy = True

        es_nocturno = cruza_med
        if not es_nocturno and hora_ent_teo and hora_sal_teo:
            p_in = QuantumPhaseTopology.time_to_phase(hora_ent_teo)
            p_out = QuantumPhaseTopology.time_to_phase(hora_sal_teo)
            if p_out < p_in:
                es_nocturno = True

        if not is_bolsa and marcas_hoy_cand:
            try:
                primera_fh = str(marcas_hoy_cand[0].get('fecha_hora', ''))
                if len(primera_fh) >= 13 and int(primera_fh[11:13]) >= 18:
                    es_nocturno = True
            except Exception:
                pass

        start_horizon, end_horizon = QuantumPhaseTopology.get_dynamic_observation_horizon(
            fecha_str=fecha,
            hora_ent_teo_str=hora_ent_teo,
            hora_sal_teo_str=hora_sal_teo,
            cruza_medianoche=es_nocturno,
            anclaje_entrada_minutos=anclaje_entrada,
            anclaje_salida_minutos=anclaje_salida,
        )

        if marca_ayer_nocturna:
            dt_ayer_m = datetime.strptime(str(marca_ayer_nocturna['fecha_hora'])[:19], "%Y-%m-%d %H:%M:%S")
            start_horizon = min(start_horizon, dt_ayer_m - timedelta(minutes=60))
            end_horizon = dt_fecha + timedelta(days=1, seconds=-1)
        elif es_nocturno:
            end_horizon = dt_fecha + timedelta(days=1, hours=14)

        marcas_disponibles = []
        if not postergar_nocturna_hoy:
            for l in marcas_no_consumidas:
                fh_str = str(l.get('fecha_hora', ''))[:19]
                try:
                    dt_l = datetime.strptime(fh_str, "%Y-%m-%d %H:%M:%S")
                    if start_horizon <= dt_l <= end_horizon:
                        marcas_disponibles.append(l)
                except Exception:
                    pass

        # 4. Segmentación Multi-Bloque (+2 y Emergencias)
        segment_res = MultiBlockTensorSolver.segment_blocks(
            marcas_disponibles,
            gap_emergencia_horas=gap_emergencia,
            limite_jornada_emergencia_horas=limite_emergencia,
            bounce_seconds=bounce_sec
        )

        bloque_p = segment_res['bloque_principal']
        marcas_consumidas_ids = list(segment_res['marcas_consumidas_ids'])

        # Resultado base
        res: Dict[str, Any] = {
            'hora_entrada_real': None,
            'hora_salida_real': None,
            'hora_salida_colacion': None,
            'hora_entrada_colacion': None,
            'hora_inicio_permiso': None,
            'hora_termino_permiso': None,
            'horas_teoricas': horas_teoricas,
            'horas_trabajadas': 0.0,
            'minutos_colacion': 0,
            'minutos_colacion_real': 0,
            'minutos_colacion_auto': minutos_col_auto if descuento_col_auto else 0,
            'minutos_exceso_colacion': 0,
            'minutos_permisos_detectados': 0,
            'minutos_permiso_personal_deuda': 0,
            'minutos_atraso': 0.0,
            'minutos_salida_adelantada': 0.0,
            'minutos_extra_bruto': 0.0,
            'minutos_deuda': 0.0,
            'tiene_atraso': 0,
            'tiene_salida_adelantada': 0,
            'tiene_permiso': 0,
            'alerta_atraso': False,
            'estado': 'OK',
            'observaciones': '',
            'marcas_consumidas_ids': marcas_consumidas_ids,
            '_jornada_especial': None,
            '_jornada_adicional': None
        }

        if segment_res['jornada_adicional_obs']:
            res['observaciones'] += segment_res['jornada_adicional_obs']
            res['_jornada_adicional'] = {
                'minutos': segment_res['jornada_adicional_minutos'],
                'bloques': segment_res['bloques_extras']
            }
        if segment_res['emergencia_detectada']:
            res['observaciones'] += segment_res['emergencia_detectada']['texto'] + " "

        # Si no hay marcas en el bloque principal
        now_local = datetime.now()
        today_str = now_local.strftime("%Y-%m-%d")

        if not bloque_p:
            if is_holiday:
                res['estado'] = 'FERIADO'
                res['observaciones'] = 'Feriado Nacional (Proyección automática)'
                return res

            # Evaluar justificaciones de día completo (Licencia Médica, Vacaciones, Permisos)
            justs_dia = [
                j for j in (justificaciones or [])
                if j.get('fecha_inicio', '') <= fecha <= j.get('fecha_fin', '')
            ]
            if justs_dia:
                j = justs_dia[0]
                if not j.get('dias_corridos') and es_libre_dia:
                    pass  # Respeta día libre del turno
                else:
                    tipo_nom = (j.get('tipo_nombre') or 'JUSTIFICADO').upper()
                    res['estado'] = tipo_nom
                    res['nomenclatura'] = j.get('tipo_nomenclatura')
                    res['justificacion_id'] = j.get('id')
                    res['observaciones'] = f"Justificación: {tipo_nom}. "
                    res['horas_teoricas'] = 0.0
                    res['horas_trabajadas'] = 0.0
                    res['minutos_deuda'] = 0.0
                    res['minutos_atraso'] = 0.0
                    return res

            if es_libre_dia:
                res['estado'] = 'LIBRE'
                return res

            # Días futuros sin marcas no generan registro
            if fecha > today_str:
                return None

            # Día de hoy sin marcas: evaluar hora límite ficticia o de entrada
            if fecha == today_str:
                if is_bolsa and hora_limite_ficticia:
                    try:
                        limite_dt = datetime.strptime(f"{fecha} {hora_limite_ficticia}", "%Y-%m-%d %H:%M")
                        if now_local < limite_dt:
                            return None
                    except Exception:
                        pass
                elif hora_ent_teo:
                    try:
                        limite_dt = datetime.strptime(f"{fecha} {hora_ent_teo}", "%Y-%m-%d %H:%M") + timedelta(minutes=anclaje_entrada)
                        if now_local < limite_dt:
                            return None
                    except Exception:
                        pass
                else:
                    return None

            # Día hábil sin marcas (día pasado o hoy superada la hora límite sin actividad):
            res['estado'] = 'INASISTENCIA'
            if is_bolsa:
                res['observaciones'] += 'Inasistencia detectada (Bolsa Flexible sin marcas). '
            else:
                res['observaciones'] += 'Inasistencia detectada (Día hábil sin marcas). '
            res['horas_trabajadas'] = 0.0
            res['minutos_deuda'] = 0.0 if is_bolsa else round(horas_teoricas * 60.0, 2)
            return res

        # 5. Extraer timestamps del bloque principal
        dt_list: List[datetime] = []
        for l in bloque_p:
            dt = MultiBlockTensorSolver.parse_dt(l)
            if dt:
                dt_list.append(dt)

        dt_list = sorted(dt_list)
        n_marks = len(dt_list)

        # 6. Caso 1 Marca Aislada (Anomalía o En Curso)
        if n_marks == 1:
            m_dt = dt_list[0]
            m_phase = QuantumPhaseTopology.time_to_phase(m_dt)

            # Evaluar si la jornada sigue en curso hoy
            if fecha == today_str:
                ventana_min = int(t_cfg.get('ventana_en_curso_minutos', 180) or 180)
                sigue_en_curso = True
                if hora_sal_teo:
                    try:
                        dt_sal_teo = datetime.strptime(f"{fecha} {hora_sal_teo}", "%Y-%m-%d %H:%M")
                        if now_local >= dt_sal_teo + timedelta(minutes=ventana_min):
                            sigue_en_curso = False
                    except Exception:
                        pass
                if sigue_en_curso:
                    res['hora_entrada_real'] = m_dt.strftime("%H:%M:%S")
                    res['estado'] = 'EN_CURSO'
                    res['observaciones'] += 'Jornada en curso (falta salida).'
                    return res

            if hora_ent_teo and hora_sal_teo:
                p_ent = QuantumPhaseTopology.time_to_phase(hora_ent_teo)
                p_sal = QuantumPhaseTopology.time_to_phase(hora_sal_teo)
                d_ent = abs(QuantumPhaseTopology.circular_distance(p_ent, m_phase))
                d_sal = abs(QuantumPhaseTopology.circular_distance(p_sal, m_phase))
                if d_ent <= d_sal:
                    res['hora_entrada_real'] = m_dt.strftime("%H:%M:%S")
                    res['estado'] = 'ANOMALIA'
                    res['observaciones'] += 'Solo una marcación (falta salida). '
                else:
                    res['hora_salida_real'] = m_dt.strftime("%H:%M:%S")
                    res['estado'] = 'ANOMALIA'
                    res['observaciones'] += 'Solo una marcación (falta entrada). '
            else:
                res['hora_entrada_real'] = m_dt.strftime("%H:%M:%S")
                res['estado'] = 'ANOMALIA'
                res['observaciones'] += 'Solo una marcación registrada. '
            return res

        # ─────────────────────────────────────────────────────────────────────
        # 7. RESOLUCIÓN MULTI-MARCA (2, 4, 6 o más marcas)
        # ─────────────────────────────────────────────────────────────────────
        r_ent_dt = dt_list[0]
        r_sal_dt = dt_list[-1]

        res['hora_entrada_real'] = r_ent_dt.strftime("%H:%M:%S")
        res['hora_salida_real'] = r_sal_dt.strftime("%H:%M:%S")

        # Partición en pares cronológicos de presencia activa: (E1, S1), (E2, S2), ...
        # Y pausas intermedias: (S1, E2), (S2, E3), ...
        pares_trabajo: List[Tuple[datetime, datetime]] = []
        pausas_intermedias: List[Tuple[datetime, datetime, float]] = []

        if n_marks % 2 == 0:
            for i in range(0, n_marks, 2):
                pares_trabajo.append((dt_list[i], dt_list[i + 1]))
            for i in range(1, n_marks - 1, 2):
                s_int = dt_list[i]
                e_int = dt_list[i + 1]
                dur_min = max(0.0, (e_int - s_int).total_seconds() / 60.0)
                pausas_intermedias.append((s_int, e_int, dur_min))
        else:
            for i in range(0, n_marks - 1, 2):
                pares_trabajo.append((dt_list[i], dt_list[i + 1]))
            for i in range(1, n_marks - 2, 2):
                s_int = dt_list[i]
                e_int = dt_list[i + 1]
                dur_min = max(0.0, (e_int - s_int).total_seconds() / 60.0)
                pausas_intermedias.append((s_int, e_int, dur_min))
            res['observaciones'] += 'Marcaciones con número impar de registros. '

        # Aplicación de anclajes paramétricos de inicio y fin de turno
        if pares_trabajo and dt_ent_teo and dt_sal_teo and horas_teoricas > 0 and not is_holiday and not es_libre_dia:
            # 1. Anclaje de entrada para el primer bloque
            p0_in, p0_out = pares_trabajo[0]
            if p0_in < dt_ent_teo:
                anticip_seg = (dt_ent_teo - p0_in).total_seconds()
                anticip_min = anticip_seg / 60.0
                if anclaje_entrada > 0 and anticip_min <= anclaje_entrada:
                    p0_in = dt_ent_teo
                elif anclaje_entrada == 0 and anticip_seg < 60.0:
                    p0_in = dt_ent_teo

            # 2. Anclaje de salida para el último bloque
            pn_in, pn_out = pares_trabajo[-1]
            if pn_out > dt_sal_teo:
                demora_seg = (pn_out - dt_sal_teo).total_seconds()
                demora_min = demora_seg / 60.0
                if anclaje_salida > 0 and demora_min <= anclaje_salida:
                    pn_out = dt_sal_teo
                elif demora_seg < 60.0:
                    pn_out = dt_sal_teo

            if len(pares_trabajo) == 1:
                pares_trabajo = [(p0_in, pn_out)]
            else:
                pares_trabajo[0] = (p0_in, p0_out)
                pares_trabajo[-1] = (pn_in, pn_out)

        # Suma estricta de tiempo presencial efectivo trabajado
        duracion_bruta_sec = sum(max(0.0, (p[1] - p[0]).total_seconds()) for p in pares_trabajo)
        horas_brutas = max(0.0, duracion_bruta_sec / 3600.0)

        # ─────────────────────────────────────────────────────────────────────
        # 8. DISCRIMINACIÓN DE PAUSAS: COLACIÓN VS PERMISOS
        # ─────────────────────────────────────────────────────────────────────
        minutos_col_real = 0.0
        minutos_permisos_detectados = 0.0

        if pausas_intermedias:
            target_col = float(minutos_col_auto if (descuento_col_auto and minutos_col_auto > 0) else 60.0)
            
            # El intervalo intermedio más cercano a la duración de colación se asigna a colación
            mejor_par_col = min(pausas_intermedias, key=lambda p: abs(p[2] - target_col))
            
            res['hora_salida_colacion'] = mejor_par_col[0].strftime("%H:%M:%S")
            res['hora_entrada_colacion'] = mejor_par_col[1].strftime("%H:%M:%S")
            minutos_col_real = mejor_par_col[2]
            res['minutos_colacion_real'] = int(round(minutos_col_real))

            # Las demás pausas intermedias corresponden a Permisos / Salidas Intermedias
            pausas_permisos = [p for p in pausas_intermedias if p != mejor_par_col]
            if pausas_permisos:
                minutos_permisos_detectados = sum(p[2] for p in pausas_permisos)
                res['minutos_permisos_detectados'] = int(round(minutos_permisos_detectados))
                res['hora_inicio_permiso'] = pausas_permisos[0][0].strftime("%H:%M:%S")
                res['hora_termino_permiso'] = pausas_permisos[-1][1].strftime("%H:%M:%S")
                res['tiene_permiso'] = 1
                res['observaciones'] += f"Permiso intermedio detectado ({int(round(minutos_permisos_detectados))} min). "

        # 9. Operador de Colación
        # Si la colación ya fue marcada físicamente, las horas presenciales brutas ya la excluyen
        if minutos_col_real > 0:
            min_col_ap = int(round(minutos_col_real))
            min_exc_col = 0
            if descuento_col_auto and minutos_col_auto > 0:
                if minutos_col_real > (minutos_col_auto + tolerancia_exceso_col):
                    min_exc_col = int(round(minutos_col_real - minutos_col_auto))
            horas_netas = horas_brutas
        else:
            horas_netas, min_col_ap, min_exc_col = AutoMealOperator.apply_meal_deduction(
                horas_brutas=horas_brutas,
                minutos_colacion_real=0.0,
                descuento_colacion_auto=descuento_col_auto,
                minutos_colacion_auto=minutos_col_auto,
                umbral_horas_colacion=umbral_col,
                tolerancia_exceso_minutos=tolerancia_exceso_col
            )
            if min_col_ap > 0 and not res['hora_salida_colacion']:
                mitad = r_ent_dt + timedelta(seconds=(r_sal_dt - r_ent_dt).total_seconds() / 2.0)
                res['hora_salida_colacion'] = (mitad - timedelta(minutes=min_col_ap / 2.0)).strftime("%H:%M:%S")
                res['hora_entrada_colacion'] = (mitad + timedelta(minutes=min_col_ap / 2.0)).strftime("%H:%M:%S")

        res['horas_trabajadas'] = round(horas_netas, 4)
        res['minutos_colacion'] = min_col_ap
        res['minutos_exceso_colacion'] = min_exc_col

        # ─────────────────────────────────────────────────────────────────────
        # 10. SEGREGACIÓN ESTRICTA DE JORNADA_ESPECIAL
        # ─────────────────────────────────────────────────────────────────────
        if is_holiday or es_libre_dia:
            res['estado'] = 'JORNADA_ESPECIAL'
            res['minutos_extra_bruto'] = 0.0  # REGLA DE ORO: 0 HE ordinarias
            res['minutos_deuda'] = 0.0
            res['tiene_atraso'] = 0
            res['tiene_salida_adelantada'] = 0
            res['minutos_atraso'] = 0.0
            res['minutos_salida_adelantada'] = 0.0

            res['_jornada_especial'] = SpecialWorkdayClassifier.evaluate(
                empleado_id=empleado_id,
                fecha=fecha,
                is_holiday=is_holiday,
                es_libre=es_libre_dia,
                horas_trabajadas=horas_netas,
                hora_entrada_real=res['hora_entrada_real'],
                hora_salida_real=res['hora_salida_real'],
                has_punches=True,
                observaciones_previas=res['observaciones']
            )
            return res

        # ─────────────────────────────────────────────────────────────────────
        # 11. EJE DISCIPLINARIO (Atrasos y Salidas Adelantadas con Anclajes de UI)
        # ─────────────────────────────────────────────────────────────────────
        diff_ent = 0.0
        diff_sal = 0.0

        if hora_ent_teo:
            p_ent_teo = QuantumPhaseTopology.time_to_phase(hora_ent_teo)
            p_ent_real = QuantumPhaseTopology.time_to_phase(r_ent_dt)
            delta_in = QuantumPhaseTopology.circular_distance(p_ent_teo, p_ent_real)

            if delta_in > 1.0:
                diff_ent = delta_in
            elif delta_in < -1.0:
                anticip_in = abs(delta_in)
                if anclaje_entrada > 0 and anticip_in > anclaje_entrada:
                    res['observaciones'] += f"Llegada anticipada {res['hora_entrada_real'][:5]} ({int(anticip_in)} min). "

        if hora_sal_teo:
            p_sal_teo = QuantumPhaseTopology.time_to_phase(hora_sal_teo)
            p_sal_real = QuantumPhaseTopology.time_to_phase(r_sal_dt)
            delta_out = QuantumPhaseTopology.circular_distance(p_sal_real, p_sal_teo)

            if delta_out > 1.0:
                diff_sal = delta_out
            elif delta_out < -1.0:
                extra_out = abs(delta_out)
                if anclaje_salida > 0 and extra_out > anclaje_salida:
                    res['observaciones'] += f"Salida extendida {res['hora_salida_real'][:5]} (+{int(extra_out)} min). "

        if diff_ent > tolerancia_descuento:
            res['minutos_atraso'] = round(diff_ent, 2)
            res['tiene_atraso'] = 1
            res['estado'] = 'ATRASO'
        elif diff_ent > tolerancia_alerta:
            res['alerta_atraso'] = True

        if diff_sal > 0:
            res['minutos_salida_adelantada'] = round(diff_sal, 2)
            res['tiene_salida_adelantada'] = 1
            if res['estado'] == 'OK':
                res['estado'] = 'SALIDA_ADELANTADA'

        # ─────────────────────────────────────────────────────────────────────
        # 12. EJE FINANCIERO: BOLSA FLEXIBLE LOCAL VS TURNOS ORDINARIOS
        # ─────────────────────────────────────────────────────────────────────
        if is_bolsa:
            # Bolsa Local presencial: anula deuda diaria y atraso punitivo diario
            res['minutos_deuda'] = 0.0
            res['minutos_extra_bruto'] = 0.0
            res['minutos_atraso'] = 0.0
            res['minutos_salida_adelantada'] = 0.0
            res['tiene_atraso'] = 0
            res['tiene_salida_adelantada'] = 0
            res['estado'] = 'OK'
        else:
            min_trab = horas_netas * 60.0
            min_teo = horas_teoricas * 60.0

            # Evaluar permisos con goce de sueldo de la tabla justificaciones
            permisos_hora = [j for j in (justificaciones or []) if j.get('tiene_permiso_hora') and j.get('permiso_activo')]
            min_permiso_comp = 0.0
            for p in permisos_hora:
                if not p.get('genera_deuda_horaria', False):
                    h_i = p.get('hora_inicio')
                    h_f = p.get('hora_fin')
                    if h_i and h_f:
                        try:
                            dt_pi = datetime.strptime(f"{fecha} {h_i}", "%Y-%m-%d %H:%M")
                            dt_pf = datetime.strptime(f"{fecha} {h_f}", "%Y-%m-%d %H:%M")
                            min_permiso_comp += (dt_pf - dt_pi).total_seconds() / 60.0
                        except Exception:
                            pass

            diff_extra = min_trab - min_teo
            if diff_extra >= 1.0:
                res['minutos_extra_bruto'] = round(diff_extra, 2)
                res['minutos_deuda'] = 0.0
            else:
                deuda_calculada = max(0.0, min_teo - min_trab - min_permiso_comp)
                res['minutos_deuda'] = round(deuda_calculada, 2)
                res['minutos_extra_bruto'] = 0.0

        return res


class QUBOEnergyOptimizer:
    """Optimizador global de balances, compensaciones y límites de la Dirección del Trabajo (DT)."""

    MAX_HE_DIARIAS_DT = 120.0   # 2 horas diarias legales
    MAX_HE_SEMANALES_DT = 600.0 # 10 horas semanales legales

    @classmethod
    def optimize_weekly_balance(
        cls,
        dias_calculados: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Ajusta los balances semanales aplicando topes legales de horas extras ordinarias."""
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
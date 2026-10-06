import React, { useMemo, useState } from 'react';
import { In, Meter, Skeleton, fmt, hhmm, num } from './ui';

const PAGE = 40;

const norm = (s) =>
  String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');

// Clasificación de cada fila (misma lógica de siempre, ahora tolerante a nulos)
function rowStatus(item) {
  const estado = String(item.estado || '').toUpperCase().trim();
  if (item.hora_entrada_real) return num(item.minutos_atraso) > 0 ? 'ATRASO' : 'OK';
  if (estado === 'INASISTENCIA' || estado.includes('FALTA')) return 'AUSENTE';
  if (estado === 'EN_CURSO') return 'EN_CURSO';
  if (item.hora_entrada_teorica) return 'INASISTENCIA';
  return estado || 'SIN MARCA';
}

const isAusente = (s) => s === 'AUSENTE' || s === 'INASISTENCIA';

// Lo que requiere atención va primero
const SEVERIDAD = { AUSENTE: 0, INASISTENCIA: 0, ATRASO: 1, EN_CURSO: 2, OK: 4 };
const sev = (s) => (s in SEVERIDAD ? SEVERIDAD[s] : 3);

function State({ status }) {
  if (status === 'OK') return <span className="dx-state" data-tone="ok">Puntual</span>;
  if (status === 'ATRASO') return <span className="dx-state" data-tone="warn">Atraso</span>;
  if (isAusente(status)) return <span className="dx-state" data-tone="bad">Ausente</span>;
  if (status === 'EN_CURSO') return <span className="dx-state" data-tone="info">En turno</span>;
  const txt = String(status || 'Sin marca').replace(/_/g, ' ').toLowerCase();
  return <span className="dx-state" data-tone="mute">{txt.charAt(0).toUpperCase() + txt.slice(1)}</span>;
}

function HoySkeleton() {
  return (
    <div aria-busy="true" aria-label="Cargando datos de hoy">
      <div className="dx-hero">
        <div className="dx-panel dx-live"><Skeleton h={18} w="40%" /><Skeleton h={64} w="55%" /><Skeleton h={8} r={99} /><Skeleton h={14} w="70%" /></div>
        <div className="dx-stats">
          {[0, 1, 2].map((i) => <div key={i} className="dx-panel dx-stat"><Skeleton h={14} w="60%" /><Skeleton h={36} w="40%" /></div>)}
        </div>
      </div>
      <div className="dx-panel dx-sec" style={{ padding: 18 }}>
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} h={38} style={{ marginTop: i ? 10 : 0 }} />)}
      </div>
    </div>
  );
}

export default function TabHoy({ pulse, detail, loading }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('todos');
  const [limit, setLimit] = useState(PAGE);

  const rows = useMemo(
    () => (Array.isArray(detail) ? detail : []).map((d) => ({ ...d, _s: rowStatus(d || {}) })),
    [detail]
  );

  const counts = useMemo(() => {
    let presentes = 0, atrasos = 0, ausentes = 0;
    rows.forEach((r) => {
      if (r.hora_entrada_real) presentes += 1;
      if (r._s === 'ATRASO') atrasos += 1;
      if (!r.hora_entrada_real && isAusente(r._s)) ausentes += 1;
    });
    return { todos: rows.length, presentes, atrasos, ausentes };
  }, [rows]);

  const visible = useMemo(() => {
    const q = norm(query);
    return rows
      .filter((r) => {
        if (q && !norm(r.empleado).includes(q)) return false;
        if (filter === 'presentes') return !!r.hora_entrada_real;
        if (filter === 'atrasos') return r._s === 'ATRASO';
        if (filter === 'ausentes') return !r.hora_entrada_real && isAusente(r._s);
        return true;
      })
      .map((r, i) => ({ r, i }))
      .sort((a, b) => sev(a.r._s) - sev(b.r._s) || a.i - b.i)
      .map((x) => x.r);
  }, [rows, query, filter]);

  if (loading && !pulse) return <HoySkeleton />;

  const tasa = num(pulse && pulse.tasa_asistencia);
  const presentes = num(pulse && pulse.presentes);
  const esperados = num(pulse && pulse.esperados);
  const turno = (pulse && pulse.turno_actual) || '';

  const CHIPS = [
    ['todos', 'Todos', counts.todos],
    ['presentes', 'Presentes', counts.presentes],
    ['atrasos', 'Atrasos', counts.atrasos],
    ['ausentes', 'Ausentes', counts.ausentes],
  ];

  const shown = visible.slice(0, limit);

  return (
    <div>
      <div className="dx-hero">
        <In i={0} className="dx-panel dx-live">
          <div className="dx-live-top">
            <span className="dx-livetag"><span className="dx-dot" aria-hidden="true" /> En vivo</span>
            {turno && turno !== 'N/A' && <span className="dx-tag" data-tone="mute">Turno {turno}</span>}
          </div>
          <div>
            <div className="dx-big">{fmt(tasa, 1)}<small>%</small></div>
            <p style={{ marginTop: 6 }}>Asistencia sobre el personal esperado</p>
          </div>
          <div>
            <Meter value={tasa} />
            <p style={{ marginTop: 10 }}><b>{fmt(presentes)}</b> presentes de <b>{fmt(esperados)}</b> esperados</p>
          </div>
        </In>

        <div className="dx-stats">
          <In i={1} className="dx-panel dx-stat">
            <div className="dx-stat-label"><span className="dx-mark" data-tone="warn" />Atrasos</div>
            <div className="dx-stat-num">{fmt(pulse && pulse.atrasos)}</div>
            <div className="dx-stat-hint">Ingresaron fuera de horario</div>
          </In>
          <In i={2} className="dx-panel dx-stat">
            <div className="dx-stat-label"><span className="dx-mark" data-tone="bad" />Ausentes</div>
            <div className="dx-stat-num">{fmt(counts.ausentes)}</div>
            <div className="dx-stat-hint">Sin marca y sin justificación</div>
          </In>
          <In i={3} className="dx-panel dx-stat">
            <div className="dx-stat-label"><span className="dx-mark" data-tone="info" />En curso</div>
            <div className="dx-stat-num">{fmt(pulse && pulse.alertas_en_curso)}</div>
            <div className="dx-stat-hint">Turnos iniciados, pendientes de cierre</div>
          </In>
        </div>
      </div>

      <In i={4} className="dx-panel dx-sec" style={{ padding: 0 }}>
        <div className="dx-roster-head">
          <div className="dx-roster-title">
            <h2 className="dx-sec-title">Dotación de hoy</h2>
            <span className="dx-sec-sub">{fmt(visible.length)} de {fmt(rows.length)}</span>
          </div>
          <div className="dx-chips" role="group" aria-label="Filtrar por estado">
            {CHIPS.map(([key, label, n]) => (
              <button
                key={key}
                type="button"
                className="dx-chip"
                aria-pressed={filter === key}
                onClick={() => { setFilter(key); setLimit(PAGE); }}
              >
                {label} <em>{fmt(n)}</em>
              </button>
            ))}
          </div>
          <label className="dx-search">
            <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Buscar colaborador por nombre</span>
            <i className="bi bi-search" aria-hidden="true" />
            <input
              id="tabhoy-search-input"
              className="dx-input"
              type="search"
              inputMode="search"
              autoComplete="off"
              placeholder="Buscar colaborador"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }}
            />
          </label>
        </div>

        <div className="dx-cols" aria-hidden="true">
          <span>Colaborador</span><span>Área</span>
          <span className="dx-num">Horario</span><span className="dx-num">Entrada</span><span className="dx-num">Atraso</span>
          <span className="dx-end">Estado</span>
        </div>

        <div role="list">
          {shown.map((r, idx) => {
            const atraso = r.hora_entrada_real && num(r.minutos_atraso) > 0 ? `+${fmt(r.minutos_atraso)} min` : '';
            return (
              <div className="dx-row" role="listitem" key={`${r.empleado || 'x'}-${idx}`}>
                <span className="dx-name" title={r.empleado || ''}>{r.empleado || 'Sin nombre'}</span>
                <span className="dx-muted dx-hide-sm">{r.area || '–'}</span>
                <span className="dx-num dx-hide-sm">{hhmm(r.hora_entrada_teorica)}</span>
                <span className="dx-num dx-hide-sm">{hhmm(r.hora_entrada_real)}</span>
                <span className={`dx-num dx-hide-sm ${atraso ? 'dx-late' : ''}`}>{atraso || '–'}</span>
                <State status={r._s} />
                <span className="dx-meta">
                  {r.area || 'Sin área'} · Horario <b>{hhmm(r.hora_entrada_teorica)}</b> · Entrada <b>{hhmm(r.hora_entrada_real)}</b>
                  {atraso ? <> · <b style={{ color: 'var(--dx-warn)' }}>{atraso}</b></> : null}
                </span>
              </div>
            );
          })}
        </div>

        {visible.length === 0 && (
          <div className="dx-empty">
            <b>{rows.length === 0 ? 'Sin datos para hoy' : 'Nadie coincide con el filtro'}</b>
            {rows.length === 0 ? 'Aún no hay turnos programados para esta área.' : 'Prueba con otro estado o borra la búsqueda.'}
          </div>
        )}

        {visible.length > shown.length && (
          <div className="dx-more">
            <button type="button" className="dx-btn dx-ghost" onClick={() => setLimit((l) => l + PAGE)}>
              Mostrar {Math.min(PAGE, visible.length - shown.length)} más
            </button>
          </div>
        )}
      </In>
    </div>
  );
}

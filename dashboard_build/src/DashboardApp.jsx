import React, { useState, useEffect, useCallback, useRef } from 'react';
import { DP_CSS } from './styles';
import { ErrorBoundary, Skeleton, num, fmt, pct, plural, fechaCorta, diasHasta } from './ui';
import Indicadores, { PanelDetalle } from './Indicadores';

const API_BASE_URL = '/api';

// Inyecta los estilos una sola vez (el bundle es un único .js, no hay hoja aparte)
function useDashboardStyles() {
  useEffect(() => {
    if (document.getElementById('dp-styles')) return;
    const el = document.createElement('style');
    el.id = 'dp-styles';
    el.textContent = DP_CSS;
    document.head.appendChild(el);
  }, []);
}

const TONO = { cerrado: 'ok', listo: 'ready', pendiente: 'warn' };
const COLOR_TONO = { ok: 'var(--dp-ok)', ready: 'var(--dp-blue)', warn: 'var(--dp-warn)' };
const ORDEN = { listo: 0, pendiente: 1, cerrado: 2 };

const ddmm = (iso) => { const s = String(iso || ''); return s.length >= 10 ? `${s.slice(8, 10)}-${s.slice(5, 7)}` : s; };
const mesCorto = (mes) => String(mes || '').split(' ')[0].toLowerCase();
const hhmm = (s) => String(s || '').slice(11, 16);

// Las acciones llevan a la pantalla donde se hace el trabajo (Marcaciones o Empleados): el Dashboard no cambia nada.
function irAMarcaciones(opts) {
  if (typeof window.abrirMarcacionesDesde === 'function') window.abrirMarcacionesDesde(opts);
  else if (typeof window.switchPage === 'function') window.switchPage('marcaciones');
}
function verContratos() {
  if (typeof window.switchPage === 'function') window.switchPage('empleados');
  setTimeout(() => { const t = document.getElementById('contratos-tab'); if (t) t.click(); }, 300);
}

// Qué le falta a un área para cerrar el tramo y qué botón la resuelve
function lecturaArea(a, tramo, hoy) {
  if (a.estado === 'cerrado') {
    const c = a.cerrado || {};
    const dia = String(c.fecha || '').slice(0, 10);
    const cuando = dia === hoy ? `Hoy a las ${hhmm(c.fecha)}` : `El ${ddmm(dia)} a las ${hhmm(c.fecha)}`;
    return { chip: 'Cerrado', por: `${cuando}${c.por ? `, por ${c.por}` : ''}`, accion: null };
  }
  const aceptar = a.inasistencias ? `${plural(a.inasistencias, 'falta sin aviso', 'faltas sin aviso')} por aceptar al cerrar` : '';
  if (a.estado === 'listo') {
    return {
      chip: 'Lista para cerrar',
      por: aceptar || 'Sin horas extra por decidir ni días por revisar',
      accion: { label: `Cerrar ${mesCorto(tramo.mes)}`, op: 'cierre', pr: true },
    };
  }
  const partes = [];
  if (a.libreta_dias) partes.push(`${plural(a.libreta_dias, 'día', 'días')} de libreta sin registrar (${plural(a.libreta_personas, 'chofer', 'choferes')})`);
  if (a.por_revisar) partes.push(`${plural(a.por_revisar, 'día', 'días')} por revisar (${a.fechas_por_revisar.map(ddmm).join(', ')})`);
  if (a.he_pendientes) partes.push(`${plural(a.he_pendientes, 'solicitud', 'solicitudes')} de horas extra por decidir (${fmt(a.he_horas, 1)} h)`);
  if (a.anomalias) partes.push(`${plural(a.anomalias, 'día', 'días')} con anomalía`);
  if (a.otros_pendientes) partes.push(`${plural(a.otros_pendientes, 'día', 'días')} sin calcular`);
  if (a.en_curso) partes.push(`${plural(a.en_curso, 'jornada', 'jornadas')} en curso`);
  if (aceptar) partes.push(aceptar);
  let chip = 'Con pendientes';
  let accion = { label: 'Ver en la grilla', op: 'grilla' };
  if (a.libreta_dias) { chip = `Faltan ${plural(a.libreta_dias, 'día', 'días')} de libreta`; accion = { label: 'Ir a libretas', op: 'libreta' }; }
  else if (a.por_revisar) { chip = `Falta revisar ${plural(a.por_revisar, 'día', 'días')}`; accion = { label: 'Revisar días', op: 'revisar' }; }
  else if (a.he_pendientes) { chip = 'Faltan horas extra por decidir'; accion = { label: 'Decidir horas extra', op: 'he' }; }
  else if (a.anomalias) { chip = `${plural(a.anomalias, 'día', 'días')} con anomalía`; }
  return { chip, por: partes.join(' · '), accion };
}

function Card({ title, sub, children, className = '' }) {
  return (
    <section className={`dp-card ${className}`}>
      <div className="dp-card-head">
        <h2>{title}</h2>
        {sub ? <span className="dp-card-sub">{sub}</span> : null}
      </div>
      {children}
    </section>
  );
}

function CierreTramo({ tramo, hoy }) {
  const areas = [...tramo.areas].sort((x, y) => ORDEN[x.estado] - ORDEN[y.estado] || x.area.localeCompare(y.area, 'es'));
  const n = (e) => areas.filter((a) => a.estado === e).length;
  const resumen = [
    n('cerrado') ? plural(n('cerrado'), 'cerrada', 'cerradas') : null,
    n('listo') ? plural(n('listo'), 'lista', 'listas') : null,
    n('pendiente') ? `${fmt(n('pendiente'))} con pendientes` : null,
  ].filter(Boolean).join(' · ');
  const SEG = { cerrado: 0, listo: 1, pendiente: 2 };
  const segs = [...tramo.areas].sort((x, y) => SEG[x.estado] - SEG[y.estado]);
  return (
    <Card title={`Cierre de ${tramo.mes}`} sub={`El tramo terminó el ${ddmm(tramo.fecha_fin)}`}>
      <div className="dp-segs" aria-hidden="true">
        {segs.map((a) => <span key={a.area} style={{ background: COLOR_TONO[TONO[a.estado]] }} />)}
      </div>
      <div className="dp-legend-line">{resumen}</div>
      <div className="dp-close-list">
        {areas.map((a) => {
          const l = lecturaArea(a, tramo, hoy);
          return (
            <div className="dp-close-row" key={a.area}>
              <div className="dp-close-area">{a.area}</div>
              <span className="dp-chip" data-tone={TONO[a.estado]}>{l.chip}</span>
              <div className="dp-close-why">{l.por}</div>
              {l.accion ? (
                <button
                  type="button"
                  className={`dp-btn ${l.accion.pr ? 'dp-pr' : ''}`}
                  onClick={() => irAMarcaciones({ area: a.area, desde: tramo.fecha_inicio, hasta: tramo.fecha_fin, accion: l.accion.op })}
                >
                  {l.accion.label}
                </button>
              ) : <span />}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function HorasExtra({ he, tramo }) {
  const max = Math.max(0.0001, ...he.por_area.map((x) => num(x.horas)));
  const meses = he.por_tramo.map((t) => mesCorto(t.mes)).map((m) => m.charAt(0).toUpperCase() + m.slice(1)).join(' y ');
  const sub = he.solicitudes ? `${meses} · ${plural(he.solicitudes, 'solicitud', 'solicitudes')} · ${fmt(he.horas, 1)} h` : '';
  return (
    <Card title="Horas extra por decidir" sub={sub}>
      {he.solicitudes === 0 ? (
        <div className="dp-empty">No hay horas extra por decidir.</div>
      ) : (
        <>
          <div style={{ marginTop: 8 }}>
            {he.por_area.map((x) => (
              <div className="dp-bar-row" key={x.area}>
                <span>{x.area}</span>
                <div className="dp-track"><span style={{ width: `${(num(x.horas) / max) * 100}%` }} /></div>
                <span className="dp-num" style={{ fontSize: 14 }}>{fmt(x.solicitudes)} · {fmt(x.horas, 1)} h</span>
              </div>
            ))}
          </div>
          {tramo ? (
            <div className="dp-foot">
              <button type="button" className="dp-btn" onClick={() => irAMarcaciones({ area: '', desde: tramo.fecha_inicio, hasta: tramo.fecha_fin, accion: 'he' })}>
                Decidir horas extra
              </button>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function Contratos({ c, hoy }) {
  const conDecision = c.total + c.vencidos - c.sin_decision;
  const sub = c.total + c.vencidos === 0 ? '' : `${fmt(c.total)} en ${fmt(c.dias)} días · ${conDecision === 0 ? 'ninguno con decisión' : `${plural(c.sin_decision, 'sin decisión', 'sin decisión')}`}`;
  return (
    <Card title="Contratos por vencer" sub={sub}>
      {c.total + c.vencidos === 0 ? (
        <div className="dp-empty">Ningún contrato vence en los próximos {fmt(c.dias)} días.</div>
      ) : (
        <>
          <div className="dp-list">
            {c.vencidos ? (
              <div className="dp-list-row">
                <span className="dp-grow dp-soon">Ya vencieron y siguen activos</span>
                <span className="dp-num dp-soon">{fmt(c.vencidos)}</span>
              </div>
            ) : null}
            {c.por_fecha.map((f) => {
              const d = diasHasta(f.fecha, hoy);
              return (
                <div className="dp-list-row" key={f.fecha}>
                  <span className="dp-num" style={{ width: 96, fontWeight: 500 }}>{fechaCorta(f.fecha)}</span>
                  <span className="dp-grow">{plural(f.total, 'contrato', 'contratos')}</span>
                  <span className={`dp-when ${d !== null && d <= 7 ? 'dp-soon' : ''}`}>{d === 0 ? 'hoy' : d === 1 ? 'mañana' : `en ${fmt(d)} días`}</span>
                </div>
              );
            })}
          </div>
          <div className="dp-foot"><button type="button" className="dp-btn" onClick={verContratos}>Ver contratos</button></div>
        </>
      )}
    </Card>
  );
}

function Hoy({ filas, total, fecha, tramo }) {
  const [abierto, setAbierto] = useState(false);
  const largo = (() => {
    const [y, m, d] = String(fecha || '').split('-').map(Number);
    if (!y) return '';
    return new Date(y, m - 1, d).toLocaleDateString('es-CL', { weekday: 'long', day: '2-digit', month: '2-digit' }).replace(/\//g, '-');
  })();
  const resto = [
    total.aun_no_marcan ? `${fmt(total.aun_no_marcan)} aún no marcan` : null,
    total.libreta_por_registrar ? `${plural(total.libreta_por_registrar, 'chofer', 'choferes')} con libreta por registrar` : null,
    total.justificados ? `${fmt(total.justificados)} con licencia, vacaciones o permiso` : null,
    total.en_dia_libre ? `${fmt(total.en_dia_libre)} trabajando en día libre` : null,
  ].filter(Boolean).join(' · ');
  return (
    <Card title="Hoy" sub={largo} className="dp-a-hoy">
      <div className="dp-today-total" style={{ marginTop: 8 }}>
        <b className="dp-num">{fmt(total.llegaron)}</b> de <span className="dp-num">{fmt(total.con_reloj)}</span> marcaron
        {total.con_atraso ? <> · <span style={{ color: '#a35f00' }}>{plural(total.con_atraso, 'con atraso', 'con atraso')}</span></> : null}
        {total.faltan ? <> · <b style={{ color: '#b3352b' }}>{plural(total.faltan, 'faltó sin aviso', 'faltaron sin aviso')}</b></> : null}
      </div>
      {resto ? <div className="dp-today-note" style={{ fontSize: 13 }}>{resto}</div> : null}
      <div className="dp-stack dp-solo-movil" aria-hidden="true">
        {total.llegaron - total.con_atraso > 0 ? <span style={{ width: `${((total.llegaron - total.con_atraso) / Math.max(1, total.con_reloj)) * 100}%`, background: 'var(--dp-ok)' }} /> : null}
        {total.con_atraso ? <span style={{ width: `${(total.con_atraso / Math.max(1, total.con_reloj)) * 100}%`, background: 'var(--dp-warn)' }} /> : null}
        {total.faltan ? <span style={{ width: `${(total.faltan / Math.max(1, total.con_reloj)) * 100}%`, background: 'var(--dp-bad)' }} /> : null}
      </div>
      <button type="button" className="dp-btn dp-solo-movil" style={{ marginTop: 10 }} aria-expanded={abierto} onClick={() => setAbierto((v) => !v)}>
        {abierto ? 'Ocultar áreas' : 'Ver por área'} <i className={`bi bi-chevron-${abierto ? 'up' : 'down'}`} aria-hidden="true" />
      </button>
      <div className={`dp-hoy-areas ${abierto ? 'dp-open' : ''}`} style={{ marginTop: 10 }}>
        {filas.length === 0 ? <div className="dp-empty">Hoy no hay personas con horario en estas áreas.</div> : filas.map((r) => {
          const aTiempo = Math.max(0, r.llegaron - r.con_atraso);
          const base = Math.max(1, r.con_reloj);
          const nota = [
            r.libreta_por_registrar ? `${fmt(r.libreta_por_registrar)} libreta` : null,
            r.justificados ? `${fmt(r.justificados)} licencia o permiso` : null,
            r.aun_no_marcan ? `${fmt(r.aun_no_marcan)} aún no marca${r.aun_no_marcan === 1 ? '' : 'n'}` : null,
            r.en_turno ? `${fmt(r.en_turno)} en turno` : null,
          ].filter(Boolean).join(' · ');
          return (
            <button
              type="button"
              className="dp-today-row"
              key={r.area}
              onClick={() => tramo && irAMarcaciones({ area: r.area, desde: tramo.fecha_inicio, hasta: tramo.fecha_fin, accion: 'grilla' })}
              aria-label={`${r.area}: ${r.llegaron} de ${r.con_reloj} marcaron, ${r.con_atraso} con atraso, ${r.faltan} faltan. Abrir en Marcaciones`}
            >
              <div className="dp-today-top"><span>{r.area}</span><span className="dp-num" style={{ fontSize: 14 }}>{fmt(r.llegaron)} de {fmt(r.con_reloj)}</span></div>
              <div className="dp-stack" aria-hidden="true">
                {aTiempo ? <span style={{ width: `${(aTiempo / base) * 100}%`, background: 'var(--dp-ok)' }} /> : null}
                {r.con_atraso ? <span style={{ width: `${(r.con_atraso / base) * 100}%`, background: 'var(--dp-warn)' }} /> : null}
                {r.faltan ? <span style={{ width: `${(r.faltan / base) * 100}%`, background: 'var(--dp-bad)' }} /> : null}
              </div>
              {nota ? <div className="dp-today-note">{nota}</div> : null}
            </button>
          );
        })}
      </div>
      <div className="dp-keys" aria-hidden="true">
        <span><i style={{ background: 'var(--dp-ok)' }} />a la hora</span>
        <span><i style={{ background: 'var(--dp-warn)' }} />con atraso</span>
        <span><i style={{ background: 'var(--dp-bad)' }} />faltó sin aviso</span>
      </div>
    </Card>
  );
}

function TramoPorArea({ t }) {
  if (!t || !t.mes || !t.areas.length) return null;
  return (
    <Card title={`${t.mes} por área`} sub="asistencia · días con atraso" className="dp-a-tramo">
      <table className="dp-table">
        <thead><tr><th>Área</th><th>Asistencia</th><th>Días con atraso</th></tr></thead>
        <tbody>
          {t.areas.map((a) => (
            <tr key={a.area}>
              <td>{a.area}</td>
              <td className="dp-num">{pct(a.asistencia_pct)}</td>
              <td className="dp-num dp-high">{pct(a.dias_con_atraso_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Cargando() {
  return (
    <div className="dp-layout" aria-busy="true" aria-label="Cargando el dashboard">
      <div className="dp-a-main" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div className="dp-card"><Skeleton h={22} w="40%" /><Skeleton h={8} style={{ marginTop: 14 }} />{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} h={34} style={{ marginTop: 12 }} />)}</div>
      </div>
      <div className="dp-a-hoy dp-card"><Skeleton h={22} w="30%" />{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} h={28} style={{ marginTop: 12 }} />)}</div>
    </div>
  );
}

function Dashboard() {
  useDashboardStyles();
  const [area, setArea] = useState('Todas');
  const [areas, setAreas] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const reqId = useRef(0);
  // Pestaña elegida: se recuerda en este navegador (si el almacenamiento falla, abre «Lo que falta hacer»)
  const [vista, setVista] = useState(() => {
    try { return localStorage.getItem('dashboard_vista') === 'indicadores' ? 'indicadores' : 'pendientes'; } catch (e) { return 'pendientes'; }
  });
  const [tramoId, setTramoId] = useState('');
  const [ind, setInd] = useState(null);
  const [indLoading, setIndLoading] = useState(false);
  const [indError, setIndError] = useState(null);
  const indReq = useRef(0);
  const [detalleDe, setDetalleDe] = useState(null);
  const elegirVista = (v) => {
    setVista(v);
    try { localStorage.setItem('dashboard_vista', v); } catch (e) { /* sin almacenamiento: solo esta vez */ }
  };

  const headers = useCallback(() => {
    const token = localStorage.getItem('access_token');
    return { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        if (!localStorage.getItem('access_token')) return;
        const res = await fetch(`${API_BASE_URL}/empleados/stats/`, { headers: headers() });
        if (res.ok) {
          const stats = await res.json();
          setAreas(Array.isArray(stats && stats.areas) ? stats.areas.map((a) => a.area).filter(Boolean) : []);
        }
      } catch (err) {
        console.error('Dashboard: no se pudieron leer las áreas:', err);
      }
    })();
  }, [headers]);

  const cargar = useCallback(async () => {
    const mine = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const q = area !== 'Todas' ? `?area=${encodeURIComponent(area)}` : '';
      const res = await fetch(`${API_BASE_URL}/dashboard/pendientes/${q}`, { headers: headers() });
      if (!res.ok) throw new Error('No se pudo leer lo pendiente. Reintente en un momento.');
      const json = await res.json();
      if (mine !== reqId.current) return;
      setData((json && json.data) || null);
    } catch (err) {
      if (mine === reqId.current) setError(err.message);
    } finally {
      if (mine === reqId.current) setLoading(false);
    }
  }, [area, headers]);

  const cargarIndicadores = useCallback(async () => {
    const mine = ++indReq.current;
    setIndLoading(true);
    setIndError(null);
    try {
      const q = new URLSearchParams();
      if (area !== 'Todas') q.set('area', area);
      if (tramoId) q.set('tramo', tramoId);
      const res = await fetch(`${API_BASE_URL}/dashboard/indicadores/${q.toString() ? `?${q}` : ''}`, { headers: headers() });
      if (!res.ok) throw new Error('No se pudieron calcular los indicadores. Reintente en un momento.');
      const json = await res.json();
      if (mine !== indReq.current) return;
      setInd((json && json.data) || null);
    } catch (err) {
      if (mine === indReq.current) setIndError(err.message);
    } finally {
      if (mine === indReq.current) setIndLoading(false);
    }
  }, [area, tramoId, headers]);

  useEffect(() => { if (vista === 'pendientes') cargar(); }, [cargar, vista]);
  useEffect(() => { if (vista === 'indicadores') cargarIndicadores(); }, [cargarIndicadores, vista]);

  const pedirDetalle = useCallback(async (id, tramo) => {
    const q = new URLSearchParams({ indicador: id });
    if (area !== 'Todas') q.set('area', area);
    if (tramo) q.set('tramo', tramo);
    const res = await fetch(`${API_BASE_URL}/dashboard/indicadores/detalle/?${q}`, { headers: headers() });
    if (!res.ok) throw new Error('No se pudo armar el detalle. Reintente en un momento.');
    const json = await res.json();
    return json && json.data;
  }, [area, headers]);

  const verDetalle = (i) => setDetalleDe(i);
  const cerrarDetalle = useCallback(() => setDetalleDe(null), []);
  const irAGrilla = (i) => {
    setDetalleDe(null);
    const t = ind && ind.tramo;
    if (i.accion === 'empleados') { if (typeof window.switchPage === 'function') window.switchPage('empleados'); return; }
    const zona = (i.donde && i.donde[0] && i.donde[0].area) || (area !== 'Todas' ? area : '');
    irAMarcaciones({ area: zona, desde: t ? t.fecha_inicio : '', hasta: t ? t.fecha_fin : '', accion: i.accion === 'he' ? 'he' : 'grilla' });
  };
  const esInd = vista === 'indicadores';
  const ocupado = esInd ? indLoading : loading;
  const actualizar = esInd ? cargarIndicadores : cargar;

  const d = data;
  const tramoActual = d && d.tramo_en_curso;
  const tramoHE = d && (tramoActual || (d.tramos_por_cerrar && d.tramos_por_cerrar[0]));
  const je = d ? d.jornadas_por_validar : null;

  return (
    <div className="dp">
      <div className="dp-top">
        <div className="dp-tabs" role="tablist" aria-label="Vista del dashboard">
          <button type="button" role="tab" aria-selected={!esInd} onClick={() => elegirVista('pendientes')}>Lo que falta hacer</button>
          <button type="button" role="tab" aria-selected={esInd} onClick={() => elegirVista('indicadores')}>Indicadores</button>
        </div>
        <div className="dp-tools">
          <select className="dp-select" aria-label="Área" value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="Todas">Todas las áreas</option>
            {areas.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          {esInd && ind && Array.isArray(ind.tramos) && ind.tramos.length ? (
            <select className="dp-select" aria-label="Tramo" value={tramoId || (ind.tramo ? String(ind.tramo.id) : '')} onChange={(e) => setTramoId(e.target.value)}>
              {[...ind.tramos].reverse().map((t) => <option key={t.id} value={String(t.id)}>{t.mes}{t.en_curso ? ' (en curso)' : ''}</option>)}
            </select>
          ) : null}
          {!esInd && d ? <span className="dp-stamp dp-num">{fechaCorta(d.hoy)} · {String(d.generado || '').slice(11, 16)}</span> : null}
          <button type="button" className="dp-btn" onClick={actualizar} aria-label="Actualizar el dashboard">
            <i className={`bi bi-arrow-clockwise ${ocupado ? 'dp-spin' : ''}`} aria-hidden="true" /> <span className="dp-btn-txt">Actualizar</span>
          </button>
        </div>
      </div>

      {esInd ? (
        <>
          {indError ? (
            <div className="dp-alert" role="alert">
              <i className="bi bi-exclamation-triangle-fill" aria-hidden="true" />
              <div style={{ flex: 1 }}><b>No se pudo actualizar.</b> {indError}</div>
              <button type="button" className="dp-btn" onClick={cargarIndicadores}>Reintentar</button>
            </div>
          ) : null}
          {ind ? <Indicadores data={ind} onDetalle={verDetalle} /> : (indLoading || !indError ? <Cargando /> : null)}
          {detalleDe && ind ? (
            <PanelDetalle i={detalleDe} tramo={ind.tramo} area={area} pedir={pedirDetalle}
              onClose={cerrarDetalle} onGrilla={() => irAGrilla(detalleDe)} />
          ) : null}
        </>
      ) : null}

      {!esInd && error ? (
        <div className="dp-alert" role="alert">
          <i className="bi bi-exclamation-triangle-fill" aria-hidden="true" />
          <div style={{ flex: 1 }}><b>No se pudo actualizar.</b> {error}</div>
          <button type="button" className="dp-btn" onClick={cargar}>Reintentar</button>
        </div>
      ) : null}

      {esInd ? null : !d ? (loading || !error ? <Cargando /> : null) : (
        <div className="dp-layout">
          <div className="dp-a-main">
            {d.tramos_por_cerrar.length === 0 ? (
              <Card title="Cierres al día" sub={tramoActual ? `Tramo en curso: ${tramoActual.mes}, día ${fmt(tramoActual.dia)} de ${fmt(tramoActual.dias)}` : ''}>
                <div className="dp-empty">No quedan tramos anteriores por cerrar en estas áreas.</div>
              </Card>
            ) : d.tramos_por_cerrar.map((t) => <CierreTramo key={t.id} tramo={t} hoy={d.hoy} />)}
            <div className="dp-pair">
              <HorasExtra he={d.horas_extra_por_decidir} tramo={tramoHE} />
              <Contratos c={d.contratos} hoy={d.hoy} />
            </div>
            {je && je.total === 0 ? (
              <div className="dp-quiet"><i className="bi bi-check-circle" aria-hidden="true" /> Sin jornadas especiales ni coberturas (+2) por validar.</div>
            ) : je ? (
              <Card title="Jornadas especiales por validar" sub={plural(je.total, 'jornada', 'jornadas')}>
                <div className="dp-list">
                  {je.por_area.map((x) => (
                    <div className="dp-list-row" key={x.area}><span className="dp-grow">{x.area}</span><span className="dp-num">{fmt(x.jornadas)}</span></div>
                  ))}
                </div>
                {tramoHE ? <div className="dp-foot"><button type="button" className="dp-btn" onClick={() => irAMarcaciones({ area: '', desde: tramoHE.fecha_inicio, hasta: tramoHE.fecha_fin, accion: 'grilla' })}>Validar en la grilla</button></div> : null}
              </Card>
            ) : null}
          </div>
          <Hoy filas={d.hoy_por_area} total={d.hoy_total} fecha={d.hoy} tramo={tramoActual} />
          <TramoPorArea t={d.tramo_por_area} />
        </div>
      )}
    </div>
  );
}

export default function DashboardApp() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  );
}

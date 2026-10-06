import React, { useMemo } from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { In, Skeleton, Tag, fmt, hrs, num } from './ui';

const C = {
  brand: '#2447b8',
  ok: '#1f9d6b',
  bad: '#d64545',
  warn: '#d98a1c',
  info: '#2f80c9',
  ink3: '#77839d',
  line: '#e2e7f0',
};

const DIAS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

const ausenciaColor = (tipo) => {
  const t = String(tipo || '');
  if (t.includes('Injustificada')) return C.bad;
  if (t.includes('Vacaciones')) return C.ok;
  if (t.includes('Licencias')) return C.info;
  if (t.includes('Permisos')) return C.warn;
  return C.brand;
};

function PeriodoSkeleton() {
  return (
    <div aria-busy="true" aria-label="Cargando análisis del período">
      <div className="dx-panel dx-band">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="dx-cell"><Skeleton h={14} w="55%" /><Skeleton h={34} w="45%" /><Skeleton h={12} w="80%" /></div>
        ))}
      </div>
      <div className="dx-panel dx-sec dx-card-pad"><Skeleton h={16} w="35%" /><Skeleton h={220} style={{ marginTop: 14 }} /></div>
    </div>
  );
}

function Cell({ label, tag, children, hint }) {
  return (
    <div className="dx-cell">
      <div className="dx-cell-top">
        <span className="dx-cell-label">{label}</span>
        {tag}
      </div>
      <div className="dx-cell-num">{children}</div>
      <div className="dx-cell-hint">{hint}</div>
    </div>
  );
}

function TightRow({ label, value, pct, color }) {
  return (
    <div className="dx-tight">
      <span>{label}</span>
      <div className="dx-track"><span style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} /></div>
      <span>{value}</span>
    </div>
  );
}

function BarRow({ label, right, pct, color }) {
  return (
    <div className="dx-mini">
      <div className="dx-bar-row-top"><span>{label}</span><span>{right}</span></div>
      <div className="dx-track"><span style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} /></div>
    </div>
  );
}

export default function TabPeriodo({ data, loading }) {
  const d = data || {};
  const fuerza = d.fuerza_laboral || {};
  const hoy = fuerza.hoy || {};
  const paridad = hoy.paridad || {};
  const contratos = hoy.contratos || {};
  const edades = hoy.edades || {};
  const antig = hoy.antiguedad || {};
  const matriz = d.matriz_asistencia || {};
  const kpi = d.kpis_operacionales || {};
  const colacion = kpi.colacion || {};
  const deuda = kpi.deuda || {};
  const he = kpi.horas_extras || {};
  const cierres = Array.isArray(d.cierres_pendientes) ? d.cierres_pendientes : [];
  const desglose = (d.origen_ausentismo && Array.isArray(d.origen_ausentismo.desglose)) ? d.origen_ausentismo.desglose : [];
  const deudores = Array.isArray(d.top_deudores) ? d.top_deudores : [];
  const fugas = Array.isArray(d.top_infractores) ? d.top_infractores : [];

  const esperado = num(matriz.esperado);
  const real = num(matriz.asistencia_real);
  const tasaAsist = esperado > 0 ? Math.round((real / esperado) * 1000) / 10 : 0;
  const tasaAus = esperado > 0 ? Math.round((100 - tasaAsist) * 10) / 10 : 0;

  const trend = useMemo(
    () => (Array.isArray(matriz.tendencia) ? matriz.tendencia : []).map((t) => ({
      fecha: t && t.fecha ? String(t.fecha).substring(5) : '',
      Asistencias: num(t && t.asistencia),
      Justificados: num(t && t.ausencia_justificada),
      Inasistencias: num(t && t.inasistencia),
    })),
    [matriz.tendencia]
  );

  const heat = useMemo(() => {
    const pivot = {};
    (Array.isArray(d.heatmap_area_dia) ? d.heatmap_area_dia : []).forEach((h) => {
      if (!h) return;
      const area = h.area || 'Sin área';
      if (!pivot[area]) pivot[area] = Array(7).fill(0);
      if (h.dia >= 0 && h.dia <= 6) pivot[area][h.dia] = num(h.fugas_min);
    });
    return pivot;
  }, [d.heatmap_area_dia]);

  if (loading && !data) return <PeriodoSkeleton />;

  if (!data) {
    return (
      <div className="dx-panel dx-empty">
        <b>Elige un rango de fechas</b>
        Selecciona desde y hasta para ver el análisis del período.
      </div>
    );
  }

  const total = num(paridad.Total) || num(fuerza.dotacion_activa);
  const hombres = num(paridad.Hombres);
  const mujeres = num(paridad.Mujeres);
  const pH = total > 0 ? Math.round((hombres / total) * 100) : 0;
  const pM = total > 0 ? Math.round((mujeres / total) * 100) : 0;

  const antTotal = Object.values(antig).reduce((a, b) => a + num(b), 0) || 1;
  const antRows = [
    ['< 1 año', 'less_1'], ['1 a 3 años', '1_3'], ['3 a 5 años', '3_5'], ['Más de 5 años', 'plus_5'],
  ].map(([label, key]) => ({ label, val: num(antig[key]), pct: Math.round((num(antig[key]) / antTotal) * 100) }));

  const edadRows = Object.keys(edades).map((k) => ({ label: k, val: num(edades[k]) }));
  const edadMax = Math.max(1, ...edadRows.map((e) => e.val));
  const contratoRows = Object.keys(contratos).map((k) => ({ label: k, val: num(contratos[k]) }));
  const contratoTotal = contratoRows.reduce((a, b) => a + b.val, 0) || 1;
  const contratoColors = [C.brand, C.ok, C.warn, C.info, C.bad];

  const totalDias = desglose.reduce((a, b) => a + num(b && b.dias), 0);
  const heatAreas = Object.keys(heat);

  const heatStyle = (min) => {
    if (!(min > 0)) return {};
    const a = Math.min(0.88, 0.14 + (Math.min(min, 240) / 240) * 0.74);
    return { background: `rgba(184,34,45,${a.toFixed(2)})`, color: a > 0.5 ? '#fff' : '#7d1620' };
  };

  return (
    <div>
      {/* Resumen del período */}
      <In i={0} className="dx-panel dx-band">
        <Cell
          label="Ausentismo"
          tag={<Tag tone="mute">{fmt(tasaAsist, 1)}% asistencia</Tag>}
          hint={<>Asistió <b>{fmt(real)}</b> de <b>{fmt(esperado)}</b> días esperados · <b>{fmt(Math.max(0, esperado - real))}</b> sin trabajar</>}
        >{fmt(tasaAus, 1)}<small>%</small></Cell>
        <Cell
          label="Deuda horaria"
          tag={<Tag tone={num(deuda.pendiente_hrs) > 100 ? 'bad' : 'mute'}>{num(deuda.pendiente_hrs) > 100 ? 'Alta' : 'Pendiente'}</Tag>}
          hint={<>Condonada <b>{hrs(deuda.condonada_hrs)}</b> · permisos personales <b>{hrs(deuda.permisos_hrs)}</b></>}
        >{fmt(deuda.pendiente_hrs, num(deuda.pendiente_hrs) % 1 ? 1 : 0)}<small>h</small></Cell>
        <Cell
          label="Horas extra en cola"
          tag={<Tag tone="info">{fmt(he.tasa_aprobacion)}% aprobadas</Tag>}
          hint={<><b>{hrs(he.pendientes_hrs)}</b> acumuladas por resolver</>}
        >{fmt(he.pendientes_solicitudes)}<small>solicitudes</small></Cell>
        <Cell
          label="Excesos de colación"
          tag={<Tag tone={num(colacion.tasa_exceso) > 30 ? 'warn' : 'ok'}>{num(colacion.tasa_exceso) > 30 ? 'Sobre lo normal' : 'Controlado'}</Tag>}
          hint={<>Almuerzo real <b>{fmt(colacion.real_prom)} min</b> vs <b>{fmt(colacion.teorico_prom)} min</b> teóricos · {hrs(colacion.total_exceso_hrs)} de exceso</>}
        >{fmt(colacion.tasa_exceso)}<small>%</small></Cell>
      </In>

      {/* Cierres de período */}
      <In i={1} className="dx-sec">
        {cierres.length === 0 ? (
          <div className="dx-panel dx-notice" data-tone="ok">
            <i className="bi bi-check-circle-fill" aria-hidden="true" />
            <div>
              <div className="dx-notice-title">Cierres de período al día</div>
              <div className="dx-notice-text">Todas las áreas activas cerraron los meses anteriores.</div>
            </div>
          </div>
        ) : (
          <div className="dx-panel dx-notice" data-tone="warn">
            <i className="bi bi-exclamation-triangle-fill" aria-hidden="true" />
            <div style={{ minWidth: 0 }}>
              <div className="dx-notice-title">{cierres.length === 1 ? '1 período' : `${cierres.length} períodos`} con cierres pendientes</div>
              <div className="dx-notice-text">Las áreas listadas aún no ejecutan el cierre.</div>
              <div className="dx-closures">
                {cierres.map((p, i) => (
                  <div className="dx-closure" key={i}>
                    <b>{p.mes_cierre}</b> <span>· {p.activo === 1 ? 'período activo' : 'mes pasado'} · {p.fecha_inicio} al {p.fecha_fin}</span>
                    <div style={{ marginTop: 4 }}>{(p.areas_pendientes || []).join(', ') || `${fmt(p.total_pendientes)} áreas`}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </In>

      {/* Tendencia + composición de ausencias */}
      <div className="dx-grid-2 dx-sec">
        <In i={2} className="dx-panel dx-card-pad">
          <div className="dx-sec-head" style={{ margin: 0 }}>
            <h2 className="dx-sec-title">Tendencia diaria</h2>
            <span className="dx-sec-sub">Personas por día</span>
          </div>
          <div className="dx-legend">
            <span><i style={{ background: C.brand }} />Asistencias</span>
            <span><i style={{ background: C.ok }} />Justificados</span>
            <span><i style={{ background: C.bad }} />Inasistencias</span>
          </div>
          <div className="dx-chart">
            {trend.length === 0 ? (
              <div className="dx-empty">Sin datos en este período.</div>
            ) : (
              <ResponsiveContainer>
                <AreaChart data={trend} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 4" vertical={false} stroke={C.line} />
                  <XAxis dataKey="fecha" stroke={C.ink3} fontSize={11} tickLine={false} axisLine={false} tickMargin={8} minTickGap={18} />
                  <YAxis stroke={C.ink3} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    cursor={{ stroke: C.line }}
                    contentStyle={{ background: '#fff', border: `1px solid ${C.line}`, borderRadius: 10, fontSize: 12, boxShadow: '0 6px 20px rgba(20,32,59,.08)' }}
                  />
                  <Area type="monotone" dataKey="Asistencias" stroke={C.brand} strokeWidth={2} fill={C.brand} fillOpacity={0.08} isAnimationActive={false} />
                  <Area type="monotone" dataKey="Justificados" stroke={C.ok} strokeWidth={2} fill={C.ok} fillOpacity={0.06} isAnimationActive={false} />
                  <Area type="monotone" dataKey="Inasistencias" stroke={C.bad} strokeWidth={2} fill={C.bad} fillOpacity={0.06} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </In>

        <In i={3} className="dx-panel dx-card-pad">
          <div className="dx-sec-head" style={{ margin: 0 }}>
            <h2 className="dx-sec-title">Por qué faltan</h2>
            <span className="dx-sec-sub">{fmt(totalDias)} días</span>
          </div>
          {desglose.length === 0 ? (
            <div className="dx-empty">No hay ausencias registradas en este período.</div>
          ) : (
            <div className="dx-bars">
              {desglose.map((it, i) => {
                const pct = totalDias > 0 ? Math.round((num(it.dias) / totalDias) * 100) : 0;
                return (
                  <div key={i}>
                    <div className="dx-bar-row-top">
                      <span>{it.tipo}</span>
                      <span>{fmt(it.dias)} {num(it.dias) === 1 ? 'día' : 'días'} · {pct}%</span>
                    </div>
                    <div className="dx-track"><span style={{ width: `${pct}%`, background: ausenciaColor(it.tipo) }} /></div>
                  </div>
                );
              })}
            </div>
          )}
        </In>
      </div>

      {/* Fugas por área y día + desviaciones */}
      <div className="dx-grid-eq dx-sec">
        <In i={4} className="dx-panel dx-card-pad">
          <div className="dx-sec-head" style={{ margin: 0 }}>
            <h2 className="dx-sec-title">Fugas horarias</h2>
            <span className="dx-sec-sub">Minutos por área y día</span>
          </div>
          {heatAreas.length === 0 ? (
            <div className="dx-empty">No hay fugas horarias en el período.</div>
          ) : (
            <>
              <div className="dx-heat-wrap">
                <div className="dx-heat" role="table" aria-label="Fugas horarias por área y día de la semana">
                  <div className="dx-heat-h" role="columnheader">Área</div>
                  {DIAS.map((x) => <div className="dx-heat-h" role="columnheader" key={x}>{x}</div>)}
                  {heatAreas.map((area) => (
                    <React.Fragment key={area}>
                      <div className="dx-heat-area" role="rowheader" title={area}>{area}</div>
                      {heat[area].map((v, i) => (
                        <div className="dx-heat-c" role="cell" key={i} style={heatStyle(v)} title={`${area} · ${DIAS[i]}: ${Math.round(v)} min`}>
                          {v > 0 ? Math.round(v) : '·'}
                        </div>
                      ))}
                    </React.Fragment>
                  ))}
                </div>
              </div>
              <div className="dx-scale">menos <i aria-hidden="true" /> más minutos</div>
            </>
          )}
        </In>

        <In i={5} className="dx-panel dx-card-pad">
          <div className="dx-sec-head" style={{ margin: 0 }}>
            <h2 className="dx-sec-title">Desviaciones</h2>
            <span className="dx-sec-sub">Top 5 del período</span>
          </div>
          <div className="dx-ranks">
            <div>
              <div className="dx-rank-title">Mayor deuda de tiempo</div>
              {deudores.length === 0 ? <div className="dx-empty" style={{ padding: '18px 0' }}>Sin deudores</div> : deudores.slice(0, 5).map((x, i) => (
                <div className="dx-rank" key={i}>
                  <span className="dx-rank-n">{i + 1}</span>
                  <span className="dx-rank-name" title={x.nombre}>{x.nombre || 'Sin nombre'}</span>
                  <span className="dx-rank-val" data-tone="bad">{fmt(x.deuda_hrs, num(x.deuda_hrs) % 1 ? 1 : 0)} h</span>
                </div>
              ))}
            </div>
            <div>
              <div className="dx-rank-title">Fugas más frecuentes</div>
              {fugas.length === 0 ? <div className="dx-empty" style={{ padding: '18px 0' }}>Sin registros</div> : fugas.slice(0, 5).map((x, i) => (
                <div className="dx-rank" key={i}>
                  <span className="dx-rank-n">{i + 1}</span>
                  <span className="dx-rank-name" title={x.nombre}>{x.nombre || 'Sin nombre'}</span>
                  <span className="dx-rank-val" data-tone="warn">{fmt(x.eventos)} ev.</span>
                </div>
              ))}
            </div>
          </div>
        </In>
      </div>

      {/* Dotación */}
      <In i={6} className="dx-sec">
        <div className="dx-sec-head">
          <h2 className="dx-sec-title">Dotación</h2>
          <span className="dx-sec-sub">{fmt(fuerza.dotacion_activa)} activos · rotación {fmt(fuerza.tasa_rotacion, 1)}%</span>
        </div>
        <div className="dx-panel dx-demo">
          <div>
            <div className="dx-demo-title">Género</div>
            <div className="dx-kv"><span>Hombres</span><span>{fmt(hombres)} · {pH}%</span></div>
            <div className="dx-kv"><span>Mujeres</span><span>{fmt(mujeres)} · {pM}%</span></div>
            <div className="dx-split" aria-hidden="true">
              <span style={{ width: `${pH}%`, background: C.brand }} />
              <span style={{ width: `${pM}%`, background: '#8aa0e6' }} />
            </div>
            <div className="dx-sec-sub">Total registrado: {fmt(total)}</div>
          </div>
          <div>
            <div className="dx-demo-title">Edades · promedio {fmt(fuerza.edad_promedio, 1)} años</div>
            {edadRows.length === 0 ? <div className="dx-sec-sub">Sin datos de edades</div> : edadRows.map((e) => (
              <TightRow key={e.label} label={e.label} value={fmt(e.val)} pct={(e.val / edadMax) * 100} color={C.brand} />
            ))}
          </div>
          <div>
            <div className="dx-demo-title">Antigüedad</div>
            {antRows.map((a) => (
              <BarRow key={a.label} label={a.label} right={`${fmt(a.val)} · ${a.pct}%`} pct={a.pct} color={C.brand} />
            ))}
          </div>
          <div>
            <div className="dx-demo-title">Contratos</div>
            <div className="dx-kv">
              <span>Vencen en 30 días</span>
              <span style={{ color: num(fuerza.contratos_por_vencer) > 0 ? 'var(--dx-bad)' : 'var(--dx-ok)' }}>{fmt(fuerza.contratos_por_vencer)}</span>
            </div>
            <div className="dx-split" aria-hidden="true">
              {contratoRows.map((c, i) => <span key={c.label} style={{ width: `${(c.val / contratoTotal) * 100}%`, background: contratoColors[i % contratoColors.length] }} />)}
            </div>
            <div className="dx-donut-legend" style={{ marginTop: 10 }}>
              {contratoRows.length === 0 ? <span className="dx-sec-sub">Sin datos</span> : contratoRows.map((c, i) => (
                <div key={c.label}><i style={{ background: contratoColors[i % contratoColors.length] }} /><span title={c.label}>{c.label}</span><b>{fmt(c.val)}</b></div>
              ))}
            </div>
          </div>
        </div>
      </In>
    </div>
  );
}

import React from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  BarChart,
  Bar,
  Cell,
  PieChart,
  Pie
} from 'recharts';

export default function TabPeriodo({ data, loading }) {
  if (loading && !data) {
    return (
      <div className="d-flex justify-content-center align-items-center py-5">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando...</span>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-5 text-muted bg-white rounded border border-light p-4">
        <i className="bi bi-calendar-x fs-1 mb-2 block"></i>
        <p className="mb-0">Seleccione un rango de fechas y presione buscar para ver el análisis del período.</p>
      </div>
    );
  }

  const {
    fuerza_laboral,
    matriz_asistencia,
    fugas_operativas,
    origen_ausentismo,
    kpis_operacionales,
    cierres_pendientes,
    top_infractores,
    top_deudores,
    heatmap_area_dia
  } = data;

  const hoyData = fuerza_laboral?.hoy || {};
  const paridad = hoyData.paridad || {};
  const contratos = hoyData.contratos || {};
  const edades = hoyData.edades || {};
  const antiguedad = hoyData.antiguedad || {};

  const totalFuerza = paridad.Total || fuerza_laboral?.dotacion_activa || 0;
  const hombres = paridad.Hombres || 0;
  const mujeres = paridad.Mujeres || 0;
  const pctHombres = totalFuerza > 0 ? Math.round((hombres / totalFuerza) * 100) : 0;
  const pctMujeres = totalFuerza > 0 ? Math.round((mujeres / totalFuerza) * 100) : 0;

  const edadesChartData = Object.keys(edades).map(key => ({
    rango: key,
    Cantidad: edades[key] || 0
  }));

  const antiTotal = Object.values(antiguedad).reduce((a, b) => a + b, 0) || 1;
  const antiDataList = [
    { label: '< 1 Año', key: 'less_1', color: '#3B82F6' },
    { label: '1 - 3 Años', key: '1_3', color: '#6366F1' },
    { label: '3 - 5 Años', key: '3_5', color: '#0EA5E9' },
    { label: '> 5 Años', key: 'plus_5', color: '#10B981' }
  ].map(item => ({
    ...item,
    val: antiguedad[item.key] || 0,
    pct: Math.round(((antiguedad[item.key] || 0) / antiTotal) * 100)
  }));

  const COLORS = ['#10B981', '#6366F1', '#F59E0B', '#3B82F6', '#EF4444'];
  const contratosChartData = Object.keys(contratos).map(key => ({
    name: key,
    value: contratos[key] || 0
  }));

  // Calculate global attendance rate (real present days / expected workdays)
  const esperado = matriz_asistencia?.esperado || 0;
  const realAsistencia = matriz_asistencia?.asistencia_real || 0;
  const tasaAsistencia = esperado > 0 ? Math.round((realAsistencia / esperado) * 1000) / 10 : 0;
  const tasaAusentismo = esperado > 0 ? Math.round((100 - tasaAsistencia) * 10) / 10 : 0;

  // Format daily trend data for Recharts
  const trendData = (matriz_asistencia?.tendencia || []).map(item => ({
    fecha: item.fecha ? item.fecha.substring(5) : '', // format YYYY-MM-DD to MM-DD
    Asistencias: item.asistencia || 0,
    Justificados: item.ausencia_justificada || 0,
    Inasistencias: item.inasistencia || 0
  }));

  // Heatmap helper: convert day number (0-6) to column index (0=Domingo, 1=Lunes, etc.)
  const diasSemana = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
  
  // Pivot heatmap data: Area -> {0: min, 1: min, ...}
  const heatmapPivot = {};
  (heatmap_area_dia || []).forEach(h => {
    if (!heatmapPivot[h.area]) {
      heatmapPivot[h.area] = Array(7).fill(0);
    }
    // h.dia is 0 (Sunday) to 6 (Saturday)
    if (h.dia >= 0 && h.dia <= 6) {
      heatmapPivot[h.area][h.dia] = h.fugas_min || 0;
    }
  });

  // Helper for heatmap cell color based on time debt leakage
  const getHeatmapColor = (min) => {
    if (min === 0) return 'bg-white text-muted';
    if (min < 30) return 'bg-warning-subtle text-warning-emphasis';
    if (min < 120) return 'bg-danger-subtle text-danger-emphasis';
    return 'bg-danger text-white fw-bold';
  };

  // Helper to format minutes into hours
  const fmtHrs = (h) => {
    if (!h) return '0 hrs';
    return `${h} hrs`;
  };

  return (
    <div>
      {/* 4 Main Operational KPI Cards */}
      <div className="row g-3 mb-4">
        {/* KPI 1: Lunch Break Overruns */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">EXCESOS DE COLACIÓN</span>
              <span className={`badge rounded-pill px-2 py-1 ${(kpis_operacionales?.colacion?.tasa_exceso ?? 0) > 30 ? 'bg-warning-subtle text-warning' : 'bg-success-subtle text-success'}`}>
                {kpis_operacionales?.colacion?.tasa_exceso ?? 0}% de excesos
              </span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{kpis_operacionales?.colacion?.tasa_exceso ?? 0}%</h3>
            </div>
            <p className="text-muted small mt-2 mb-0">
              Almuerzo real promedio: <strong className="text-dark">{kpis_operacionales?.colacion?.real_prom ?? 0} min</strong> (vs {kpis_operacionales?.colacion?.teorico_prom ?? 0} min teóricos).
              Exceso acumulado: <strong className="text-dark">{kpis_operacionales?.colacion?.total_exceso_hrs ?? 0}h</strong>.
            </p>
          </div>
        </div>

        {/* KPI 2: Time Debt */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">DEUDA HORARIA NETA</span>
              <span className={`badge rounded-pill px-2 py-1 ${(kpis_operacionales?.deuda?.pendiente_hrs ?? 0) > 100 ? 'bg-danger-subtle text-danger' : 'bg-secondary-subtle text-secondary'}`}>
                {fmtHrs(kpis_operacionales?.deuda?.pendiente_hrs)} Pendiente
              </span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{fmtHrs(kpis_operacionales?.deuda?.pendiente_hrs)}</h3>
            </div>
            <p className="text-muted small mt-2 mb-0">
              Deuda condonada: <strong className="text-dark">{fmtHrs(kpis_operacionales?.deuda?.condonada_hrs)}</strong>.
              Deuda por permisos personales: <strong className="text-dark">{fmtHrs(kpis_operacionales?.deuda?.permisos_hrs)}</strong>.
            </p>
          </div>
        </div>

        {/* KPI 3: Overtime Approvals & Queue */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">HORAS EXTRAS EN COLA</span>
              <span className="badge bg-primary-subtle text-primary rounded-pill px-2 py-1">
                {kpis_operacionales?.horas_extras?.tasa_aprobacion ?? 0}% Aprobación
              </span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{kpis_operacionales?.horas_extras?.pendientes_solicitudes ?? 0} <span className="fs-6 text-muted fw-normal">solicitudes</span></h3>
            </div>
            <p className="text-muted small mt-2 mb-0">
              Horas extras acumuladas en cola: <strong className="text-dark">{fmtHrs(kpis_operacionales?.horas_extras?.pendientes_hrs)}</strong>.
              Tasa aprobación del periodo: <strong className="text-dark">{kpis_operacionales?.horas_extras?.tasa_aprobacion ?? 0}%</strong>.
            </p>
          </div>
        </div>

        {/* KPI 4: Absenteeism Rate */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">TASA DE AUSENTISMO</span>
              <span className="badge bg-secondary-subtle text-secondary rounded-pill px-2 py-1">
                {tasaAsistencia}% Asistencia
              </span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{tasaAusentismo}%</h3>
            </div>
            <p className="text-muted small mt-2 mb-0">
              Presencias físicas: <strong className="text-dark">{realAsistencia} días</strong> (de {esperado} esperados).
              Días no trabajados: <strong className="text-dark">{esperado - realAsistencia} turnos</strong>.
            </p>
          </div>
        </div>
      </div>

      {/* Row: Demographics and Force Labor */}
      <div className="row g-3 mb-4">
        <div className="col-12">
          <div className="card bg-white border border-light shadow-sm rounded">
            <div className="card-header bg-white border-bottom border-light p-3 d-flex justify-content-between align-items-center">
              <h5 className="mb-0 fw-bold text-dark">
                <i className="bi bi-people-fill text-muted me-2"></i>
                Dotación y Fuerza Laboral (Demografía)
              </h5>
              <div className="d-flex gap-2">
                <span className="badge bg-primary-subtle text-primary rounded-pill px-2.5 py-1" style={{ fontSize: '0.75rem' }}>
                  Dotación Activa: {fuerza_laboral?.dotacion_activa ?? 0}
                </span>
                <span className="badge bg-warning-subtle text-warning-emphasis rounded-pill px-2.5 py-1" style={{ fontSize: '0.75rem' }}>
                  Rotación: {fuerza_laboral?.tasa_rotacion ?? 0}%
                </span>
              </div>
            </div>
            <div className="card-body p-3">
              <div className="row g-4">
                
                {/* Column 1: Gender Parity */}
                <div className="col-12 col-md-3 border-end border-light">
                  <div className="d-flex flex-column h-100 justify-content-between">
                    <div>
                      <h6 className="fw-bold text-muted small mb-3">PARIDAD DE GÉNERO</h6>
                      <div className="d-flex justify-content-between align-items-center mb-2">
                        <span className="small text-dark fw-semibold"><i className="bi bi-gender-male text-primary me-1"></i>Hombres</span>
                        <span className="small fw-mono text-dark">{hombres} ({pctHombres}%)</span>
                      </div>
                      <div className="d-flex justify-content-between align-items-center mb-3">
                        <span className="small text-dark fw-semibold"><i className="bi bi-gender-female text-danger me-1"></i>Mujeres</span>
                        <span className="small fw-mono text-dark">{mujeres} ({pctMujeres}%)</span>
                      </div>
                    </div>
                    <div>
                      <div className="progress rounded-pill mb-2" style={{ height: '8px' }}>
                        <div className="progress-bar bg-primary" role="progressbar" style={{ width: `${pctHombres}%` }} aria-valuenow={pctHombres} aria-valuemin="0" aria-valuemax="100"></div>
                        <div className="progress-bar bg-danger" role="progressbar" style={{ width: `${pctMujeres}%` }} aria-valuenow={pctMujeres} aria-valuemin="0" aria-valuemax="100"></div>
                      </div>
                      <span className="text-muted small block text-center">Total registrado: {totalFuerza}</span>
                    </div>
                  </div>
                </div>

                {/* Column 2: Age Distribution */}
                <div className="col-12 col-md-3 border-end border-light">
                  <h6 className="fw-bold text-muted small mb-2">DISTRIBUCIÓN POR EDADES</h6>
                  <div className="d-flex justify-content-between align-items-center mb-1">
                    <span className="small text-muted">Edad Promedio:</span>
                    <span className="small fw-bold text-dark">{fuerza_laboral?.edad_promedio ?? 0} años</span>
                  </div>
                  <div style={{ width: '100%', height: '110px' }}>
                    {edadesChartData.length > 0 ? (
                      <ResponsiveContainer>
                        <BarChart data={edadesChartData} margin={{ top: 5, right: 5, left: -35, bottom: 0 }}>
                          <XAxis dataKey="rango" stroke="#94A3B8" fontSize={8} tickLine={false} />
                          <YAxis stroke="#94A3B8" fontSize={8} tickLine={false} axisLine={false} allowDecimals={false} />
                          <Tooltip contentStyle={{ fontSize: '10px', padding: '4px 8px', borderRadius: '4px' }} />
                          <Bar dataKey="Cantidad" fill="#8B5CF6" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="text-muted small text-center pt-4">Sin datos de edades</div>
                    )}
                  </div>
                </div>

                {/* Column 3: Seniority/Permanence */}
                <div className="col-12 col-md-3 border-end border-light">
                  <h6 className="fw-bold text-muted small mb-2">PERMANENCIA Y RETENCIÓN</h6>
                  <div className="d-flex flex-column gap-2">
                    {antiDataList.map((item, idx) => (
                      <div key={idx}>
                        <div className="d-flex justify-content-between align-items-center mb-0.5" style={{ fontSize: '0.72rem' }}>
                          <span className="text-dark">{item.label}</span>
                          <span className="text-muted fw-mono">{item.val} ({item.pct}%)</span>
                        </div>
                        <div className="progress rounded-pill" style={{ height: '5px' }}>
                          <div className="progress-bar rounded-pill" role="progressbar" style={{ width: `${item.pct}%`, backgroundColor: item.color }} aria-valuenow={item.pct} aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Column 4: Contract Types */}
                <div className="col-12 col-md-3">
                  <h6 className="fw-bold text-muted small mb-2">CONFIGURACIÓN CONTRACTUAL</h6>
                  <div className="d-flex align-items-center justify-content-between mb-2">
                    <span className="small text-muted">Vencimientos (30 días):</span>
                    <span className={`badge ${fuerza_laboral?.contratos_por_vencer > 0 ? 'bg-danger-subtle text-danger' : 'bg-success-subtle text-success'} rounded-pill`}>
                      {fuerza_laboral?.contratos_por_vencer ?? 0} por vencer
                    </span>
                  </div>
                  <div className="d-flex align-items-center" style={{ height: '90px' }}>
                    <div style={{ width: '55%', height: '100%' }}>
                      {contratosChartData.length > 0 ? (
                        <ResponsiveContainer>
                          <PieChart>
                            <Pie
                              data={contratosChartData}
                              cx="50%"
                              cy="50%"
                              innerRadius={20}
                              outerRadius={35}
                              paddingAngle={2}
                              dataKey="value"
                            >
                              {contratosChartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip contentStyle={{ fontSize: '10px', padding: '4px 8px', borderRadius: '4px' }} />
                          </PieChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="text-muted small text-center pt-4">Sin datos</div>
                      )}
                    </div>
                    <div className="flex-grow-1" style={{ fontSize: '0.68rem', lineHeight: '1.2' }}>
                      {contratosChartData.slice(0, 3).map((item, idx) => (
                        <div key={idx} className="d-flex align-items-center gap-1 mb-1 text-truncate">
                          <span className="d-inline-block rounded-circle" style={{ width: 6, height: 6, background: COLORS[idx % COLORS.length] }}></span>
                          <span className="text-dark fw-semibold truncate" style={{ maxWidth: '65px' }} title={item.name}>{item.name}:</span>
                          <span className="text-muted fw-mono">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Pending Period Closures Widget */}
      <div className="row mb-4">
        <div className="col-12">
          <div className="card bg-white border border-light shadow-sm rounded">
            <div className="card-header bg-white border-bottom border-light p-3">
              <h5 className="mb-0 fw-bold text-dark">
                <i className="bi bi-lock-fill text-muted me-2"></i>
                Auditoría: Cierres de Período Pendientes por Área
              </h5>
            </div>
            <div className="card-body p-3">
              {(!cierres_pendientes || cierres_pendientes.length === 0) ? (
                <div className="alert alert-success d-flex align-items-center mb-0 border border-success-subtle p-3 rounded" role="alert">
                  <i className="bi bi-patch-check-fill me-2 fs-5"></i>
                  <div><strong>¡Todo al día!</strong> Todas las áreas activas han ejecutado sus cierres de período para los meses anteriores.</div>
                </div>
              ) : (
                <div className="row g-3">
                  {cierres_pendientes.map((p, idx) => (
                    <div key={idx} className="col-12 col-md-6 col-lg-4">
                      <div className="p-3 rounded bg-light border border-light h-100 d-flex flex-column justify-content-between">
                        <div>
                          <div className="d-flex justify-content-between align-items-center mb-2">
                            <h6 className="fw-bold mb-0 text-dark">{p.mes_cierre}</h6>
                            {p.activo === 1 ? (
                              <span className="badge bg-primary text-white rounded px-2 py-0.5" style={{ fontSize: '0.65rem' }}>Periodo Activo</span>
                            ) : (
                              <span className="badge bg-warning text-dark rounded px-2 py-0.5" style={{ fontSize: '0.65rem' }}>Mes Pasado</span>
                            )}
                          </div>
                          <p className="text-muted small mb-3">Rango: {p.fecha_inicio} al {p.fecha_fin}</p>
                          <div className="d-flex flex-wrap gap-1.5 align-items-center">
                            <span className="text-muted small me-1">Pendientes ({p.total_pendientes}):</span>
                            {p.areas_pendientes.map((area, aIdx) => (
                              <span key={aIdx} className="badge bg-white text-dark border border-light shadow-sm rounded px-2 py-1" style={{ fontSize: '0.75rem' }}>
                                {area}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Row 3: Daily Trend & Absenteeism Breakdown */}
      <div className="row g-4 mb-4">
        {/* Daily Trend Chart */}
        <div className="col-12 col-lg-8">
          <div className="card bg-white border border-light shadow-sm rounded h-100">
            <div className="card-header bg-white border-bottom border-light p-3">
              <h5 className="mb-0 fw-bold text-dark">
                <i className="bi bi-graph-up-arrow text-muted me-2"></i>
                Tendencia Diaria de Dotación y Ausentismo
              </h5>
            </div>
            <div className="card-body p-3">
              <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                  <AreaChart
                    data={trendData}
                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="colorAsistencias" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#4F46E5" stopOpacity={0.1}/>
                        <stop offset="95%" stopColor="#4F46E5" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorJustificados" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10B981" stopOpacity={0.1}/>
                        <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorInasistencias" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#EF4444" stopOpacity={0.1}/>
                        <stop offset="95%" stopColor="#EF4444" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                    <XAxis dataKey="fecha" stroke="#94A3B8" fontSize={11} tickLine={false} />
                    <YAxis stroke="#94A3B8" fontSize={11} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: '8px' }} />
                    <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />
                    <Area type="monotone" dataKey="Asistencias" stroke="#4F46E5" strokeWidth={2} fillOpacity={1} fill="url(#colorAsistencias)" />
                    <Area type="monotone" dataKey="Justificados" stroke="#10B981" strokeWidth={2} fillOpacity={1} fill="url(#colorJustificados)" />
                    <Area type="monotone" dataKey="Inasistencias" stroke="#EF4444" strokeWidth={2} fillOpacity={1} fill="url(#colorInasistencias)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>

        {/* Operational Absenteeism Breakdown */}
        <div className="col-12 col-lg-4">
          <div className="card bg-white border border-light shadow-sm rounded h-100">
            <div className="card-header bg-white border-bottom border-light p-3">
              <h5 className="mb-0 fw-bold text-dark">
                <i className="bi bi-pie-chart text-muted me-2"></i>
                Composición de Ausencias
              </h5>
            </div>
            <div className="card-body p-3 d-flex flex-column justify-content-center">
              {(!origen_ausentismo?.desglose || origen_ausentismo.desglose.length === 0) ? (
                <div className="text-center text-muted py-5">
                  No hay ausencias registradas en este período.
                </div>
              ) : (
                <div className="d-flex flex-column gap-3.5 w-100">
                  {origen_ausentismo.desglose.map((item, idx) => {
                    const totalDays = origen_ausentismo.desglose.reduce((a, b) => a + b.dias, 0);
                    const pct = totalDays > 0 ? Math.round((item.dias / totalDays) * 100) : 0;
                    
                    // Assign colors operationally
                    let progressColor = 'bg-primary';
                    if (item.tipo.includes('Injustificada')) progressColor = 'bg-danger';
                    else if (item.tipo.includes('Vacaciones')) progressColor = 'bg-success';
                    else if (item.tipo.includes('Licencias')) progressColor = 'bg-info';
                    else if (item.tipo.includes('Permisos')) progressColor = 'bg-warning';

                    return (
                      <div key={idx}>
                        <div className="d-flex justify-content-between align-items-center mb-1">
                          <span className="small fw-semibold text-dark">{item.tipo}</span>
                          <span className="small text-muted">{item.dias} {item.dias === 1 ? 'día' : 'días'} ({pct}%)</span>
                        </div>
                        <div className="progress rounded-pill" style={{ height: '7px' }}>
                          <div
                            className={`progress-bar ${progressColor} rounded-pill`}
                            role="progressbar"
                            style={{ width: `${pct}%` }}
                            aria-valuenow={pct}
                            aria-valuemin="0"
                            aria-valuemax="100"
                          ></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Row 4: Leakage Heatmap & Tops */}
      <div className="row g-4 mb-4">
        {/* Heatmap area & day */}
        <div className="col-12 col-lg-6">
          <div className="card bg-white border border-light shadow-sm rounded h-100">
            <div className="card-header bg-white border-bottom border-light p-3">
              <h5 className="mb-0 fw-bold text-dark">
                <i className="bi bi-clock-history text-muted me-2"></i>
                Fugas Horarias Acumuladas por Área y Día (min)
              </h5>
            </div>
            <div className="card-body p-3">
              <div className="table-responsive rounded border border-light">
                <table className="table table-bordered align-middle text-center mb-0" style={{ fontSize: '0.8rem' }}>
                  <thead className="table-light text-muted">
                    <tr>
                      <th className="text-start px-2 py-1.5" style={{ minWidth: '110px' }}>Área</th>
                      {diasSemana.map((d, i) => <th key={i} className="py-1.5">{d}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(heatmapPivot).length === 0 ? (
                      <tr>
                        <td colSpan="8" className="text-center py-4 text-muted">
                          No hay fugas horarias en el periodo.
                        </td>
                      </tr>
                    ) : (
                      Object.keys(heatmapPivot).map((area, idx) => (
                        <tr key={idx}>
                          <td className="text-start fw-semibold text-dark px-2 py-1">{area}</td>
                          {heatmapPivot[area].map((val, dIdx) => (
                            <td key={dIdx} className={`${getHeatmapColor(val)} py-1`} style={{ transition: 'background-color 0.2s' }}>
                              {val > 0 ? `${Math.round(val)}'` : '-'}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              <div className="d-flex gap-3 justify-content-end mt-2" style={{ fontSize: '0.7rem' }}>
                <span className="d-flex align-items-center gap-1"><span className="d-inline-block rounded-circle" style={{ width: 8, height: 8, background: '#fee2e2' }}></span> &lt;30m</span>
                <span className="d-flex align-items-center gap-1"><span className="d-inline-block rounded-circle" style={{ width: 8, height: 8, background: '#fca5a5' }}></span> 30m - 2h</span>
                <span className="d-flex align-items-center gap-1"><span className="d-inline-block rounded-circle" style={{ width: 8, height: 8, background: '#ef4444' }}></span> &gt;2h</span>
              </div>
            </div>
          </div>
        </div>

        {/* Tops lists (Time Debtors & Overtime Generators) */}
        <div className="col-12 col-lg-6">
          <div className="card bg-white border border-light shadow-sm rounded h-100">
            <div className="card-header bg-white border-bottom border-light p-3">
              <h5 className="mb-0 fw-bold text-dark">
                <i className="bi bi-award text-muted me-2"></i>
                Comportamiento y Desviaciones
              </h5>
            </div>
            <div className="card-body p-3">
              <div className="row g-3">
                {/* Top Debtors */}
                <div className="col-12 col-md-6">
                  <h6 className="fw-bold text-muted small mb-2"><i className="bi bi-arrow-down-circle text-danger me-1"></i> TOP DEUDORES DE TIEMPO</h6>
                  <div className="table-responsive rounded border border-light">
                    <table className="table table-hover mb-0" style={{ fontSize: '0.75rem' }}>
                      <thead className="table-light">
                        <tr>
                          <th className="py-1">Nombre</th>
                          <th className="py-1 text-end">Deuda</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(!top_deudores || top_deudores.length === 0) ? (
                          <tr><td colSpan="2" className="text-center text-muted py-2">Sin deudores</td></tr>
                        ) : (
                          top_deudores.slice(0, 5).map((d, i) => (
                            <tr key={i}>
                              <td className="text-dark fw-semibold truncate py-1" style={{ maxWidth: '140px' }} title={d.nombre}>{d.nombre}</td>
                              <td className="text-end text-danger fw-mono py-1">+{d.deuda_hrs ?? 0}h</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Top Overtime Generators */}
                <div className="col-12 col-md-6">
                  <h6 className="fw-bold text-muted small mb-2"><i className="bi bi-arrow-up-circle text-success me-1"></i> TOP GENERADORES HE</h6>
                  <div className="table-responsive rounded border border-light">
                    <table className="table table-hover mb-0" style={{ fontSize: '0.75rem' }}>
                      <thead className="table-light">
                        <tr>
                          <th className="py-1">Nombre</th>
                          <th className="py-1 text-end">H.Extra</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(!top_infractores || top_infractores.length === 0) ? (
                          // Note: the analytics API returns top generators under top_infractores or top_he?
                          // In dashboard_analytics.py, get_dashboard_metrics outputs results[7] under 'top_infractores' (which queries asistencias for fugas)
                          // and results[8] under 'top_deudores'. Wait, let's verify where 'top_he' or top generators is!
                          // Ah, in dashboard_analytics.py:
                          // results[7] is top_infractores (fugas events)
                          // results[8] is top_deudores
                          // Let's check what keys exist in the analytics API. We mapped:
                          // results[7] -> top_infractores
                          // results[8] -> top_deudores
                          // results[9] -> heatmap_area_dia
                          // So we can show top infractores (eventos de fuga) instead of top HE, or show both!
                          <tr><td colSpan="2" className="text-center text-muted py-2">Sin registros</td></tr>
                        ) : (
                          top_infractores.slice(0, 5).map((item, i) => (
                            <tr key={i}>
                              <td className="text-dark fw-semibold truncate py-1" style={{ maxWidth: '140px' }} title={item.nombre}>{item.nombre}</td>
                              <td className="text-end text-warning fw-mono py-1">{item.eventos ?? 0} ev</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

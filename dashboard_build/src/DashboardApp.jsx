import React, { useState, useEffect, useCallback } from 'react';
import TabHoy from './TabHoy';
import TabPeriodo from './TabPeriodo';

const API_BASE_URL = '/api';

export default function DashboardApp() {
  const [activeTab, setActiveTab] = useState('hoy');
  const [selectedArea, setSelectedArea] = useState('Todas');
  const [selectedHorario, setSelectedHorario] = useState('Todos');
  const [fechaInicio, setFechaInicio] = useState('');
  const [fechaFin, setFechaFin] = useState('');
  
  const [areasList, setAreasList] = useState([]);
  const [horariosList, setHorariosList] = useState([]);
  
  const [todayPulse, setTodayPulse] = useState(null);
  const [todayDetail, setTodayDetail] = useState([]);
  const [todayLoading, setTodayLoading] = useState(false);
  
  const [periodData, setPeriodData] = useState(null);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [error, setError] = useState(null);

  // Get Auth headers
  const getHeaders = useCallback(() => {
    const token = localStorage.getItem('access_token');
    return {
      'Content-Type': 'application/json',
      'Authorization': token ? `Bearer ${token}` : ''
    };
  }, []);

  // Fetch areas on mount
  useEffect(() => {
    async function fetchAreas() {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) return;

        // Fetch areas
        const areasRes = await fetch(`${API_BASE_URL}/empleados/stats/`, { headers: getHeaders() });
        if (areasRes.ok) {
          const stats = await areasRes.json();
          setAreasList(stats.areas || []);
        }
      } catch (err) {
        console.error('Error fetching areas filter:', err);
      }
    }
    fetchAreas();
  }, [getHeaders]);

  // Fetch turnos dynamically when selectedArea changes
  useEffect(() => {
    async function fetchTurnos() {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) return;

        const areaParam = selectedArea === 'Todas' ? '' : `?area=${encodeURIComponent(selectedArea)}`;
        const turnosRes = await fetch(`${API_BASE_URL}/turnos/${areaParam}`, { headers: getHeaders() });
        if (turnosRes.ok) {
          const turnos = await turnosRes.json();
          setHorariosList(Array.isArray(turnos) ? turnos : []);
          setSelectedHorario('Todos');
        }
      } catch (err) {
        console.error('Error fetching turnos filter:', err);
      }
    }
    fetchTurnos();
  }, [selectedArea, getHeaders]);

  // Sync dates with the active period when selected area changes
  useEffect(() => {
    async function loadActivePeriod() {
      if (activeTab === 'hoy') return;
      try {
        const areaName = selectedArea || 'Todas';
        const res = await fetch(`${API_BASE_URL}/configuracion/periodos/activo/${encodeURIComponent(areaName)}/`, {
          headers: getHeaders()
        });
        if (res.ok) {
          const period = await res.json();
          if (period && period.fecha_inicio && period.fecha_fin) {
            setFechaInicio(period.fecha_inicio);
            setFechaFin(period.fecha_fin);
          }
        }
      } catch (err) {
        console.error('Error fetching active period:', err);
      }
    }
    loadActivePeriod();
  }, [selectedArea, activeTab, getHeaders]);

  // Load Today's Data
  const loadTodayData = useCallback(async () => {
    setTodayLoading(true);
    setError(null);
    try {
      const areaParam = selectedArea !== 'Todas' ? `?area=${encodeURIComponent(selectedArea)}` : '';
      
      const [pulseRes, detailRes] = await Promise.all([
        fetch(`${API_BASE_URL}/dashboard/pulse/${areaParam}`, { headers: getHeaders() }),
        fetch(`${API_BASE_URL}/dashboard/pulse/detail/${areaParam}`, { headers: getHeaders() })
      ]);

      if (pulseRes.ok && detailRes.ok) {
        const pulseJson = await pulseRes.json();
        const detailJson = await detailRes.json();
        
        setTodayPulse(pulseJson.data || null);
        setTodayDetail(detailJson.data || []);
      } else {
        throw new Error('Error al cargar datos en vivo de hoy.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setTodayLoading(false);
    }
  }, [selectedArea, getHeaders]);

  // Load Period Data
  const loadPeriodData = useCallback(async () => {
    if (!fechaInicio || !fechaFin) return;
    setPeriodLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        area: selectedArea,
        horario: selectedHorario
      });
      const res = await fetch(`${API_BASE_URL}/dashboard/analytics/?${params.toString()}`, {
        headers: getHeaders()
      });
      if (res.ok) {
        const json = await res.json();
        setPeriodData(json.data || null);
      } else {
        throw new Error('Error al cargar métricas analíticas del período.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setPeriodLoading(false);
    }
  }, [fechaInicio, fechaFin, selectedArea, selectedHorario, getHeaders]);

  // Load data based on selected tab and filters
  useEffect(() => {
    if (activeTab === 'hoy') {
      loadTodayData();
    } else {
      loadPeriodData();
    }
  }, [activeTab, selectedArea, selectedHorario, fechaInicio, fechaFin, loadTodayData, loadPeriodData]);

  return (
    <div className="container-fluid p-0">
      {/* Top Filter and Tab Selection Bar */}
      <div className="filter-bar d-flex flex-wrap justify-content-between align-items-center mb-4 bg-white p-3 rounded border border-light shadow-sm gap-3">
        <div className="d-flex align-items-center gap-2">
          {/* Segmented Control Tabs */}
          <div className="btn-group p-1 bg-light rounded" style={{ padding: '3px !important' }}>
            <button
              onClick={() => setActiveTab('hoy')}
              className={`btn btn-sm rounded ${activeTab === 'hoy' ? 'btn-white bg-white shadow-sm font-semibold' : 'btn-link text-muted border-0'}`}
              type="button"
              style={{ fontWeight: activeTab === 'hoy' ? '600' : '400' }}
            >
              <i className="bi bi-clock-history me-1"></i> Hoy
            </button>
            <button
              onClick={() => setActiveTab('periodo')}
              className={`btn btn-sm rounded ${activeTab === 'periodo' ? 'btn-white bg-white shadow-sm font-semibold' : 'btn-link text-muted border-0'}`}
              type="button"
              style={{ fontWeight: activeTab === 'periodo' ? '600' : '400' }}
            >
              <i className="bi bi-calendar3 me-1"></i> Análisis Período
            </button>
          </div>
        </div>

        {/* Global Filters */}
        <div className="d-flex flex-wrap align-items-center gap-3">
          <div className="filter-group">
            <label className="fw-bold small text-muted mb-1 block">
              <i className="bi bi-geo-alt me-1"></i> Área
            </label>
            <select
              value={selectedArea}
              onChange={(e) => setSelectedArea(e.target.value)}
              className="form-select form-select-sm"
              style={{ minWidth: '150px' }}
            >
              <option value="Todas">Todas las Áreas</option>
              {areasList.map((a, i) => (
                <option key={i} value={a.area}>{a.area}</option>
              ))}
            </select>
          </div>

          {activeTab === 'periodo' && (
            <>
              <div className="filter-group">
                <label className="fw-bold small text-muted mb-1 block">
                  <i className="bi bi-person-badge me-1"></i> Turno
                </label>
                <select
                  value={selectedHorario}
                  onChange={(e) => setSelectedHorario(e.target.value)}
                  className="form-select form-select-sm"
                  style={{ minWidth: '150px' }}
                >
                  <option value="Todos">Todos los Turnos</option>
                  {horariosList.map((t) => (
                    <option key={t.id} value={t.id}>{t.nombre}</option>
                  ))}
                </select>
              </div>

              <div className="filter-group">
                <label className="fw-bold small text-muted mb-1 block">
                  <i className="bi bi-calendar-event me-1"></i> Desde
                </label>
                <input
                  type="date"
                  value={fechaInicio}
                  onChange={(e) => setFechaInicio(e.target.value)}
                  className="form-control form-control-sm"
                  style={{ maxWidth: '140px' }}
                />
              </div>

              <div className="filter-group">
                <label className="fw-bold small text-muted mb-1 block">
                  <i className="bi bi-calendar-check me-1"></i> Hasta
                </label>
                <input
                  type="date"
                  value={fechaFin}
                  onChange={(e) => setFechaFin(e.target.value)}
                  className="form-control form-control-sm"
                  style={{ maxWidth: '140px' }}
                />
              </div>
            </>
          )}

          {/* Manual Refresh Button */}
          <button
            onClick={activeTab === 'hoy' ? loadTodayData : loadPeriodData}
            className="btn btn-outline-secondary btn-sm rounded-circle d-flex align-items-center justify-content-center"
            style={{ width: '31px', height: '31px', marginTop: '19px' }}
            type="button"
            title="Refrescar datos"
          >
            <i className={`bi bi-arrow-clockwise ${(todayLoading || periodLoading) ? 'spin' : ''}`}></i>
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger d-flex align-items-center mb-4 rounded border border-danger-subtle p-3" role="alert">
          <i className="bi bi-exclamation-triangle-fill me-2 fs-5"></i>
          <div>{error}</div>
        </div>
      )}

      {/* Tab Contents */}
      {activeTab === 'hoy' ? (
        <TabHoy
          pulse={todayPulse}
          detail={todayDetail}
          loading={todayLoading}
          onRefresh={loadTodayData}
        />
      ) : (
        <TabPeriodo
          data={periodData}
          loading={periodLoading}
          onRefresh={loadPeriodData}
        />
      )}
    </div>
  );
}

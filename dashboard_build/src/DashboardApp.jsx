import React, { useState, useEffect, useCallback, useRef } from 'react';
import TabHoy from './TabHoy';
import TabPeriodo from './TabPeriodo';
import { DX_CSS } from './styles';
import { ErrorBoundary, Seg, horaActual } from './ui';

const API_BASE_URL = '/api';

// Inyecta los estilos una sola vez (el bundle es un único .js, no hay hoja aparte)
function useDashboardStyles() {
  useEffect(() => {
    if (document.getElementById('dx-styles')) return;
    const el = document.createElement('style');
    el.id = 'dx-styles';
    el.textContent = DX_CSS;
    document.head.appendChild(el);
  }, []);
}

function Dashboard() {
  useDashboardStyles();

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
  const [updatedAt, setUpdatedAt] = useState(null);

  // Evita que una respuesta lenta pise a una más nueva (cambios rápidos de filtro)
  const reqId = useRef(0);

  const getHeaders = useCallback(() => {
    const token = localStorage.getItem('access_token');
    return {
      'Content-Type': 'application/json',
      Authorization: token ? `Bearer ${token}` : '',
    };
  }, []);

  // Áreas del filtro
  useEffect(() => {
    async function fetchAreas() {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) return;
        const res = await fetch(`${API_BASE_URL}/empleados/stats/`, { headers: getHeaders() });
        if (res.ok) {
          const stats = await res.json();
          setAreasList(Array.isArray(stats && stats.areas) ? stats.areas : []);
        }
      } catch (err) {
        console.error('Error fetching areas filter:', err);
      }
    }
    fetchAreas();
  }, [getHeaders]);

  // Turnos según el área elegida
  useEffect(() => {
    async function fetchTurnos() {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) return;
        const areaParam = selectedArea === 'Todas' ? '' : `?area=${encodeURIComponent(selectedArea)}`;
        const res = await fetch(`${API_BASE_URL}/turnos/${areaParam}`, { headers: getHeaders() });
        if (res.ok) {
          const turnos = await res.json();
          setHorariosList(Array.isArray(turnos) ? turnos : []);
          setSelectedHorario('Todos');
        }
      } catch (err) {
        console.error('Error fetching turnos filter:', err);
      }
    }
    fetchTurnos();
  }, [selectedArea, getHeaders]);

  // Fechas del período activo del área
  useEffect(() => {
    async function loadActivePeriod() {
      if (activeTab === 'hoy') return;
      try {
        const areaName = selectedArea || 'Todas';
        const res = await fetch(`${API_BASE_URL}/configuracion/periodos/activo/${encodeURIComponent(areaName)}/`, { headers: getHeaders() });
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

  const loadTodayData = useCallback(async () => {
    const mine = ++reqId.current;
    setTodayLoading(true);
    setError(null);
    try {
      const areaParam = selectedArea !== 'Todas' ? `?area=${encodeURIComponent(selectedArea)}` : '';
      const [pulseRes, detailRes] = await Promise.all([
        fetch(`${API_BASE_URL}/dashboard/pulse/${areaParam}`, { headers: getHeaders() }),
        fetch(`${API_BASE_URL}/dashboard/pulse/detail/${areaParam}`, { headers: getHeaders() }),
      ]);
      if (!(pulseRes.ok && detailRes.ok)) throw new Error('No se pudieron cargar los datos en vivo de hoy.');
      const pulseJson = await pulseRes.json();
      const detailJson = await detailRes.json();
      if (mine !== reqId.current) return;
      setTodayPulse((pulseJson && pulseJson.data) || null);
      setTodayDetail(Array.isArray(detailJson && detailJson.data) ? detailJson.data : []);
      setUpdatedAt(new Date());
    } catch (err) {
      if (mine === reqId.current) setError(err.message);
    } finally {
      if (mine === reqId.current) setTodayLoading(false);
    }
  }, [selectedArea, getHeaders]);

  const loadPeriodData = useCallback(async () => {
    if (!fechaInicio || !fechaFin) return;
    const mine = ++reqId.current;
    setPeriodLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ fecha_inicio: fechaInicio, fecha_fin: fechaFin, area: selectedArea, horario: selectedHorario });
      const res = await fetch(`${API_BASE_URL}/dashboard/analytics/?${params.toString()}`, { headers: getHeaders() });
      if (!res.ok) throw new Error('No se pudieron cargar las métricas del período.');
      const json = await res.json();
      if (mine !== reqId.current) return;
      setPeriodData((json && json.data) || null);
      setUpdatedAt(new Date());
    } catch (err) {
      if (mine === reqId.current) setError(err.message);
    } finally {
      if (mine === reqId.current) setPeriodLoading(false);
    }
  }, [fechaInicio, fechaFin, selectedArea, selectedHorario, getHeaders]);

  useEffect(() => {
    if (activeTab === 'hoy') loadTodayData();
    else loadPeriodData();
  }, [activeTab, selectedArea, selectedHorario, fechaInicio, fechaFin, loadTodayData, loadPeriodData]);

  const busy = todayLoading || periodLoading;
  const refresh = activeTab === 'hoy' ? loadTodayData : loadPeriodData;

  return (
    <div className="dx">
      <div className="dx-bar">
        <Seg
          value={activeTab}
          onChange={setActiveTab}
          label="Vista del dashboard"
          options={[{ value: 'hoy', label: 'Hoy' }, { value: 'periodo', label: 'Análisis del período' }]}
        />

        <div className="dx-filters">
          <label className="dx-field">
            <span>Área</span>
            <select
              id="dash-global-area-select"
              className="dx-input"
              aria-label="Área"
              value={selectedArea}
              onChange={(e) => setSelectedArea(e.target.value)}
            >
              <option value="Todas">Todas las áreas</option>
              {areasList.map((a, i) => (
                <option key={i} value={a.area}>{a.area}</option>
              ))}
            </select>
          </label>

          {activeTab === 'periodo' && (
            <>
              <label className="dx-field">
                <span>Turno</span>
                <select
                  id="dash-global-turno-select"
                  className="dx-input"
                  aria-label="Turno"
                  value={selectedHorario}
                  onChange={(e) => setSelectedHorario(e.target.value)}
                >
                  <option value="Todos">Todos los turnos</option>
                  {horariosList.map((t) => (
                    <option key={t.id} value={t.id}>{t.nombre}</option>
                  ))}
                </select>
              </label>
              <label className="dx-field">
                <span>Desde</span>
                <input id="dash-fecha-inicio-input" className="dx-input" type="date" aria-label="Fecha desde" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} />
              </label>
              <label className="dx-field">
                <span>Hasta</span>
                <input id="dash-fecha-fin-input" className="dx-input" type="date" aria-label="Fecha hasta" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} />
              </label>
            </>
          )}

          <div className={`dx-field ${activeTab === 'periodo' ? 'dx-wide' : ''}`}>
            <span className="dx-stamp" style={{ minHeight: 16 }}>{updatedAt ? `Actualizado ${horaActual(updatedAt)}` : ' '}</span>
            <button type="button" className="dx-iconbtn" onClick={refresh} aria-label="Actualizar datos del dashboard" title="Actualizar datos">
              <i className={`bi bi-arrow-clockwise ${busy ? 'dx-spin' : ''}`} aria-hidden="true" />
              Actualizar
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="dx-alert" role="alert">
          <i className="bi bi-exclamation-triangle-fill" aria-hidden="true" />
          <div><b>No se pudo actualizar</b>{error}</div>
          <button type="button" className="dx-iconbtn" onClick={refresh}>Reintentar</button>
        </div>
      )}

      <ErrorBoundary key={activeTab}>
        {activeTab === 'hoy' ? (
          <TabHoy pulse={todayPulse} detail={todayDetail} loading={todayLoading} />
        ) : (
          <TabPeriodo data={periodData} loading={periodLoading} />
        )}
      </ErrorBoundary>
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

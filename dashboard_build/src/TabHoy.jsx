import React, { useState } from 'react';

export default function TabHoy({ pulse, detail, loading }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('todos');
  const [selectedArea, setSelectedArea] = useState('Todas');

  if (loading && !pulse) {
    return (
      <div className="d-flex justify-content-center align-items-center py-5">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando...</span>
        </div>
      </div>
    );
  }

  // Get distinct areas from today's details for local filtering
  const areas = ['Todas', ...new Set(detail.map(d => d.area).filter(Boolean))];

  // Helper to classify row status
  const getRowStatus = (item) => {
    const estado = (item.estado || '').toUpperCase().trim();
    if (item.hora_entrada_real) {
      if (item.minutos_atraso > 0) return 'ATRASO';
      return 'OK';
    }
    // Si no ha entrado
    if (estado === 'INASISTENCIA' || estado.includes('FALTA')) {
      return 'AUSENTE';
    }
    if (estado === 'EN_CURSO') {
      return 'EN_CURSO';
    }
    if (item.hora_entrada_teorica) {
      // Si ya pasó el horario y no hay marca, y no tiene justificación
      return 'INASISTENCIA';
    }
    return estado || 'SIN MARCA';
  };

  // Filter details
  const filteredDetail = detail.filter(item => {
    const matchesSearch = item.empleado.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesArea = selectedArea === 'Todas' || item.area === selectedArea;
    
    const status = getRowStatus(item);
    let matchesStatus = true;
    if (statusFilter === 'presentes') {
      matchesStatus = !!item.hora_entrada_real;
    } else if (statusFilter === 'atrasos') {
      matchesStatus = item.hora_entrada_real && item.minutos_atraso > 0;
    } else if (statusFilter === 'ausentes') {
      matchesStatus = !item.hora_entrada_real && (status === 'AUSENTE' || status === 'INASISTENCIA');
    } else if (statusFilter === 'otros') {
      matchesStatus = !item.hora_entrada_real && status !== 'AUSENTE' && status !== 'INASISTENCIA';
    }

    return matchesSearch && matchesArea && matchesStatus;
  });

  return (
    <div>
      {/* Live Pulse KPI Cards */}
      <div className="row g-3 mb-4">
        {/* Attendance Rate Card */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">TASA DE ASISTENCIA</span>
              <span className="badge bg-success-subtle text-success rounded-pill px-2 py-1">En Vivo</span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{pulse?.tasa_asistencia ?? 0}%</h3>
            </div>
            <p className="text-muted small mt-2 mb-0">Asistencia real sobre personal esperado</p>
          </div>
        </div>

        {/* Expected vs Present Card */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">PERSONAL HOY</span>
              <span className="badge bg-primary-subtle text-primary rounded-pill px-2 py-1">Turno {pulse?.turno_actual ?? 'N/A'}</span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{pulse?.presentes ?? 0} <span className="fs-5 text-muted fw-normal">/ {pulse?.esperados ?? 0}</span></h3>
            </div>
            <p className="text-muted small mt-2 mb-0">Presentes frente a dotación esperada</p>
          </div>
        </div>

        {/* Late Arrivals Card */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">ATRASOS DETECTADOS</span>
              <span className="badge bg-warning-subtle text-warning rounded-pill px-2 py-1">Entrada</span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{pulse?.atrasos ?? 0}</h3>
            </div>
            <p className="text-muted small mt-2 mb-0">Colaboradores ingresados fuera de horario</p>
          </div>
        </div>

        {/* Active Alerts Card */}
        <div className="col-12 col-md-3">
          <div className="card h-100 bg-white border border-light shadow-sm rounded p-3">
            <div className="d-flex align-items-center justify-content-between mb-2">
              <span className="text-muted small fw-bold">ALERTAS ACTIVAS</span>
              <span className="badge bg-danger-subtle text-danger rounded-pill px-2 py-1">En Curso</span>
            </div>
            <div className="d-flex align-items-baseline gap-2">
              <h3 className="mb-0 fw-bold text-dark">{pulse?.alertas_en_curso ?? 0}</h3>
            </div>
            <p className="text-muted small mt-2 mb-0">Turnos iniciados pendientes de cierre</p>
          </div>
        </div>
      </div>

      {/* Today Detail Interactive Section */}
      <div className="card bg-white border border-light shadow-sm rounded mb-4">
        <div className="card-header bg-white border-bottom border-light p-3 d-flex flex-wrap justify-content-between align-items-center gap-3">
          <h5 className="mb-0 fw-bold text-dark">
            <i className="bi bi-people-fill text-muted me-2"></i>
            Estado de Asistencia y Dotación Hoy
          </h5>

          {/* Status Filter Chips */}
          <div className="d-flex gap-2">
            <button
              onClick={() => setStatusFilter('todos')}
              className={`btn btn-sm rounded-pill px-3 ${statusFilter === 'todos' ? 'btn-secondary text-white' : 'btn-outline-secondary'}`}
              type="button"
            >
              Todos ({detail.length})
            </button>
            <button
              onClick={() => setStatusFilter('presentes')}
              className={`btn btn-sm rounded-pill px-3 ${statusFilter === 'presentes' ? 'btn-success text-white' : 'btn-outline-success'}`}
              type="button"
            >
              Presentes ({detail.filter(d => d.hora_entrada_real).length})
            </button>
            <button
              onClick={() => setStatusFilter('atrasos')}
              className={`btn btn-sm rounded-pill px-3 ${statusFilter === 'atrasos' ? 'btn-warning text-white' : 'btn-outline-warning'}`}
              type="button"
            >
              Atrasos ({detail.filter(d => d.hora_entrada_real && d.minutos_atraso > 0).length})
            </button>
            <button
              onClick={() => setStatusFilter('ausentes')}
              className={`btn btn-sm rounded-pill px-3 ${statusFilter === 'ausentes' ? 'btn-danger text-white' : 'btn-outline-danger'}`}
              type="button"
            >
              Faltas/Ausentes ({detail.filter(d => !d.hora_entrada_real && (getRowStatus(d) === 'AUSENTE' || getRowStatus(d) === 'INASISTENCIA')).length})
            </button>
          </div>
        </div>

        <div className="card-body p-3">
          {/* Sub-Filters: Search and Area filter */}
          <div className="row g-3 mb-3">
            <div className="col-12 col-md-8">
              <div className="input-group input-group-sm">
                <span className="input-group-text bg-light border-light text-muted">
                  <i className="bi bi-search"></i>
                </span>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="form-control border-light bg-light"
                  placeholder="Buscar colaborador por nombre..."
                />
              </div>
            </div>
            <div className="col-12 col-md-4">
              <select
                value={selectedArea}
                onChange={(e) => setSelectedArea(e.target.value)}
                className="form-select form-select-sm border-light bg-light"
              >
                <option value="Todas">Filtrar por Área (Todas)</option>
                {areas.filter(a => a !== 'Todas').map((a, i) => (
                  <option key={i} value={a}>{a}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Table list */}
          <div className="table-responsive rounded border border-light">
            <table className="table table-hover align-middle mb-0" style={{ fontSize: '0.85rem' }}>
              <thead className="table-light text-muted">
                <tr>
                  <th className="py-2 px-3">Colaborador</th>
                  <th className="py-2">Área</th>
                  <th className="py-2 text-center">Horario Teórico</th>
                  <th className="py-2 text-center">Entrada Real</th>
                  <th className="py-2 text-center">Atraso</th>
                  <th className="py-2 text-end px-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan="6" className="text-center py-4">
                      <div className="spinner-border spinner-border-sm text-secondary me-2" role="status"></div>
                      Cargando detalles...
                    </td>
                  </tr>
                )}
                {!loading && filteredDetail.length === 0 && (
                  <tr>
                    <td colSpan="6" className="text-center py-4 text-muted">
                      No se encontraron colaboradores para los filtros seleccionados.
                    </td>
                  </tr>
                )}
                {!loading && filteredDetail.map((item, idx) => {
                  const status = getRowStatus(item);
                  let statusBadge = '';
                  
                  if (status === 'OK') {
                    statusBadge = <span className="badge bg-success-subtle text-success rounded px-2 py-1">Puntual</span>;
                  } else if (status === 'ATRASO') {
                    statusBadge = <span className="badge bg-warning-subtle text-warning rounded px-2 py-1">Atraso</span>;
                  } else if (status === 'AUSENTE' || status === 'INASISTENCIA') {
                    statusBadge = <span className="badge bg-danger-subtle text-danger rounded px-2 py-1">Ausente</span>;
                  } else if (status === 'EN_CURSO') {
                    statusBadge = <span className="badge bg-info-subtle text-info rounded px-2 py-1">En Turno</span>;
                  } else {
                    statusBadge = <span className="badge bg-secondary-subtle text-secondary rounded px-2 py-1">{status}</span>;
                  }

                  return (
                    <tr key={idx}>
                      <td className="fw-semibold text-dark py-2 px-3">{item.empleado}</td>
                      <td className="text-muted">{item.area}</td>
                      <td className="text-center fw-mono">{item.hora_entrada_teorica ? item.hora_entrada_teorica.substring(0, 5) : '-'}</td>
                      <td className="text-center fw-mono">{item.hora_entrada_real ? item.hora_entrada_real.substring(0, 5) : '-'}</td>
                      <td className="text-center">
                        {item.hora_entrada_real && item.minutos_atraso > 0 ? (
                          <span className="text-warning fw-semibold">+{item.minutos_atraso} min</span>
                        ) : '-'}
                      </td>
                      <td className="text-end px-3">{statusBadge}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

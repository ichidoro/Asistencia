/**
 * LlavesModule — Módulo de Entrega de Llaves
 * IIFE pattern siguiendo Articulo22Module / VisitasModule
 */
const LlavesModule = (() => {
    let _initialized = false;

    async function initTab() {
        const container = document.getElementById('llaves-container');
        if (!container) return;
        
        container.innerHTML = `
            <style>
                .llaves-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 16px; }
                .llaves-kpi { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
                .llaves-kpi-item { flex: 1; min-width: 120px; padding: 16px; border-radius: 10px; text-align: center; }
                .llaves-kpi-item .kpi-value { font-size: 2rem; font-weight: 700; }
                .llaves-kpi-item .kpi-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; opacity: 0.7; }
                .llave-row { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #f0f0f0; transition: background 0.2s; }
                .llave-row:hover { background: #f8f9fa; }
                .llave-estado { padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
                .llave-disponible { background: #d4edda; color: #155724; }
                .llave-entregada { background: #f8d7da; color: #721c24; }
                .llaves-section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
                .llaves-tabs { display: flex; gap: 0; border-bottom: 2px solid #e9ecef; margin-bottom: 20px; }
                .llaves-tab-btn { padding: 10px 20px; border: none; background: none; font-weight: 500; color: #6c757d; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
                .llaves-tab-btn.active { color: #0d6efd; border-bottom-color: #0d6efd; font-weight: 600; }
                .llaves-tab-btn:hover { color: #0d6efd; }
                .llaves-section { display: none; }
                .llaves-section.active { display: block; }
            </style>
            
            <div class="llaves-kpi" id="llaves-kpis">
                <div class="llaves-kpi-item" style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9)">
                    <div class="kpi-value" id="kpi-total">-</div>
                    <div class="kpi-label">Total Llaves</div>
                </div>
                <div class="llaves-kpi-item" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb)">
                    <div class="kpi-value" id="kpi-disponibles">-</div>
                    <div class="kpi-label">Disponibles</div>
                </div>
                <div class="llaves-kpi-item" style="background:linear-gradient(135deg,#fce4ec,#f8bbd0)">
                    <div class="kpi-value" id="kpi-fuera">-</div>
                    <div class="kpi-label">Entregadas</div>
                </div>
            </div>

            <div class="llaves-tabs">
                <button class="llaves-tab-btn active" onclick="LlavesModule.showSection('estado')">📊 Estado Actual</button>
                <button class="llaves-tab-btn" onclick="LlavesModule.showSection('catalogo')">🗝️ Catálogo</button>
                <button class="llaves-tab-btn" onclick="LlavesModule.showSection('historial')">📋 Historial</button>
            </div>

            <div id="seccion-estado" class="llaves-section active">
                <div class="llaves-card">
                    <div id="llaves-estado-lista">Cargando...</div>
                </div>
            </div>

            <div id="seccion-catalogo" class="llaves-section">
                <div class="llaves-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                        <div class="llaves-section-title">🗝️ Catálogo de Llaves</div>
                        <button class="btn btn-primary btn-sm" onclick="LlavesModule.mostrarFormLlave()"><i class="bi bi-plus-lg me-1"></i>Nueva Llave</button>
                    </div>
                    <div id="form-llave-container" style="display:none;margin-bottom:16px;padding:16px;background:#f8f9fa;border-radius:8px">
                        <input type="hidden" id="llave-edit-id">
                        <div class="row g-2">
                            <div class="col-md-5"><input type="text" class="form-control" id="llave-nombre" placeholder="Nombre de la llave"></div>
                            <div class="col-md-5"><input type="text" class="form-control" id="llave-ubicacion" placeholder="Ubicación / Qué abre"></div>
                            <div class="col-md-2 d-flex gap-1">
                                <button class="btn btn-success btn-sm flex-fill" onclick="LlavesModule.guardarLlave()"><i class="bi bi-check-lg"></i></button>
                                <button class="btn btn-secondary btn-sm" onclick="LlavesModule.cancelarFormLlave()"><i class="bi bi-x-lg"></i></button>
                            </div>
                        </div>
                    </div>
                    <div id="llaves-catalogo-lista">Cargando...</div>
                </div>
            </div>

            <div id="seccion-historial" class="llaves-section">
                <div class="llaves-card">
                    <div class="llaves-section-title">📋 Historial de Movimientos</div>
                    <div class="row g-2 mb-3">
                        <div class="col-md-3"><input type="date" class="form-control form-control-sm" id="hist-fecha-desde"></div>
                        <div class="col-md-3"><input type="date" class="form-control form-control-sm" id="hist-fecha-hasta"></div>
                        <div class="col-md-3"><select class="form-select form-select-sm" id="hist-llave-filter"><option value="">Todas las llaves</option></select></div>
                        <div class="col-md-3"><button class="btn btn-primary btn-sm w-100" onclick="LlavesModule.cargarHistorial()"><i class="bi bi-search me-1"></i>Buscar</button></div>
                    </div>
                    <div id="llaves-historial-tabla">Cargando...</div>
                    <div id="llaves-historial-paginacion" class="d-flex justify-content-center mt-3"></div>
                </div>
            </div>
        `;

        // Set default dates
        const hoy = new Date().toISOString().slice(0, 10);
        const hace30 = new Date(Date.now() - 30*24*60*60*1000).toISOString().slice(0, 10);
        document.getElementById('hist-fecha-desde').value = hace30;
        document.getElementById('hist-fecha-hasta').value = hoy;

        await cargarEstado();
        _initialized = true;
    }

    function showSection(name) {
        document.querySelectorAll('.llaves-section').forEach(s => s.classList.remove('active'));
        document.querySelectorAll('.llaves-tab-btn').forEach(b => b.classList.remove('active'));
        document.getElementById(`seccion-${name}`).classList.add('active');
        event.target.classList.add('active');
        if (name === 'catalogo') cargarCatalogo();
        if (name === 'historial') { cargarFiltroLlaves(); cargarHistorial(); }
    }

    async function cargarEstado() {
        try {
            const token = localStorage.getItem('auth_token');
            const r = await fetch('/api/llaves/estado/', { headers: { 'Authorization': `Bearer ${token}` }});
            const data = await r.json();
            document.getElementById('kpi-total').textContent = data.total;
            document.getElementById('kpi-disponibles').textContent = data.disponibles;
            document.getElementById('kpi-fuera').textContent = data.fuera;
            
            const lista = document.getElementById('llaves-estado-lista');
            if (!data.llaves.length) {
                lista.innerHTML = '<div class="text-center text-muted py-4">No hay llaves registradas. Agrega llaves en el Catálogo.</div>';
                return;
            }
            lista.innerHTML = data.llaves.map(ll => `
                <div class="llave-row">
                    <div style="flex:1">
                        <div style="font-weight:600">🔑 ${ll.nombre}</div>
                        <div style="font-size:0.85rem;color:#6c757d">📍 ${ll.ubicacion}</div>
                    </div>
                    <div style="flex:1;text-align:center">
                        ${ll.estado === 'DISPONIBLE' 
                            ? '<span class="llave-estado llave-disponible">✅ Disponible</span>'
                            : `<span class="llave-estado llave-entregada">🔴 ${ll.entregada_a.nombre}</span>
                               <div style="font-size:0.75rem;color:#6c757d;margin-top:2px">${ll.entregada_hora}</div>`
                        }
                    </div>
                    <div style="width:120px;text-align:right">
                        ${ll.estado === 'DISPONIBLE'
                            ? `<button class="btn btn-success btn-sm" onclick="LlavesModule.abrirEntrega(${ll.id}, '${ll.nombre.replace(/'/g, "\\'")}')">
                                <i class="bi bi-box-arrow-right me-1"></i>Entregar</button>`
                            : `<button class="btn btn-warning btn-sm" onclick="LlavesModule.confirmarDevolucion(${ll.id}, '${ll.nombre.replace(/'/g, "\\'")}', ${ll.entregada_a.id}, '${ll.entregada_a.nombre.replace(/'/g, "\\'")}')">
                                <i class="bi bi-box-arrow-in-left me-1"></i>Devolver</button>`
                        }
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error('Error cargando estado llaves:', e);
        }
    }

    async function abrirEntrega(llaveId, llaveNombre) {
        try {
            const token = localStorage.getItem('auth_token');
            const r = await fetch('/api/llaves/autorizados/', { headers: { 'Authorization': `Bearer ${token}` }});
            const empleados = await r.json();
            if (!empleados.length) {
                Swal.fire('Sin autorizados', 'No hay empleados autorizados en tus áreas asignadas.', 'warning');
                return;
            }
            // Build options HTML
            const optsHtml = empleados.map(e => `<option value="${e.id}">${e.nombre} — ${e.area}</option>`).join('');
            const { value: formValues } = await Swal.fire({
                title: `🔑 Entregar: ${llaveNombre}`,
                html: `
                    <div style="text-align:left">
                        <label class="form-label fw-bold">Empleado autorizado:</label>
                        <select id="swal-empleado" class="form-select">${optsHtml}</select>
                        <label class="form-label fw-bold mt-3">Observaciones:</label>
                        <input id="swal-obs" class="form-control" placeholder="Opcional">
                    </div>
                `,
                focusConfirm: false,
                showCancelButton: true,
                confirmButtonText: 'Confirmar Entrega',
                cancelButtonText: 'Cancelar',
                confirmButtonColor: '#198754',
                preConfirm: () => ({
                    empleado_id: parseInt(document.getElementById('swal-empleado').value),
                    observaciones: document.getElementById('swal-obs').value
                })
            });
            if (!formValues) return;
            const resp = await fetch('/api/llaves/registrar/', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ llave_id: llaveId, empleado_id: formValues.empleado_id, tipo: 'ENTREGA', observaciones: formValues.observaciones })
            });
            const result = await resp.json();
            if (resp.ok) {
                Swal.fire({ icon: 'success', title: 'Entrega registrada', text: result.message, timer: 2000, showConfirmButton: false });
                await cargarEstado();
            } else {
                Swal.fire('Error', result.detail || 'Error al registrar', 'error');
            }
        } catch (e) {
            console.error('Error en entrega:', e);
            Swal.fire('Error', 'Error de conexión', 'error');
        }
    }

    async function confirmarDevolucion(llaveId, llaveNombre, empleadoId, empleadoNombre) {
        const result = await Swal.fire({
            title: '¿Confirmar devolución?',
            html: `<div style="text-align:left"><p><strong>🔑 ${llaveNombre}</strong></p><p>👤 ${empleadoNombre}</p><label class="form-label mt-2">Observaciones:</label><input id="swal-obs-dev" class="form-control" placeholder="Opcional"></div>`,
            showCancelButton: true,
            confirmButtonText: 'Confirmar Devolución',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#ffc107'
        });
        if (!result.isConfirmed) return;
        try {
            const token = localStorage.getItem('auth_token');
            const resp = await fetch('/api/llaves/registrar/', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ llave_id: llaveId, empleado_id: empleadoId, tipo: 'DEVOLUCION', observaciones: document.getElementById('swal-obs-dev')?.value || '' })
            });
            const data = await resp.json();
            if (resp.ok) {
                Swal.fire({ icon: 'success', title: 'Devolución registrada', text: data.message, timer: 2000, showConfirmButton: false });
                await cargarEstado();
            } else {
                Swal.fire('Error', data.detail || 'Error al registrar', 'error');
            }
        } catch (e) {
            Swal.fire('Error', 'Error de conexión', 'error');
        }
    }

    // CATALOGO CRUD
    async function cargarCatalogo() {
        try {
            const token = localStorage.getItem('auth_token');
            const r = await fetch('/api/llaves/maestro/', { headers: { 'Authorization': `Bearer ${token}` }});
            const llaves = await r.json();
            const lista = document.getElementById('llaves-catalogo-lista');
            if (!llaves.length) {
                lista.innerHTML = '<div class="text-center text-muted py-4">No hay llaves. Agrega la primera.</div>';
                return;
            }
            lista.innerHTML = `<table class="table table-sm table-hover">
                <thead><tr><th>Nombre</th><th>Ubicación</th><th style="width:100px">Acciones</th></tr></thead>
                <tbody>${llaves.map(ll => `
                    <tr>
                        <td><strong>🔑 ${ll.nombre}</strong></td>
                        <td>${ll.ubicacion}</td>
                        <td>
                            <button class="btn btn-outline-primary btn-sm" onclick="LlavesModule.editarLlave(${ll.id}, '${ll.nombre.replace(/'/g, "\\'")}', '${ll.ubicacion.replace(/'/g, "\\'")}')" title="Editar"><i class="bi bi-pencil"></i></button>
                            <button class="btn btn-outline-danger btn-sm" onclick="LlavesModule.eliminarLlave(${ll.id}, '${ll.nombre.replace(/'/g, "\\'")}')" title="Eliminar"><i class="bi bi-trash"></i></button>
                        </td>
                    </tr>
                `).join('')}</tbody></table>`;
        } catch (e) {
            console.error('Error cargando catálogo:', e);
        }
    }

    function mostrarFormLlave() {
        document.getElementById('form-llave-container').style.display = 'block';
        document.getElementById('llave-edit-id').value = '';
        document.getElementById('llave-nombre').value = '';
        document.getElementById('llave-ubicacion').value = '';
        document.getElementById('llave-nombre').focus();
    }

    function editarLlave(id, nombre, ubicacion) {
        document.getElementById('form-llave-container').style.display = 'block';
        document.getElementById('llave-edit-id').value = id;
        document.getElementById('llave-nombre').value = nombre;
        document.getElementById('llave-ubicacion').value = ubicacion;
        document.getElementById('llave-nombre').focus();
    }

    function cancelarFormLlave() {
        document.getElementById('form-llave-container').style.display = 'none';
    }

    async function guardarLlave() {
        const id = document.getElementById('llave-edit-id').value;
        const nombre = document.getElementById('llave-nombre').value.trim();
        const ubicacion = document.getElementById('llave-ubicacion').value.trim();
        if (!nombre || !ubicacion) { Swal.fire('Campos requeridos', 'Nombre y ubicación son obligatorios', 'warning'); return; }
        const token = localStorage.getItem('auth_token');
        const url = id ? `/api/llaves/maestro/${id}/` : '/api/llaves/maestro/';
        const method = id ? 'PUT' : 'POST';
        try {
            const r = await fetch(url, { method, headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ nombre, ubicacion }) });
            if (r.ok) {
                cancelarFormLlave();
                await cargarCatalogo();
                await cargarEstado();
                Swal.fire({ icon: 'success', title: id ? 'Llave actualizada' : 'Llave creada', timer: 1500, showConfirmButton: false });
            } else {
                const err = await r.json();
                Swal.fire('Error', err.detail || 'Error al guardar', 'error');
            }
        } catch (e) { Swal.fire('Error', 'Error de conexión', 'error'); }
    }

    async function eliminarLlave(id, nombre) {
        const result = await Swal.fire({ title: '¿Eliminar llave?', text: `Se eliminará "${nombre}"`, icon: 'warning', showCancelButton: true, confirmButtonColor: '#dc3545', confirmButtonText: 'Eliminar' });
        if (!result.isConfirmed) return;
        const token = localStorage.getItem('auth_token');
        try {
            await fetch(`/api/llaves/maestro/${id}/`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` }});
            await cargarCatalogo();
            await cargarEstado();
        } catch (e) { Swal.fire('Error', 'Error de conexión', 'error'); }
    }

    // HISTORIAL
    async function cargarFiltroLlaves() {
        try {
            const token = localStorage.getItem('auth_token');
            const r = await fetch('/api/llaves/maestro/', { headers: { 'Authorization': `Bearer ${token}` }});
            const llaves = await r.json();
            const sel = document.getElementById('hist-llave-filter');
            sel.innerHTML = '<option value="">Todas las llaves</option>' + llaves.map(ll => `<option value="${ll.id}">${ll.nombre}</option>`).join('');
        } catch(e) {}
    }

    async function cargarHistorial(page = 1) {
        try {
            const token = localStorage.getItem('auth_token');
            const desde = document.getElementById('hist-fecha-desde').value;
            const hasta = document.getElementById('hist-fecha-hasta').value;
            const llaveId = document.getElementById('hist-llave-filter').value;
            let url = `/api/llaves/historial/?page=${page}`;
            if (desde) url += `&fecha_desde=${desde}`;
            if (hasta) url += `&fecha_hasta=${hasta}`;
            if (llaveId) url += `&llave_id=${llaveId}`;
            const r = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` }});
            const data = await r.json();
            const tabla = document.getElementById('llaves-historial-tabla');
            if (!data.registros.length) {
                tabla.innerHTML = '<div class="text-center text-muted py-4">Sin registros en este período.</div>';
                document.getElementById('llaves-historial-paginacion').innerHTML = '';
                return;
            }
            tabla.innerHTML = `<table class="table table-sm table-hover">
                <thead><tr><th>Fecha</th><th>Hora</th><th>Llave</th><th>Empleado</th><th>Tipo</th><th>Guardia</th><th>Obs.</th></tr></thead>
                <tbody>${data.registros.map(r => `
                    <tr>
                        <td>${r.fecha}</td><td>${r.hora}</td>
                        <td><strong>${r.llave}</strong></td>
                        <td>${r.empleado}</td>
                        <td>${r.tipo === 'ENTREGA' ? '<span class="badge bg-danger">🔴 Entrega</span>' : '<span class="badge bg-success">🟢 Devolución</span>'}</td>
                        <td>${r.guardia}</td>
                        <td>${r.observaciones || '-'}</td>
                    </tr>
                `).join('')}</tbody></table>`;
            // Pagination
            if (data.pages > 1) {
                let pagHtml = '<nav><ul class="pagination pagination-sm">';
                for (let i = 1; i <= data.pages; i++) {
                    pagHtml += `<li class="page-item ${i === data.page ? 'active' : ''}"><a class="page-link" href="#" onclick="event.preventDefault();LlavesModule.cargarHistorial(${i})">${i}</a></li>`;
                }
                pagHtml += '</ul></nav>';
                document.getElementById('llaves-historial-paginacion').innerHTML = pagHtml;
            } else {
                document.getElementById('llaves-historial-paginacion').innerHTML = '';
            }
        } catch (e) {
            console.error('Error cargando historial:', e);
        }
    }

    return {
        initTab, showSection, cargarEstado,
        abrirEntrega, confirmarDevolucion,
        mostrarFormLlave, editarLlave, cancelarFormLlave, guardarLlave, eliminarLlave,
        cargarCatalogo, cargarHistorial
    };
})();

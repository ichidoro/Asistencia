/**
 * Módulo de 4 Productos
 * Controla la visualización, evaluación de empleados, asignación y catálogo.
 */

const Productos4Module = {
    productos: [],
    evaluaciones: [],
    periodoActivo: { mes: new Date().getMonth() + 1, anio: new Date().getFullYear() },

    async init() {
        logger_ui("Iniciando Módulo de 4 Productos...");
        await this.cargarProductos();
        await this.cargarFiltroAreas();
        this.inicializarFiltrosPeriodo();
        await this.cargarEvaluaciones();
    },

    // --- Cargar Catálogo ---
    async cargarProductos() {
        try {
            const response = await fetch('/api/productos-4/productos?incluir_inactivos=true', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!response.ok) throw new Error("Error al obtener catálogo de productos propios.");
            this.productos = await response.json();
        } catch (error) {
            console.error(error);
            showToast("No se pudo cargar el catálogo de productos propios.", "error");
        }
    },

    // --- Cargar Áreas permitidas ---
    async cargarFiltroAreas() {
        const selectArea = document.getElementById('productos-4-filtro-area');
        if (!selectArea) return;

        try {
            let areas = [];
            if (typeof getAreasCache === 'function') {
                areas = await getAreasCache();
            } else {
                const r = await fetch('/api/empleados/stats/', {
                    headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
                });
                if (r.ok) {
                    const stats = await r.json();
                    areas = stats.areas || [];
                }
            }

            selectArea.innerHTML = '<option value="">Todas las Áreas</option>' +
                areas.map(a => `<option value="${a.area}">${a.area}</option>`).join('');

            // RLS: si el usuario solo tiene una área asignada, la preseleccionamos y bloqueamos
            if (areas.length === 1) {
                selectArea.value = areas[0].area;
                selectArea.setAttribute('disabled', 'true');
            }
        } catch (e) {
            console.error("Error cargando filtro de áreas en 4 Productos:", e);
        }
    },

    // --- Filtros de Periodo ---
    inicializarFiltrosPeriodo() {
        const selectMes = document.getElementById('productos-4-filtro-mes');
        const selectAnio = document.getElementById('productos-4-filtro-anio');

        if (selectMes && selectAnio) {
            // Set current period
            selectMes.value = this.periodoActivo.mes;
            selectAnio.value = this.periodoActivo.anio;

            // Bind events
            selectMes.onchange = () => this.cambiarPeriodo();
            selectAnio.onchange = () => this.cambiarPeriodo();
        }
    },

    async cambiarPeriodo() {
        const selectMes = document.getElementById('productos-4-filtro-mes');
        const selectAnio = document.getElementById('productos-4-filtro-anio');
        if (selectMes && selectAnio) {
            this.periodoActivo.mes = parseInt(selectMes.value);
            this.periodoActivo.anio = parseInt(selectAnio.value);
            await this.cargarEvaluaciones();
        }
    },

    // --- Cargar grilla de evaluación ---
    async cargarEvaluaciones() {
        const grid = document.getElementById('productos-4-empleados-grid');
        if (!grid) return;

        // Show spinner
        grid.innerHTML = `
            <div class="col-12 text-center py-5 text-muted">
                <div class="spinner-border text-primary mb-3" role="status"></div>
                <div>Evaluando asistencia y antigüedad de la planilla...</div>
            </div>
        `;

        const areaVal = document.getElementById('productos-4-filtro-area')?.value || "";

        try {
            let url = `/api/productos-4/evaluacion?mes=${this.periodoActivo.mes}&anio=${this.periodoActivo.anio}`;
            if (areaVal) {
                url += `&area=${encodeURIComponent(areaVal)}`;
            }

            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!response.ok) throw new Error("Error al evaluar el periodo.");
            this.evaluaciones = await response.json();
            this.renderizarEvaluaciones();
        } catch (error) {
            grid.innerHTML = `
                <div class="col-12 text-center py-5 text-danger">
                    <i class="bi bi-exclamation-triangle-fill fs-1"></i>
                    <div class="mt-2 fw-bold">No se pudo cargar la planilla del periodo.</div>
                    <div class="small text-muted">${error.message}</div>
                </div>
            `;
        }
    },

    renderizarEvaluaciones() {
        const grid = document.getElementById('productos-4-empleados-grid');
        const searchInput = document.getElementById('productos-4-search');
        const statusFilter = document.getElementById('productos-4-filtro-estado');
        
        if (!grid) return;

        const q = searchInput ? searchInput.value.toLowerCase().trim() : '';
        const estadoFiltro = statusFilter ? statusFilter.value : 'todos';

        // Filtrar evaluaciones
        let filtrados = this.evaluaciones.filter(e => {
            const matchQuery = e.nombre.toLowerCase().includes(q) || e.rut.toLowerCase().includes(q) || e.cargo.toLowerCase().includes(q);
            
            if (estadoFiltro === 'califica') {
                return matchQuery && e.califica === true;
            } else if (estadoFiltro === 'bloqueado') {
                return matchQuery && e.califica === false;
            } else if (estadoFiltro === 'asignado') {
                return matchQuery && e.seleccion !== null;
            } else if (estadoFiltro === 'pendiente') {
                return matchQuery && e.califica === true && e.seleccion === null;
            }
            return matchQuery;
        });

        if (filtrados.length === 0) {
            grid.innerHTML = `
                <div class="col-12 text-center py-5 text-muted">
                    <i class="bi bi-folder-x fs-1"></i>
                    <div class="mt-2">No se encontraron empleados en este periodo con los filtros aplicados.</div>
                </div>
            `;
            return;
        }

        grid.innerHTML = filtrados.map(e => {
            const badge = e.califica 
                ? `<span class="badge bg-success-subtle text-success border border-success-subtle px-2.5 py-1 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i>Califica</span>`
                : `<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2.5 py-1 rounded-pill"><i class="bi bi-lock-fill me-1"></i>Bloqueado</span>`;

            let cardAction = '';
            let seleccionBadge = '';

            if (e.califica) {
                if (e.seleccion) {
                    const prodNombres = this.obtenerNombresProductosAsignados(e.seleccion);
                    seleccionBadge = `
                        <div class="mt-3 p-2 bg-light rounded text-start border border-dashed">
                            <small class="text-muted fw-bold d-block"><i class="bi bi-box-seam me-1"></i>Productos Asignados:</small>
                            <ul class="mb-0 ps-3 small text-secondary">
                                ${prodNombres.map(n => `<li>${n}</li>`).join('')}
                            </ul>
                            ${e.seleccion.observaciones ? `<div class="mt-1 small text-muted font-monospace text-truncate" title="${e.seleccion.observaciones}">Obs: ${e.seleccion.observaciones}</div>` : ''}
                        </div>
                    `;
                    cardAction = `
                        <button class="btn btn-sm btn-outline-primary w-100 mt-3" onclick="Productos4Module.abrirModalAsignacion(${e.empleado_id})">
                            <i class="bi bi-pencil-square me-1"></i> Editar Selección
                        </button>
                    `;
                } else {
                    seleccionBadge = `
                        <div class="mt-3 p-2.5 bg-warning-subtle text-warning-emphasis rounded text-center small">
                            <i class="bi bi-info-circle me-1"></i> Pendiente de asignación.
                        </div>
                    `;
                    cardAction = `
                        <button class="btn btn-sm btn-primary w-100 mt-3" onclick="Productos4Module.abrirModalAsignacion(${e.empleado_id})">
                            <i class="bi bi-gift me-1"></i> Asignar Productos
                        </button>
                    `;
                }
            } else {
                seleccionBadge = `
                    <div class="mt-3 p-2.5 bg-danger-subtle text-danger-emphasis rounded text-start small" style="min-height: 60px;">
                        <i class="bi bi-shield-slash-fill me-1"></i> <strong>Motivo de Bloqueo:</strong>
                        <div class="mt-1 small" style="font-size: 0.72rem; line-height: 1.3;">${e.motivo}</div>
                    </div>
                `;
                cardAction = `
                    <button class="btn btn-sm btn-secondary w-100 mt-3" disabled>
                        <i class="bi bi-slash-circle me-1"></i> Bloqueado
                    </button>
                `;
            }

            return `
                <div class="col-xl-3 col-lg-4 col-md-6">
                    <div class="card h-100 shadow-sm border-0 position-relative transition-all hover-translate-y" style="border-radius: 12px;">
                        <div class="card-body p-3.5 d-flex flex-column justify-content-between">
                            <div>
                                <div class="d-flex justify-content-between align-items-start mb-2">
                                    <div class="small text-muted font-monospace">${e.rut}</div>
                                    ${badge}
                                </div>
                                <h6 class="fw-bold mb-1 text-truncate" title="${e.nombre}">${e.nombre}</h6>
                                <div class="small text-secondary text-truncate mb-1"><i class="bi bi-briefcase me-1"></i>${e.cargo}</div>
                                <div class="small text-secondary text-truncate"><i class="bi bi-geo-alt me-1"></i>${e.area}</div>
                                ${seleccionBadge}
                            </div>
                            <div>
                                ${cardAction}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    obtenerNombresProductosAsignados(seleccion) {
        const list = [];
        const codigos = [seleccion.p1, seleccion.p2, seleccion.p3, seleccion.p4];
        
        codigos.forEach(c => {
            if (c) {
                const prod = this.productos.find(p => p.codigo === c);
                if (prod) {
                    list.push(`${prod.descripcion} (${prod.unidad})`);
                } else {
                    list.push(`Cód. ${c}`);
                }
            }
        });
        
        return list;
    },

    // --- Modal de Asignación ---
    abrirModalAsignacion(empleadoId) {
        const emp = this.evaluaciones.find(e => e.empleado_id === empleadoId);
        if (!emp) return;

        const activeProds = this.productos.filter(p => p.activo);
        if (activeProds.length === 0) {
            Swal.fire({
                title: "Catálogo Vacío",
                text: "No existen productos activos en el catálogo para asignar. Diríjase a Configuración -> Productos Propios para agregar productos.",
                icon: "warning"
            });
            return;
        }

        const sel = emp.seleccion || {};
        const p1Val = sel.p1 || "";
        const p2Val = sel.p2 || "";
        const p3Val = sel.p3 || "";
        const p4Val = sel.p4 || "";
        const obsVal = sel.observaciones || "";

        const selectOptions = `
            <option value="">-- Sin Seleccionar --</option>
            ${activeProds.map(p => `<option value="${p.codigo}">${p.descripcion} (${p.unidad}) [Límit. Max: ${p.max_cantidad}]</option>`).join('')}
        `;

        Swal.fire({
            title: `<span class="fw-bold fs-5">🎁 Asignar Productos a ${emp.nombre}</span>`,
            html: `
                <div class="text-start mt-3">
                    <p class="small text-muted mb-4">Seleccione hasta 4 productos propios. La interfaz validará en tiempo real que no exceda las cantidades máximas definidas por producto.</p>
                    
                    <div class="mb-3">
                        <label for="asig-select-1" class="form-label small fw-bold">Opción 1</label>
                        <select id="asig-select-1" class="form-select form-select-sm asig-prod-select">${selectOptions}</select>
                    </div>
                    
                    <div class="mb-3">
                        <label for="asig-select-2" class="form-label small fw-bold">Opción 2</label>
                        <select id="asig-select-2" class="form-select form-select-sm asig-prod-select">${selectOptions}</select>
                    </div>
                    
                    <div class="mb-3">
                        <label for="asig-select-3" class="form-label small fw-bold">Opción 3</label>
                        <select id="asig-select-3" class="form-select form-select-sm asig-prod-select">${selectOptions}</select>
                    </div>
                    
                    <div class="mb-3">
                        <label for="asig-select-4" class="form-label small fw-bold">Opción 4</label>
                        <select id="asig-select-4" class="form-select form-select-sm asig-prod-select">${selectOptions}</select>
                    </div>

                    <div class="mb-3">
                        <label for="asig-obs" class="form-label small fw-bold">Observaciones / Nota adicional</label>
                        <textarea id="asig-obs" class="form-control form-control-sm" rows="2" placeholder="Ej. Entregado en recepción">${obsVal}</textarea>
                    </div>

                    <div id="asig-validation-alert" class="alert alert-danger d-none py-2 small mb-0 mt-3">
                        <i class="bi bi-exclamation-triangle-fill me-1"></i> <span id="asig-validation-message"></span>
                    </div>
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: '<i class="bi bi-save me-1"></i> Guardar Selección',
            cancelButtonText: 'Cancelar',
            customClass: {
                confirmButton: 'btn btn-primary btn-sm px-3.5',
                cancelButton: 'btn btn-outline-secondary btn-sm px-3.5'
            },
            buttonsStyling: false,
            didOpen: () => {
                // Seleccionar valores previos
                document.getElementById('asig-select-1').value = p1Val;
                document.getElementById('asig-select-2').value = p2Val;
                document.getElementById('asig-select-3').value = p3Val;
                document.getElementById('asig-select-4').value = p4Val;

                // Enlazar listeners para validación reactiva
                const selects = document.querySelectorAll('.asig-prod-select');
                selects.forEach(s => s.addEventListener('change', () => this.validarSeleccionReactiva()));
                this.validarSeleccionReactiva();
            },
            preConfirm: async () => {
                const p1 = document.getElementById('asig-select-1').value;
                const p2 = document.getElementById('asig-select-2').value;
                const p3 = document.getElementById('asig-select-3').value;
                const p4 = document.getElementById('asig-select-4').value;
                const obs = document.getElementById('asig-obs').value;

                const codigos = [p1, p2, p3, p4].filter(c => c !== "").map(c => parseInt(c));
                
                if (codigos.length === 0) {
                    Swal.showValidationMessage("Debe seleccionar al menos un producto.");
                    return false;
                }

                // Validación de límites en cliente antes de POST
                const validacion = this.validarLimitesSeleccion(codigos);
                if (!validacion.ok) {
                    Swal.showValidationMessage(validacion.msg);
                    return false;
                }

                // Realizar POST
                try {
                    Swal.showLoading();
                    const response = await fetch('/api/productos-4/asignaciones', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem('token')}`
                        },
                        body: JSON.stringify({
                            empleado_id: empleadoId,
                            mes: this.periodoActivo.mes,
                            anio: this.periodoActivo.anio,
                            codigos: [
                                p1 ? parseInt(p1) : null,
                                p2 ? parseInt(p2) : null,
                                p3 ? parseInt(p3) : null,
                                p4 ? parseInt(p4) : null
                            ],
                            observaciones: obs
                        })
                    });

                    const res = await response.json();
                    if (!response.ok) throw new Error(res.detail || "Error guardando asignación.");

                    return true;
                } catch (error) {
                    Swal.showValidationMessage(error.message);
                    return false;
                }
            }
        }).then((result) => {
            if (result.isConfirmed) {
                showToast("Asignación guardada con éxito.", "success");
                this.cargarEvaluaciones();
            }
        });
    },

    validarLimitesSeleccion(codigos) {
        const counts = {};
        for (const code of codigos) {
            counts[code] = (counts[code] || 0) + 1;
        }

        for (const code of Object.keys(counts)) {
            const codeInt = parseInt(code);
            const prod = this.productos.find(p => p.codigo === codeInt);
            if (!prod) continue;
            
            if (counts[code] > prod.max_cantidad) {
                return {
                    ok: false,
                    msg: `Supera el límite: '${prod.descripcion}' seleccionado ${counts[code]} veces (Máx: ${prod.max_cantidad}).`
                };
            }
        }

        return { ok: true };
    },

    validarSeleccionReactiva() {
        const p1 = document.getElementById('asig-select-1').value;
        const p2 = document.getElementById('asig-select-2').value;
        const p3 = document.getElementById('asig-select-3').value;
        const p4 = document.getElementById('asig-select-4').value;
        
        const codigos = [p1, p2, p3, p4].filter(c => c !== "").map(c => parseInt(c));
        const alertDiv = document.getElementById('asig-validation-alert');
        const msgSpan = document.getElementById('asig-validation-message');

        const validacion = this.validarLimitesSeleccion(codigos);

        if (!validacion.ok) {
            msgSpan.innerText = validacion.msg;
            alertDiv.classList.remove('d-none');
            // Deshabilitar botón de confirmar Swal
            const confirmBtn = Swal.getConfirmButton();
            if (confirmBtn) confirmBtn.setAttribute('disabled', 'true');
        } else {
            alertDiv.classList.add('d-none');
            const confirmBtn = Swal.getConfirmButton();
            if (confirmBtn) confirmBtn.removeAttribute('disabled');
        }
    },


    // ==========================================
    // SECCIÓN CRUD: Catálogo de Productos
    // ==========================================

    renderizarConfiguracionCatalogo() {
        const container = document.getElementById('tab-productos-propios');
        if (!container) return;

        const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.editar') : true;

        container.innerHTML = `
            <div class="p-3">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <div>
                        <h5 class="fw-bold mb-1"><i class="bi bi-gift-fill text-primary me-2"></i>Catálogo de Productos Propios</h5>
                        <p class="text-muted small mb-0">Gestione los productos fabricados por la empresa disponibles para el beneficio mensual por 100% de asistencia.</p>
                    </div>
                    ${canEdit ? `
                    <button class="btn btn-primary btn-sm px-3" onclick="Productos4Module.abrirModalCrearProducto()">
                        <i class="bi bi-plus-circle me-1"></i> Agregar Producto
                    </button>
                    ` : ''}
                </div>
 
                <div class="table-responsive shadow-sm rounded-3">
                    <table class="table table-hover align-middle mb-0" style="font-size: 0.85rem;">
                        <thead class="table-light">
                            <tr>
                                <th style="width: 80px;">Código</th>
                                <th>Descripción</th>
                                <th>Tipo</th>
                                <th>Marca</th>
                                <th>Formato / Unidad</th>
                                <th class="text-center" style="width: 100px;">Límite Máx.</th>
                                <th class="text-center" style="width: 100px;">Estado</th>
                                ${canEdit ? `<th class="text-center" style="width: 100px;">Acciones</th>` : ''}
                            </tr>
                        </thead>
                        <tbody id="catalogo-productos-tbody">
                            <tr>
                                <td colspan="${canEdit ? 8 : 7}" class="text-center py-4 text-muted">
                                    <div class="spinner-border spinner-border-sm me-2" role="status"></div> Cargando catálogo de productos...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        this.cargarTablaProductos();
    },

    async cargarTablaProductos() {
        await this.cargarProductos();
        const tbody = document.getElementById('catalogo-productos-tbody');
        if (!tbody) return;

        const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.editar') : true;

        if (this.productos.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="${canEdit ? 8 : 7}" class="text-center py-4 text-muted">
                        No hay productos registrados en el catálogo.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = this.productos.map(p => {
            const statusBadge = p.activo 
                ? `<span class="badge bg-success-subtle text-success px-2 py-0.8 rounded-pill small">Activo</span>`
                : `<span class="badge bg-secondary-subtle text-secondary px-2 py-0.8 rounded-pill small">Inactivo</span>`;

            const actionBtn = canEdit 
                ? `<button class="btn btn-sm btn-outline-secondary px-2.5" onclick="Productos4Module.abrirModalEditarProducto(${p.codigo})"><i class="bi bi-pencil"></i></button>`
                : '';

            return `
                <tr class="${!p.activo ? 'opacity-60 bg-light' : ''}">
                    <td class="font-monospace fw-bold text-secondary">${p.codigo}</td>
                    <td class="fw-semibold">${p.descripcion}</td>
                    <td>${p.tipo}</td>
                    <td>${p.marca}</td>
                    <td>${p.unidad}</td>
                    <td class="text-center fw-bold">${p.max_cantidad} uds</td>
                    <td class="text-center">${statusBadge}</td>
                    ${canEdit ? `<td class="text-center">${actionBtn}</td>` : ''}
                </tr>
            `;
        }).join('');
    },

    // --- Modal Crear Producto ---
    abrirModalCrearProducto() {
        Swal.fire({
            title: '<span class="fw-bold fs-5"><i class="bi bi-plus-circle me-1 text-primary"></i> Agregar Producto Propio</span>',
            html: `
                <div class="text-start mt-3">
                    <div class="mb-3">
                        <label for="prod-new-codigo" class="form-label small fw-bold">Código Producto (Único)</label>
                        <input type="number" id="prod-new-codigo" class="form-control form-control-sm" placeholder="Ej. 1302">
                    </div>
                    <div class="mb-3">
                        <label for="prod-new-desc" class="form-label small fw-bold">Descripción / Nombre</label>
                        <input type="text" id="prod-new-desc" class="form-control form-control-sm" placeholder="Ej. AGUA DESTILADA 5 LTS">
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-md-6">
                            <label for="prod-new-tipo" class="form-label small fw-bold">Tipo Producto</label>
                            <input type="text" id="prod-new-tipo" class="form-control form-control-sm" placeholder="Ej. AGUA">
                        </div>
                        <div class="col-md-6">
                            <label for="prod-new-marca" class="form-label small fw-bold">Marca</label>
                            <input type="text" id="prod-new-marca" class="form-control form-control-sm" placeholder="Ej. AGUACOL">
                        </div>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-md-6">
                            <label for="prod-new-unidad" class="form-label small fw-bold">Unidad / Formato</label>
                            <input type="text" id="prod-new-unidad" class="form-control form-control-sm" placeholder="Ej. 5 Lts">
                        </div>
                        <div class="col-md-6">
                            <label for="prod-new-max" class="form-label small fw-bold">Entrega Máxima por Persona</label>
                            <input type="number" id="prod-new-max" class="form-control form-control-sm" value="2" min="1">
                        </div>
                    </div>
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: 'Guardar Producto',
            cancelButtonText: 'Cancelar',
            customClass: {
                confirmButton: 'btn btn-primary btn-sm px-3.5',
                cancelButton: 'btn btn-outline-secondary btn-sm px-3.5'
            },
            buttonsStyling: false,
            preConfirm: async () => {
                const code = document.getElementById('prod-new-codigo').value;
                const desc = document.getElementById('prod-new-desc').value;
                const tipo = document.getElementById('prod-new-tipo').value;
                const marca = document.getElementById('prod-new-marca').value;
                const unidad = document.getElementById('prod-new-unidad').value;
                const max = document.getElementById('prod-new-max').value;

                if (!code || !desc || !tipo || !marca || !unidad || !max) {
                    Swal.showValidationMessage("Todos los campos son obligatorios.");
                    return false;
                }

                try {
                    Swal.showLoading();
                    const response = await fetch('/api/productos-4/productos', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem('token')}`
                        },
                        body: JSON.stringify({
                            codigo: parseInt(code),
                            descripcion: desc,
                            tipo: tipo,
                            marca: marca,
                            unidad: unidad,
                            max_cantidad: parseInt(max),
                            activo: true
                        })
                    });

                    const res = await response.json();
                    if (!response.ok) throw new Error(res.detail || "Error guardando producto.");

                    return true;
                } catch (error) {
                    Swal.showValidationMessage(error.message);
                    return false;
                }
            }
        }).then((result) => {
            if (result.isConfirmed) {
                showToast("Producto agregado al catálogo.", "success");
                this.renderizarConfiguracionCatalogo();
            }
        });
    },

    // --- Modal Editar Producto ---
    abrirModalEditarProducto(codigo) {
        const p = this.productos.find(prod => prod.codigo === codigo);
        if (!p) return;

        Swal.fire({
            title: `<span class="fw-bold fs-5"><i class="bi bi-pencil me-1 text-primary"></i> Editar Producto Propio (${codigo})</span>`,
            html: `
                <div class="text-start mt-3">
                    <div class="mb-3">
                        <label for="prod-edit-desc" class="form-label small fw-bold">Descripción / Nombre</label>
                        <input type="text" id="prod-edit-desc" class="form-control form-control-sm" value="${p.descripcion}">
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-md-6">
                            <label for="prod-edit-tipo" class="form-label small fw-bold">Tipo Producto</label>
                            <input type="text" id="prod-edit-tipo" class="form-control form-control-sm" value="${p.tipo}">
                        </div>
                        <div class="col-md-6">
                            <label for="prod-edit-marca" class="form-label small fw-bold">Marca</label>
                            <input type="text" id="prod-edit-marca" class="form-control form-control-sm" value="${p.marca}">
                        </div>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-md-6">
                            <label for="prod-edit-unidad" class="form-label small fw-bold">Unidad / Formato</label>
                            <input type="text" id="prod-edit-unidad" class="form-control form-control-sm" value="${p.unidad}">
                        </div>
                        <div class="col-md-6">
                            <label for="prod-edit-max" class="form-label small fw-bold">Entrega Máxima por Persona</label>
                            <input type="number" id="prod-edit-max" class="form-control form-control-sm" value="${p.max_cantidad}" min="1">
                        </div>
                    </div>
                    <div class="form-check form-switch mt-3.5">
                        <input class="form-check-input" type="checkbox" role="switch" id="prod-edit-activo" ${p.activo ? 'checked' : ''}>
                        <label class="form-check-label small fw-bold" for="prod-edit-activo">Producto Habilitado / Activo</label>
                    </div>
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: 'Actualizar Producto',
            cancelButtonText: 'Cancelar',
            customClass: {
                confirmButton: 'btn btn-primary btn-sm px-3.5',
                cancelButton: 'btn btn-outline-secondary btn-sm px-3.5'
            },
            buttonsStyling: false,
            preConfirm: async () => {
                const desc = document.getElementById('prod-edit-desc').value;
                const tipo = document.getElementById('prod-edit-tipo').value;
                const marca = document.getElementById('prod-edit-marca').value;
                const unidad = document.getElementById('prod-edit-unidad').value;
                const max = document.getElementById('prod-edit-max').value;
                const activo = document.getElementById('prod-edit-activo').checked;

                if (!desc || !tipo || !marca || !unidad || !max) {
                    Swal.showValidationMessage("Todos los campos son obligatorios.");
                    return false;
                }

                try {
                    Swal.showLoading();
                    const response = await fetch(`/api/productos-4/productos/${codigo}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem('token')}`
                        },
                        body: JSON.stringify({
                            codigo: codigo,
                            descripcion: desc,
                            tipo: tipo,
                            marca: marca,
                            unidad: unidad,
                            max_cantidad: parseInt(max),
                            activo: activo
                        })
                    });

                    const res = await response.json();
                    if (!response.ok) throw new Error(res.detail || "Error actualizando producto.");

                    return true;
                } catch (error) {
                    Swal.showValidationMessage(error.message);
                    return false;
                }
            }
        }).then((result) => {
            if (result.isConfirmed) {
                showToast("Producto actualizado con éxito.", "success");
                this.renderizarConfiguracionCatalogo();
            }
        });
    }
};

// Logger simple para debug en UI
function logger_ui(msg) {
    console.log(`%c[UI-PRODUCTOS-4] ${msg}`, "color: #10b981; font-weight: bold;");
}

/**
 * Módulo de 4 Productos
 * Controla la visualización, evaluación de empleados, asignación, consolidación, entregas y catálogo.
 */

const Productos4Module = {
    productos: [],
    evaluaciones: [],
    periodoActivo: { mes: new Date().getMonth() + 1, anio: new Date().getFullYear() },
    activeTab: 'asignacion',
    areasList: [],

    async init() {
        logger_ui("Iniciando Módulo de 4 Productos...");

        // Cargar periodo activo de la base de datos si está disponible
        try {
            const activeResp = await fetch('/api/configuracion/periodos/activo/', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (activeResp.ok) {
                const activePeriod = await activeResp.json();
                if (activePeriod && activePeriod.fecha_fin) {
                    const dateParts = activePeriod.fecha_fin.split('-');
                    if (dateParts.length === 3) {
                        this.periodoActivo = {
                            mes: parseInt(dateParts[1]),
                            anio: parseInt(dateParts[0])
                        };
                        logger_ui(`Periodo activo cargado de la BD: ${this.periodoActivo.anio}-${this.periodoActivo.mes}`);
                    }
                }
            }
        } catch (err) {
            console.error("Error al cargar periodo activo desde la BD, usando fecha actual:", err);
        }

        await this.cargarProductos();
        await this.cargarFiltroAreas();
        this.inicializarFiltrosPeriodo();

        const canAsignar = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.asignar') : true;
        const canConsolidar = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.consolidar') : true;
        const canEntregar = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.entregar') : true;

        const tabAsig = document.getElementById('tab-p4-asignacion');
        const tabCons = document.getElementById('tab-p4-consolidado');
        const tabEntr = document.getElementById('tab-p4-entrega');

        if (tabAsig) {
            if (!canAsignar) tabAsig.closest('li')?.classList.add('d-none');
            else tabAsig.closest('li')?.classList.remove('d-none');
        }
        if (tabCons) {
            if (!canConsolidar) tabCons.closest('li')?.classList.add('d-none');
            else tabCons.closest('li')?.classList.remove('d-none');
        }
        if (tabEntr) {
            if (!canEntregar) tabEntr.closest('li')?.classList.add('d-none');
            else tabEntr.closest('li')?.classList.remove('d-none');
        }

        let defaultTab = '';
        if (canAsignar) defaultTab = 'asignacion';
        else if (canConsolidar) defaultTab = 'consolidado';
        else if (canEntregar) defaultTab = 'entrega';

        if (defaultTab) {
            this.cambiarTab(defaultTab);
            
            // Activar tab de Bootstrap
            let btn = null;
            if (defaultTab === 'asignacion') btn = tabAsig;
            else if (defaultTab === 'consolidado') btn = tabCons;
            else if (defaultTab === 'entrega') btn = tabEntr;

            if (btn) {
                const triggerEl = document.querySelector(`#${btn.id}`);
                if (triggerEl) {
                    const tabTrigger = new bootstrap.Tab(triggerEl);
                    tabTrigger.show();
                }
            }
        } else {
            const grid = document.getElementById('productos-4-empleados-grid');
            if (grid) {
                grid.innerHTML = `
                    <div class="col-12 text-center py-5 text-warning">
                        <i class="bi bi-shield-lock-fill fs-1"></i>
                        <div class="mt-2 fw-bold">Acceso Denegado</div>
                        <div class="small text-muted">No tiene permisos asignados para este módulo.</div>
                    </div>
                `;
            }
        }
    },

    cambiarTab(tabName) {
        this.activeTab = tabName;
        
        const fBuscar = document.getElementById('filtro-p4-container-buscar');
        const fArea = document.getElementById('filtro-p4-container-area');
        const fEstado = document.getElementById('filtro-p4-container-estado');

        // Mostrar / Ocultar filtros según pestaña
        if (tabName === 'asignacion') {
            if (fBuscar) fBuscar.classList.remove('d-none');
            if (fArea) fArea.classList.remove('d-none');
            if (fEstado) fEstado.classList.remove('d-none');
        } else if (tabName === 'consolidado') {
            if (fBuscar) fBuscar.classList.add('d-none'); // Consolidado es tabular de stock de áreas, no requiere buscador
            if (fArea) fArea.classList.add('d-none');
            if (fEstado) fEstado.classList.add('d-none');
        } else if (tabName === 'entrega') {
            if (fBuscar) fBuscar.classList.remove('d-none'); // Buscar habilitado para checklist de despacho
            if (fArea) fArea.classList.remove('d-none');     // Keep Area filter visible!
            if (fEstado) fEstado.classList.add('d-none');
        }

        // Remover clases active/show previas para evitar superposición
        document.querySelectorAll('#productos-4-tab-content .tab-pane').forEach(el => {
            el.classList.remove('show', 'active');
        });

        // Activar el contenedor correcto en el DOM
        let paneId = 'view-p4-asignacion';
        if (tabName === 'consolidado') paneId = 'view-p4-consolidado';
        else if (tabName === 'entrega') paneId = 'view-p4-entrega';

        const pane = document.getElementById(paneId);
        if (pane) {
            pane.classList.add('show', 'active');
        }

        this.refrescarVistaActiva();
    },

    async refrescarVistaActiva() {
        await this.verificarEstadoPeriodo();
        if (this.activeTab === 'asignacion') {
            this.cargarEvaluaciones();
        } else if (this.activeTab === 'consolidado') {
            this.cargarConsolidado();
        } else if (this.activeTab === 'entrega') {
            this.cargarEntrega();
        }
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

            // Guardar lista de todas las áreas para el Consolidado tabular
            this.areasList = areas.map(a => a.area);
            this.areasList.sort();

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
            this.refrescarVistaActiva();
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

        const bannerHtml = this.obtenerHtmlBannerEstado();
        const isPeriodLocked = this.periodoEstado && this.periodoEstado.status !== 'open';

        if (filtrados.length === 0) {
            grid.innerHTML = `
                ${bannerHtml}
                <div class="col-12 text-center py-5 text-muted">
                    <i class="bi bi-folder-x fs-1"></i>
                    <div class="mt-2">No se encontraron empleados en este periodo con los filtros aplicados.</div>
                </div>
            `;
            return;
        }

        grid.innerHTML = bannerHtml + filtrados.map(e => {
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
                            <small class="text-muted fw-bold d-block mb-1"><i class="bi bi-box-seam me-1"></i>Productos Asignados:</small>
                            <ul class="mb-0 ps-3 small text-secondary">
                                ${prodNombres.map(n => `<li>${n}</li>`).join('')}
                            </ul>
                            ${e.seleccion.observaciones ? `<div class="mt-1.5 small text-muted font-monospace text-truncate" title="${e.seleccion.observaciones}">Obs: ${e.seleccion.observaciones}</div>` : ''}
                        </div>
                    `;
                    cardAction = `
                        <button class="btn btn-sm btn-outline-primary w-100 mt-3" ${isPeriodLocked ? 'disabled' : ''} onclick="Productos4Module.abrirModalAsignacion(${e.empleado_id})">
                            <i class="bi bi-pencil-square me-1"></i> ${isPeriodLocked ? 'Bloqueado (Cerrado)' : 'Editar Selección'}
                        </button>
                    `;
                } else {
                    seleccionBadge = `
                        <div class="mt-3 p-2.5 bg-warning-subtle text-warning-emphasis rounded text-center small">
                            <i class="bi bi-info-circle me-1"></i> Pendiente de asignación.
                        </div>
                    `;
                    cardAction = `
                        <button class="btn btn-sm btn-primary w-100 mt-3" ${isPeriodLocked ? 'disabled' : ''} onclick="Productos4Module.abrirModalAsignacion(${e.empleado_id})">
                            <i class="bi bi-gift me-1"></i> ${isPeriodLocked ? 'Bloqueado (Cerrado)' : 'Asignar Productos'}
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
                    list.push(`[${prod.tipo}] ${prod.descripcion} (${prod.unidad})`);
                } else {
                    list.push(`Cód. ${c}`);
                }
            }
        });
        
        return list;
    },

    // --- Modal de Asignación ---
    abrirModalAsignacion(empleadoId) {
        if (this.periodoEstado && this.periodoEstado.status !== 'open') {
            Swal.fire({
                title: "Período Cerrado/Bloqueado",
                text: "No se pueden realizar ni editar asignaciones en este período.",
                icon: "error"
            });
            return;
        }

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

        const uniqueTipos = [...new Set(activeProds.map(p => p.tipo).filter(Boolean))];
        uniqueTipos.sort();

        const sel = emp.seleccion || {};
        const p1Val = sel.p1 || "";
        const p2Val = sel.p2 || "";
        const p3Val = sel.p3 || "";
        const p4Val = sel.p4 || "";
        const obsVal = sel.observaciones || "";

        Swal.fire({
            title: `<span class="fw-bold fs-5">🎁 Asignar Productos a ${emp.nombre}</span>`,
            html: `
                <div class="text-start mt-3">
                    <p class="small text-muted mb-4">Seleccione hasta 4 productos propios. La interfaz validará en tiempo real que no exceda las cantidades máximas definidas por producto.</p>
                    
                    <div class="mb-3">
                        <label for="asig-filtro-tipo" class="form-label small fw-bold text-primary"><i class="bi bi-funnel-fill me-1"></i>Filtrar por Tipo de Producto</label>
                        <select id="asig-filtro-tipo" class="form-select form-select-sm bg-light-subtle">
                            <option value="">-- Todos los Tipos --</option>
                            ${uniqueTipos.map(t => `<option value="${t}">${t}</option>`).join('')}
                        </select>
                    </div>

                    <hr class="opacity-10 my-3">
                    
                    <div class="mb-3">
                        <label for="asig-select-1" class="form-label small fw-bold text-secondary">Opción 1</label>
                        <select id="asig-select-1" class="form-select form-select-sm asig-prod-select"></select>
                    </div>
                    
                    <div class="mb-3">
                        <label for="asig-select-2" class="form-label small fw-bold text-secondary">Opción 2</label>
                        <select id="asig-select-2" class="form-select form-select-sm asig-prod-select"></select>
                    </div>
                    
                    <div class="mb-3">
                        <label for="asig-select-3" class="form-label small fw-bold text-secondary">Opción 3</label>
                        <select id="asig-select-3" class="form-select form-select-sm asig-prod-select"></select>
                    </div>
                    
                    <div class="mb-3">
                        <label for="asig-select-4" class="form-label small fw-bold text-secondary">Opción 4</label>
                        <select id="asig-select-4" class="form-select form-select-sm asig-prod-select"></select>
                    </div>

                    <div class="mb-3">
                        <label for="asig-obs" class="form-label small fw-bold text-secondary">Observaciones / Nota adicional</label>
                        <textarea id="asig-obs" class="form-control form-control-sm" rows="2" placeholder="Ej. Entregado en recepción">${obsVal}</textarea>
                    </div>

                    <div id="asig-validation-alert" class="alert alert-danger d-none py-2 px-3 small mb-0 mt-3">
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
                const selectTipo = document.getElementById('asig-filtro-tipo');
                
                // Initialize values mapping to selects
                this.filtrarOpcionesPorTipo("");

                document.getElementById('asig-select-1').value = p1Val;
                document.getElementById('asig-select-2').value = p2Val;
                document.getElementById('asig-select-3').value = p3Val;
                document.getElementById('asig-select-4').value = p4Val;

                // Bind cascade events
                selectTipo.addEventListener('change', (e) => {
                    this.filtrarOpcionesPorTipo(e.target.value);
                });

                // Bind listener to reactively update select availability
                const selects = document.querySelectorAll('.asig-prod-select');
                selects.forEach(s => s.addEventListener('change', () => this.actualizarOpcionesDisponibles()));
                
                this.actualizarOpcionesDisponibles();
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

    filtrarOpcionesPorTipo(selectedTipo) {
        const activeProds = this.productos.filter(p => p.activo);

        for (let i = 1; i <= 4; i++) {
            const select = document.getElementById(`asig-select-${i}`);
            if (!select) continue;
            const currentValue = select.value;

            // Filtrar productos
            let filteredProds = activeProds;
            if (selectedTipo) {
                filteredProds = activeProds.filter(p => p.tipo === selectedTipo);
            }

            // Asegurarse de mantener la selección actual en la lista, incluso si no coincide con el tipo, para no borrarla
            if (currentValue) {
                const currentProd = this.productos.find(p => p.codigo === parseInt(currentValue));
                if (currentProd && !filteredProds.some(p => p.codigo === currentProd.codigo)) {
                    filteredProds = [...filteredProds, currentProd];
                }
            }

            filteredProds.sort((a, b) => a.descripcion.localeCompare(b.descripcion));

            select.innerHTML = `
                <option value="">-- Sin Seleccionar --</option>
                ${filteredProds.map(p => `<option value="${p.codigo}">[${p.tipo}] ${p.descripcion} (${p.unidad}) [Máx: ${p.max_cantidad}]</option>`).join('')}
            `;

            select.value = currentValue;
        }

        this.actualizarOpcionesDisponibles();
    },

    actualizarOpcionesDisponibles() {
        const p1 = document.getElementById('asig-select-1')?.value || "";
        const p2 = document.getElementById('asig-select-2')?.value || "";
        const p3 = document.getElementById('asig-select-3')?.value || "";
        const p4 = document.getElementById('asig-select-4')?.value || "";

        const selections = [p1, p2, p3, p4].filter(v => v !== "");
        const counts = {};
        selections.forEach(v => {
            counts[v] = (counts[v] || 0) + 1;
        });

        // Habilitar/Deshabilitar dinámicamente opciones que violan el max_cantidad
        for (let i = 1; i <= 4; i++) {
            const select = document.getElementById(`asig-select-${i}`);
            if (!select) continue;
            const currentValue = select.value;

            Array.from(select.options).forEach(opt => {
                if (opt.value === "") return;
                const code = opt.value;
                const prod = this.productos.find(p => p.codigo === parseInt(code));
                if (!prod) return;

                const currentCount = counts[code] || 0;
                
                // Si ya fue seleccionado tantas veces como su límite, y no es el valor actual de este dropdown
                if (currentCount >= prod.max_cantidad && code !== currentValue) {
                    opt.disabled = true;
                    if (!opt.innerText.startsWith("🔒")) {
                        opt.innerText = `🔒 [${prod.tipo}] ${prod.descripcion} (${prod.unidad}) [Límite Máx alcanzado]`;
                    }
                } else {
                    opt.disabled = false;
                    opt.innerText = `[${prod.tipo}] ${prod.descripcion} (${prod.unidad}) [Máx: ${prod.max_cantidad}]`;
                }
            });
        }

        this.validarSeleccionReactiva();
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
        const p1 = document.getElementById('asig-select-1')?.value || "";
        const p2 = document.getElementById('asig-select-2')?.value || "";
        const p3 = document.getElementById('asig-select-3')?.value || "";
        const p4 = document.getElementById('asig-select-4')?.value || "";
        
        const codigos = [p1, p2, p3, p4].filter(c => c !== "").map(c => parseInt(c));
        const alertDiv = document.getElementById('asig-validation-alert');
        const msgSpan = document.getElementById('asig-validation-message');
        if (!alertDiv || !msgSpan) return;

        const validacion = this.validarLimitesSeleccion(codigos);

        if (!validacion.ok) {
            msgSpan.innerText = validacion.msg;
            alertDiv.classList.remove('d-none');
            const confirmBtn = Swal.getConfirmButton();
            if (confirmBtn) confirmBtn.setAttribute('disabled', 'true');
        } else {
            alertDiv.classList.add('d-none');
            const confirmBtn = Swal.getConfirmButton();
            if (confirmBtn) confirmBtn.removeAttribute('disabled');
        }
    },

    // ==========================================
    // SECCIÓN CONSOLIDADO GLOBAL
    // ==========================================

    async cargarConsolidado() {
        const content = document.getElementById('productos-4-consolidado-content');
        if (!content) return;

        content.innerHTML = `
            <div class="col-12 text-center py-5 text-muted">
                <div class="spinner-border text-primary mb-3" role="status"></div>
                <div>Generando reporte consolidado global del periodo...</div>
            </div>
        `;

        try {
            const url = `/api/productos-4/consolidado?mes=${this.periodoActivo.mes}&anio=${this.periodoActivo.anio}`;
            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!response.ok) throw new Error("Error al obtener el consolidado.");
            const data = await response.json();
            
            // Guardar detalles de asignaciones y entregas para el listado general en el Consolidado
            this.ultimoConsolidadoData = data;
            this.consolidadoDetalles = data.detalles || [];
            
            this.renderizarConsolidado(data);
        } catch (error) {
            content.innerHTML = `
                <div class="col-12 text-center py-5 text-danger">
                    <i class="bi bi-exclamation-triangle-fill fs-1"></i>
                    <div class="mt-2 fw-bold">No se pudo cargar el reporte consolidado.</div>
                    <div class="small text-muted">${error.message}</div>
                </div>
            `;
        }
    },

    renderizarConsolidado(data) {
        const content = document.getElementById('productos-4-consolidado-content');
        if (!content) return;

        const resumen = data.resumen || [];

        // 1. Obtener la lista de áreas del sistema (dinámica y combinada)
        const tempAreas = new Set();
        resumen.forEach(r => {
            (r.desglose_areas || []).forEach(da => {
                if (da.area) tempAreas.add(da.area);
            });
        });
        if (this.areasList && this.areasList.length > 0) {
            this.areasList.forEach(a => tempAreas.add(a));
        }
        const areas = [...tempAreas];
        areas.sort();

        // 2. Construir los encabezados de la tabla (Matriz)
        let headerColsHTML = `
            <th class="align-middle text-start ps-3">Descripción</th>
        `;
        areas.forEach(a => {
            headerColsHTML += `<th class="align-middle text-center" style="min-width: 100px;">${a}</th>`;
        });
        headerColsHTML += `<th class="align-middle text-center bg-light text-dark fw-bold" style="width: 130px;">Total Requerido</th>`;

        // 3. Construir filas por cada producto
        let rowsHTML = '';
        const areaTotals = {};
        areas.forEach(a => { areaTotals[a] = 0; });
        let totalGeneralSum = 0;

        if (resumen.length === 0) {
            rowsHTML = `
                <tr>
                    <td colspan="${areas.length + 2}" class="text-center py-5 text-muted">
                        <i class="bi bi-info-circle fs-3 d-block mb-2"></i>
                        No se registran asignaciones de productos en este periodo.
                    </td>
                </tr>
            `;
        } else {
            rowsHTML = resumen.map(r => {
                let cellsHTML = '';
                areas.forEach(a => {
                    const breakdown = (r.desglose_areas || []).find(da => da.area === a);
                    const qty = breakdown ? breakdown.cantidad : 0;
                    areaTotals[a] += qty;
                    
                    if (qty > 0) {
                        cellsHTML += `<td class="text-center fw-bold text-primary" style="font-size: 0.9rem;">${qty}</td>`;
                    } else {
                        cellsHTML += `<td class="text-center text-muted opacity-30">—</td>`;
                    }
                });

                totalGeneralSum += r.cantidad_total;

                return `
                    <tr>
                        <td class="fw-semibold ps-3 text-start">
                            <span class="text-dark">[${r.tipo}] ${r.descripcion} (${r.unidad})</span>
                        </td>
                        ${cellsHTML}
                        <td class="text-center fw-bold text-dark bg-light" style="font-size: 0.9rem;">${r.cantidad_total} uds</td>
                    </tr>
                `;
            }).join('');

            // 4. Fila de Totales por área en el pie
            let footerCellsHTML = '';
            areas.forEach(a => {
                const total = areaTotals[a];
                if (total > 0) {
                    footerCellsHTML += `<td class="text-center fw-bold text-dark bg-light-subtle" style="font-size: 0.9rem;">${total}</td>`;
                } else {
                    footerCellsHTML += `<td class="text-center text-muted opacity-30 bg-light-subtle">0</td>`;
                }
            });

            rowsHTML += `
                <tr class="table-secondary fw-bold border-top-2">
                    <td class="text-end pe-3 align-middle bg-light-subtle" style="font-size: 0.82rem; letter-spacing: 0.5px;">TOTALES POR ÁREA:</td>
                    ${footerCellsHTML}
                    <td class="text-center text-white bg-dark fw-bold" style="font-size: 0.92rem;">${totalGeneralSum} uds</td>
                </tr>
            `;
        }

        const bannerHtml = this.obtenerHtmlBannerEstado();
        content.innerHTML = `
            ${bannerHtml}
            <div class="col-12">
                <div class="card shadow-sm border-0 bg-white" style="border-radius: 12px;">
                    <div class="card-header bg-white pt-3 pb-2 border-bottom-0 d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div>
                            <h5 class="fw-bold mb-0 text-dark"><i class="bi bi-grid-3x3-gap-fill text-primary me-2"></i>Matriz de Distribución de Stock por Área</h5>
                            <p class="text-muted small mb-0 mt-0.5">Resumen consolidado global de las unidades asignadas por tipo de producto y departamento para la preparación logística en bodega.</p>
                        </div>
                        <div>
                            <button class="btn btn-outline-danger btn-sm px-3 rounded-pill fw-bold shadow-sm" onclick="Productos4Module.exportarPDF()">
                                <i class="bi bi-file-pdf-fill me-1"></i> Descargar PDF
                            </button>
                        </div>
                    </div>
                    <div class="table-responsive p-3" style="border-radius: 12px;">
                        <table class="table table-bordered table-hover align-middle mb-0" style="font-size: 0.82rem;">
                            <thead class="table-light text-secondary text-center">
                                <tr>
                                    ${headerColsHTML}
                                </tr>
                            </thead>
                            <tbody>
                                ${rowsHTML}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="col-12 mt-4">
                <div class="card shadow-sm border-0 bg-white" style="border-radius: 12px;">
                    <div class="card-header bg-white pt-3.5 pb-2 border-bottom-0 d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div>
                            <h5 class="fw-bold mb-0 text-dark"><i class="bi bi-list-check text-success me-2"></i>Estado de Entrega de Beneficios por Empleado</h5>
                            <p class="text-muted small mb-0 mt-0.5">Listado general de despacho del período actual sin restricción de área (se gestiona en la pestaña Entrega Beneficio).</p>
                        </div>
                        <div class="d-flex gap-2">
                            <div class="input-group input-group-sm" style="max-width: 220px;">
                                <span class="input-group-text bg-light border-end-0"><i class="bi bi-search text-muted"></i></span>
                                <input type="text" id="consolidado-emp-search" class="form-control form-control-sm bg-light border-start-0" placeholder="Buscar empleado...">
                            </div>
                            <select id="consolidado-emp-filtro-estado" class="form-select form-select-sm bg-light" style="max-width: 160px;">
                                <option value="todos">Todos los Estados</option>
                                <option value="entregado">Entregados</option>
                                <option value="pendiente">Pendientes</option>
                            </select>
                        </div>
                    </div>
                    <div class="table-responsive p-3" style="border-radius: 12px; max-height: 400px; overflow-y: auto;">
                        <table class="table table-hover align-middle mb-0" style="font-size: 0.82rem;">
                            <thead class="table-light text-secondary text-center sticky-top">
                                <tr>
                                    <th class="text-start ps-3" style="width: 120px;">RUT</th>
                                    <th class="text-start">Nombre Empleado</th>
                                    <th class="text-start">Área</th>
                                    <th class="text-start">Cargo</th>
                                    <th class="text-start" style="width: 150px;">Producto 1</th>
                                    <th class="text-start" style="width: 150px;">Producto 2</th>
                                    <th class="text-start" style="width: 150px;">Producto 3</th>
                                    <th class="text-start" style="width: 150px;">Producto 4</th>
                                    <th class="text-center" style="width: 130px;">Estado</th>
                                    <th class="text-start" style="width: 250px;">Información de Entrega</th>
                                </tr>
                            </thead>
                            <tbody id="consolidado-empleados-entregas-tbody">
                                <tr>
                                    <td colspan="10" class="text-center py-4 text-muted">
                                        <div class="spinner-border spinner-border-sm me-2" role="status"></div> Cargando listado de entregas...
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Vincular los eventos de búsqueda y filtro del listado general inferior
        setTimeout(() => {
            const searchInput = document.getElementById('consolidado-emp-search');
            const stateSelect = document.getElementById('consolidado-emp-filtro-estado');
            
            if (searchInput) {
                searchInput.addEventListener('input', () => this.filtrarYRenderizarDetallesConsolidado());
            }
            if (stateSelect) {
                stateSelect.addEventListener('change', () => this.filtrarYRenderizarDetallesConsolidado());
            }
            
            this.filtrarYRenderizarDetallesConsolidado();
        }, 50);
    },

    filtrarYRenderizarDetallesConsolidado() {
        const tbody = document.getElementById('consolidado-empleados-entregas-tbody');
        if (!tbody) return;

        const q = document.getElementById('consolidado-emp-search')?.value.toLowerCase().trim() || '';
        const filterState = document.getElementById('consolidado-emp-filtro-estado')?.value || 'todos';

        const detalles = this.consolidadoDetalles || [];

        if (detalles.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center py-5 text-muted">
                        <i class="bi bi-info-circle fs-4 d-block mb-2"></i>
                        No se registran asignaciones de beneficios en este período.
                    </td>
                </tr>
            `;
            return;
        }

        const filtrados = detalles.filter(d => {
            const matchQuery = d.empleado_nombre.toLowerCase().includes(q) || 
                               d.empleado_rut.toLowerCase().includes(q) || 
                               d.area.toLowerCase().includes(q) || 
                               (d.empleado_cargo || '').toLowerCase().includes(q);
            
            let matchState = true;
            if (filterState === 'entregado') {
                matchState = d.entregado;
            } else if (filterState === 'pendiente') {
                matchState = !d.entregado;
            }

            return matchQuery && matchState;
        });

        if (filtrados.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center py-5 text-muted">
                        <i class="bi bi-info-circle fs-4 d-block mb-2"></i>
                        No se encontraron empleados con los filtros aplicados.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = filtrados.map(d => {
            const statusBadge = d.entregado
                ? `<span class="badge bg-success-subtle text-success border border-success-subtle px-2.5 py-1 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i>ENTREGADO</span>`
                : `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle px-2.5 py-1 rounded-pill"><i class="bi bi-clock-fill me-1"></i>PENDIENTE</span>`;

            let deliveryInfo = '<span class="text-muted opacity-50">—</span>';
            if (d.entregado) {
                let dateFormatted = 'N/A';
                if (d.fecha_entrega) {
                    const dateObj = new Date(d.fecha_entrega);
                    if (!isNaN(dateObj.getTime())) {
                        const formattedDatePart = window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(dateObj) : dateObj.toLocaleDateString();
                        const timePart = `${String(dateObj.getHours()).padStart(2, '0')}:${String(dateObj.getMinutes()).padStart(2, '0')}`;
                        dateFormatted = `${formattedDatePart} ${timePart}`;
                    }
                }
                deliveryInfo = `
                    <div class="small lh-sm text-secondary font-monospace" style="font-size: 0.72rem;">
                        Por: <strong>${d.usuario_entrega_nombre || 'Sistema'}</strong><br>
                        El: ${dateFormatted}
                    </div>
                `;
            }

            // Mapear cada uno de los 4 productos en su respectiva columna
            const p1 = d.productos && d.productos[0] ? `<div class="small fw-semibold text-dark">${d.productos[0].descripcion}</div><div class="text-muted" style="font-size: 0.72rem;">${d.productos[0].unidad} (${d.productos[0].tipo})</div>` : '<span class="text-muted opacity-50">—</span>';
            const p2 = d.productos && d.productos[1] ? `<div class="small fw-semibold text-dark">${d.productos[1].descripcion}</div><div class="text-muted" style="font-size: 0.72rem;">${d.productos[1].unidad} (${d.productos[1].tipo})</div>` : '<span class="text-muted opacity-50">—</span>';
            const p3 = d.productos && d.productos[2] ? `<div class="small fw-semibold text-dark">${d.productos[2].descripcion}</div><div class="text-muted" style="font-size: 0.72rem;">${d.productos[2].unidad} (${d.productos[2].tipo})</div>` : '<span class="text-muted opacity-50">—</span>';
            const p4 = d.productos && d.productos[3] ? `<div class="small fw-semibold text-dark">${d.productos[3].descripcion}</div><div class="text-muted" style="font-size: 0.72rem;">${d.productos[3].unidad} (${d.productos[3].tipo})</div>` : '<span class="text-muted opacity-50">—</span>';

            return `
                <tr>
                    <td class="font-monospace fw-bold text-secondary ps-3">${d.empleado_rut}</td>
                    <td class="fw-semibold text-dark">${d.empleado_nombre}</td>
                    <td>${d.area}</td>
                    <td class="text-muted">${d.empleado_cargo || 'Sin Cargo'}</td>
                    <td class="text-start">${p1}</td>
                    <td class="text-start">${p2}</td>
                    <td class="text-start">${p3}</td>
                    <td class="text-start">${p4}</td>
                    <td class="text-center">${statusBadge}</td>
                    <td class="text-start">${deliveryInfo}</td>
                </tr>
            `;
        }).join('');
    },

    // ==========================================
    // SECCIÓN ENTREGA DE BENEFICIO
    // ==========================================

    async cargarEntrega() {
        const content = document.getElementById('productos-4-entrega-content');
        if (!content) return;

        content.innerHTML = `
            <div class="col-12 text-center py-5 text-muted">
                <div class="spinner-border text-primary mb-3" role="status"></div>
                <div>Cargando listado de entregas y despachos del periodo...</div>
            </div>
        `;

        const areaVal = document.getElementById('productos-4-filtro-area')?.value || "";

        try {
            let url = `/api/productos-4/entregas?mes=${this.periodoActivo.mes}&anio=${this.periodoActivo.anio}`;
            if (areaVal) {
                url += `&area=${encodeURIComponent(areaVal)}`;
            }
            const response = await fetch(url, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (!response.ok) throw new Error("Error al obtener la lista de entregas.");
            const data = await response.json();
            
            this.renderizarEntrega(data);
        } catch (error) {
            content.innerHTML = `
                <div class="col-12 text-center py-5 text-danger">
                    <i class="bi bi-exclamation-triangle-fill fs-1"></i>
                    <div class="mt-2 fw-bold">No se pudo cargar el panel de entregas.</div>
                    <div class="small text-muted">${error.message}</div>
                </div>
            `;
        }
    },

    renderizarEntrega(entregas) {
        const content = document.getElementById('productos-4-entrega-content');
        if (!content) return;

        const searchInput = document.getElementById('productos-4-search');
        const q = searchInput ? searchInput.value.toLowerCase().trim() : '';

        // Filtrar entregas según el buscador
        const filtrados = entregas.filter(e => {
            return e.empleado_nombre.toLowerCase().includes(q) || 
                   e.empleado_rut.toLowerCase().includes(q) || 
                   e.area.toLowerCase().includes(q);
        });

        // Métricas de progreso
        const totalAsignados = entregas.length;
        const totalEntregados = entregas.filter(e => e.entregado).length;
        const totalPendientes = totalAsignados - totalEntregados;
        const porcentajeEntregado = totalAsignados > 0 ? Math.round((totalEntregados / totalAsignados) * 100) : 0;

        // Armar tarjetas de los empleados
        let cardsHTML = '';
        if (filtrados.length === 0) {
            cardsHTML = `
                <div class="col-12 text-center py-5 text-muted">
                    <i class="bi bi-folder-x fs-1"></i>
                    <div class="mt-2">No se encontraron entregas en este periodo con los filtros aplicados.</div>
                </div>
            `;
        } else {
            cardsHTML = filtrados.map(e => {
                const prodNombres = e.productos.filter(p => p !== null).map(p => `[${p.tipo}] ${p.descripcion} (${p.unidad})`);

                const badge = e.entregado 
                    ? `<span class="badge bg-success-subtle text-success border border-success-subtle px-2.5 py-1 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i>Entregado</span>`
                    : `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle px-2.5 py-1 rounded-pill"><i class="bi bi-clock-fill me-1"></i>Pendiente</span>`;

                let deliveryAction = '';
                if (e.entregado) {
                    let dateFormatted = 'N/A';
                    if (e.fecha_entrega) {
                        const d = new Date(e.fecha_entrega);
                        if (!isNaN(d.getTime())) {
                            const formattedDatePart = window.formatFechaDDMMYYYY(d);
                            const timePart = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
                            dateFormatted = `${formattedDatePart} ${timePart}`;
                        }
                    }
                    deliveryAction = `
                        <button class="btn btn-sm btn-outline-danger w-100 mt-3" onclick="Productos4Module.marcarEntrega(${e.empleado_id}, false)">
                            <i class="bi bi-arrow-counterclockwise me-1"></i> Revertir Entrega
                        </button>
                        <div class="text-secondary text-center small font-monospace mt-2" style="font-size: 0.72rem; line-height: 1.25;">
                            Por: <strong>${e.usuario_entrega_nombre || 'Sistema'}</strong><br>
                            El: ${dateFormatted}
                        </div>
                    `;
                } else {
                    deliveryAction = `
                        <button class="btn btn-sm btn-success w-100 mt-3 fw-bold shadow-sm" onclick="Productos4Module.marcarEntrega(${e.empleado_id}, true)">
                            <i class="bi bi-check-circle me-1"></i> Registrar Entrega
                        </button>
                    `;
                }

                return `
                    <div class="col-xl-3 col-lg-4 col-md-6">
                        <div class="card h-100 shadow-sm border-0 position-relative transition-all hover-translate-y" style="border-radius: 12px;">
                            <div class="card-body p-3.5 d-flex flex-column justify-content-between">
                                <div>
                                    <div class="d-flex justify-content-between align-items-start mb-2">
                                        <div class="small text-muted font-monospace">${e.empleado_rut}</div>
                                        ${badge}
                                    </div>
                                    <h6 class="fw-bold mb-1 text-truncate" title="${e.empleado_nombre}">${e.empleado_nombre}</h6>
                                    <div class="small text-secondary text-truncate mb-1"><i class="bi bi-briefcase me-1"></i>${e.empleado_cargo || 'Sin Cargo'}</div>
                                    <div class="small text-secondary text-truncate"><i class="bi bi-geo-alt me-1"></i>${e.area}</div>
                                    
                                    <div class="mt-3 p-2 bg-light rounded text-start border border-dashed">
                                        <small class="text-muted fw-bold d-block mb-1"><i class="bi bi-box-seam me-1"></i>Productos Asignados:</small>
                                        <ul class="mb-0 ps-3 small text-secondary">
                                            ${prodNombres.map(n => `<li>${n}</li>`).join('')}
                                        </ul>
                                        ${e.observaciones ? `<div class="mt-1.5 small text-muted font-monospace text-truncate" title="${e.observaciones}">Obs: ${e.observaciones}</div>` : ''}
                                    </div>
                                </div>
                                <div>
                                    ${deliveryAction}
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        const bannerHtml = this.obtenerHtmlBannerEstado();
        content.innerHTML = `
            ${bannerHtml}
            <div class="col-12">
                <div class="card shadow-sm border-0 bg-white" style="border-radius: 12px;">
                    <div class="card-body p-3.5">
                        <div class="row align-items-center g-3">
                            <div class="col-md-4">
                                <h6 class="text-secondary small fw-bold mb-1"><i class="bi bi-pie-chart me-1"></i>Progreso de Entregas</h6>
                                <div class="fs-4 fw-bold text-dark">${totalEntregados} <span class="fs-6 text-muted font-normal">de ${totalAsignados} beneficios entregados (${porcentajeEntregado}%)</span></div>
                            </div>
                            <div class="col-md-5">
                                <div class="progress rounded-pill bg-light border" style="height: 14px;">
                                    <div class="progress-bar progress-bar-striped progress-bar-animated bg-success rounded-pill" role="progressbar" style="width: ${porcentajeEntregado}%" aria-valuenow="${porcentajeEntregado}" aria-valuemin="0" aria-valuemax="100"></div>
                                </div>
                            </div>
                            <div class="col-md-3 text-end d-flex justify-content-end gap-3.5">
                                <div class="text-center">
                                    <div class="small text-muted">Pendientes</div>
                                    <span class="badge bg-warning text-warning-emphasis rounded-pill fs-6 px-3 py-1 mt-1">${totalPendientes}</span>
                                </div>
                                <div class="text-center">
                                    <div class="small text-muted">Entregados</div>
                                    <span class="badge bg-success text-success-emphasis rounded-pill fs-6 px-3 py-1 mt-1">${totalEntregados}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-12 mt-4">
                <div class="d-flex align-items-center justify-content-between mb-3">
                    <h5 class="fw-bold mb-0 text-dark"><i class="bi bi-list-check me-2 text-success"></i>Planilla de Despacho y Firma</h5>
                    <span class="badge bg-light text-dark border font-monospace py-1.5 px-3">Mostrando: ${filtrados.length} / ${totalAsignados}</span>
                </div>
                <div class="row g-3">
                    ${cardsHTML}
                </div>
            </div>
        `;
    },

    async marcarEntrega(empleadoId, entregado) {
        const actionText = entregado ? "marcar como ENTREGADO" : "REVERTIR la entrega a PENDIENTE";
        const confirmColor = entregado ? "#198754" : "#dc3545";
        
        const result = await Swal.fire({
            title: `¿Confirmar operación?`,
            text: `¿Está seguro de que desea ${actionText} para este empleado en el periodo seleccionado?`,
            icon: "question",
            showCancelButton: true,
            confirmButtonText: "Sí, registrar",
            cancelButtonText: "Cancelar",
            confirmButtonColor: confirmColor
        });

        if (!result.isConfirmed) return;

        try {
            const response = await fetch('/api/productos-4/entregar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({
                    empleado_id: empleadoId,
                    mes: this.periodoActivo.mes,
                    anio: this.periodoActivo.anio,
                    entregado: entregado
                })
            });

            const res = await response.json();
            if (!response.ok) throw new Error(res.detail || "Error al actualizar la entrega.");

            showToast("Entrega de beneficio actualizada con éxito.", "success");
            this.cargarEntrega();
        } catch (error) {
            console.error(error);
            Swal.fire({
                title: "Error",
                text: error.message,
                icon: "error"
            });
        }
    },

    // ==========================================
    // SECCIÓN CRUD: Catálogo de Productos
    // ==========================================

    renderizarConfiguracionCatalogo() {
        const container = document.getElementById('tab-productos-propios');
        if (!container) return;

        const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.catalogo') : true;

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

        const canEdit = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.catalogo') : true;

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
    },

    // --- Control de Períodos ---
    async verificarEstadoPeriodo() {
        try {
            const response = await fetch(`/api/productos-4/periodo/status?mes=${this.periodoActivo.mes}&anio=${this.periodoActivo.anio}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            if (response.ok) {
                this.periodoEstado = await response.json();
            } else {
                console.error("Error al verificar estado del periodo");
                this.periodoEstado = { status: 'open', mensaje: 'Error al verificar estado, asumiendo abierto.' };
            }
        } catch (error) {
            console.error("Error en verificarEstadoPeriodo:", error);
            this.periodoEstado = { status: 'open', mensaje: 'Error al verificar estado, asumiendo abierto.' };
        }
        
        this.renderizarAccionesPeriodo();
    },

    renderizarAccionesPeriodo() {
        const container = document.getElementById('productos-4-period-actions');
        if (!container) return;

        if (!this.periodoEstado) {
            container.innerHTML = '';
            return;
        }

        const canAsignar = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.asignar') : true;
        const canCatalogo = typeof AuthService !== 'undefined' ? AuthService.hasPermission('productos_4.catalogo') : false;

        let html = '';

        if (this.periodoEstado.status === 'closed') {
            html += `
                <span class="badge bg-danger-subtle text-danger border border-danger-subtle d-inline-flex align-items-center px-3 py-2 rounded-pill fw-bold">
                    <i class="bi bi-lock-fill me-1"></i> Período Cerrado
                </span>
            `;
            if (canCatalogo) {
                html += `
                    <button class="btn btn-outline-danger btn-sm border shadow-sm px-3 rounded-pill fw-bold" onclick="Productos4Module.confirmarReabrirPeriodo()">
                        <i class="bi bi-unlock-fill me-1"></i> Reabrir Período
                    </button>
                `;
            }
        } else if (this.periodoEstado.status === 'blocked_previous') {
            html += `
                <span class="badge bg-warning-subtle text-warning border border-warning-subtle d-inline-flex align-items-center px-3 py-2 rounded-pill fw-bold" 
                      title="${this.periodoEstado.mensaje || ''}" data-bs-toggle="tooltip" data-bs-placement="bottom">
                    <i class="bi bi-slash-circle-fill me-1"></i> Bloqueado
                </span>
            `;
        } else {
            // status === 'open'
            if (canAsignar) {
                html += `
                    <button class="btn btn-warning btn-sm border shadow-sm px-3 rounded-pill fw-bold" onclick="Productos4Module.confirmarCerrarPeriodo()">
                        <i class="bi bi-lock-fill me-1"></i> Cerrar Período
                    </button>
                `;
            } else {
                html += `
                    <span class="badge bg-success-subtle text-success border border-success-subtle d-inline-flex align-items-center px-3 py-2 rounded-pill fw-bold">
                        <i class="bi bi-check-circle-fill me-1"></i> Abierto
                    </span>
                `;
            }
        }

        container.innerHTML = html;

        // Inicializar tooltips
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltips = container.querySelectorAll('[data-bs-toggle="tooltip"]');
            tooltips.forEach(el => new bootstrap.Tooltip(el));
        }
    },

    obtenerHtmlBannerEstado() {
        if (!this.periodoEstado) return '';

        if (this.periodoEstado.status === 'closed') {
            return `
                <div class="col-12 mb-4">
                    <div class="alert alert-danger d-flex align-items-center border-0 shadow-sm p-3" style="border-radius: 12px; background-color: #fff5f5; border-left: 5px solid #e53e3e !important;">
                        <i class="bi bi-lock-fill fs-4 text-danger me-3"></i>
                        <div>
                            <strong class="text-danger">Período Cerrado:</strong> El período de asignación de productos propios para este mes ha sido cerrado. No se permiten nuevas asignaciones ni modificaciones de productos.
                        </div>
                    </div>
                </div>
            `;
        } else if (this.periodoEstado.status === 'blocked_previous') {
            const prevMesStr = String(this.periodoEstado.prev_mes).padStart(2, '0');
            return `
                <div class="col-12 mb-4">
                    <div class="alert alert-warning d-flex align-items-center border-0 shadow-sm p-3" style="border-radius: 12px; background-color: #fffdf5; border-left: 5px solid #dd6b20 !important;">
                        <i class="bi bi-exclamation-triangle-fill fs-4 text-warning me-3"></i>
                        <div>
                            <strong class="text-warning">Período Bloqueado:</strong> No se pueden realizar asignaciones para este mes porque el período anterior (<strong>${this.periodoEstado.prev_anio}-${prevMesStr}</strong>) aún no se ha cerrado.
                        </div>
                    </div>
                </div>
            `;
        }
        return '';
    },

    async confirmarCerrarPeriodo() {
        const mesStr = String(this.periodoActivo.mes).padStart(2, '0');
        const result = await Swal.fire({
            title: '¿Cerrar Período?',
            text: `Esta acción bloqueará las asignaciones para el período ${this.periodoActivo.anio}-${mesStr}. No se podrán editar ni agregar nuevas asignaciones.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Sí, cerrar período',
            cancelButtonText: 'Cancelar',
            customClass: {
                confirmButton: 'btn btn-warning btn-sm px-3.5 me-2',
                cancelButton: 'btn btn-outline-secondary btn-sm px-3.5'
            },
            buttonsStyling: false
        });

        if (result.isConfirmed) {
            try {
                Swal.showLoading();
                const response = await fetch('/api/productos-4/periodo/cerrar', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('token')}`
                    },
                    body: JSON.stringify({
                        mes: this.periodoActivo.mes,
                        anio: this.periodoActivo.anio
                    })
                });

                const res = await response.json();
                if (!response.ok) throw new Error(res.detail || "Error al cerrar el período.");

                showToast("El período ha sido cerrado exitosamente.", "success");
                await this.verificarEstadoPeriodo();
                this.refrescarVistaActiva();
            } catch (error) {
                console.error(error);
                Swal.fire({
                    title: 'Error',
                    text: error.message,
                    icon: 'error'
                });
            }
        }
    },

    async confirmarReabrirPeriodo() {
        const mesStr = String(this.periodoActivo.mes).padStart(2, '0');
        const result = await Swal.fire({
            title: '¿Reabrir Período?',
            text: `Esta acción volverá a habilitar la edición y asignación de productos para el período ${this.periodoActivo.anio}-${mesStr}.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Sí, reabrir período',
            cancelButtonText: 'Cancelar',
            customClass: {
                confirmButton: 'btn btn-danger btn-sm px-3.5 me-2',
                cancelButton: 'btn btn-outline-secondary btn-sm px-3.5'
            },
            buttonsStyling: false
        });

        if (result.isConfirmed) {
            try {
                Swal.showLoading();
                const response = await fetch('/api/productos-4/periodo/reabrir', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('token')}`
                    },
                    body: JSON.stringify({
                        mes: this.periodoActivo.mes,
                        anio: this.periodoActivo.anio
                    })
                });

                const res = await response.json();
                if (!response.ok) throw new Error(res.detail || "Error al reabrir el período.");

                showToast("El período ha sido reabierto exitosamente.", "success");
                await this.verificarEstadoPeriodo();
                this.refrescarVistaActiva();
            } catch (error) {
                console.error(error);
                Swal.fire({
                    title: 'Error',
                    text: error.message,
                    icon: 'error'
                });
            }
        }
    },

    exportarPDF() {
        const { jsPDF } = window.jspdf || {};
        if (!jsPDF) {
            showToast("No se pudo cargar la librería de PDF.", "error");
            return;
        }

        const data = this.ultimoConsolidadoData;
        if (!data) {
            showToast("No hay datos de consolidado cargados para exportar.", "warning");
            return;
        }

        const doc = new jsPDF('l', 'pt', 'letter');
        
        const mesStr = String(this.periodoActivo.mes).padStart(2, '0');
        const periodStr = `${this.periodoActivo.anio}-${mesStr}`;
        const timestamp = new Date().toLocaleString();
        const userName = (typeof AuthService !== 'undefined' && AuthService.currentUser) ? AuthService.currentUser.username : 'Usuario';

        // Título del PDF
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(16);
        doc.setTextColor(33, 37, 41);
        doc.text("Reporte Consolidado de Beneficios: 4 Productos", 40, 45);
        
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(9);
        doc.setTextColor(108, 117, 125);
        doc.text(`Período: ${periodStr}   |   Generado por: ${userName}   |   Fecha: ${timestamp}`, 40, 62);

        // --- SECCIÓN 1: MATRIZ DE STOCK ---
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(12);
        doc.setTextColor(33, 37, 41);
        doc.text("1. Matriz de Distribución de Stock por Área", 40, 95);

        const resumen = data.resumen || [];
        const tempAreas = new Set();
        resumen.forEach(r => {
            (r.desglose_areas || []).forEach(da => {
                if (da.area) tempAreas.add(da.area);
            });
        });
        if (this.areasList && this.areasList.length > 0) {
            this.areasList.forEach(a => tempAreas.add(a));
        }
        const areas = [...tempAreas];
        areas.sort();

        // Encabezados Matriz
        const matrixHeaders = ['Descripción / Producto'];
        areas.forEach(a => matrixHeaders.push(a));
        matrixHeaders.push('Total Requerido');

        // Cuerpo Matriz
        const matrixBody = [];
        const areaTotals = {};
        areas.forEach(a => { areaTotals[a] = 0; });
        let totalGeneralSum = 0;

        resumen.forEach(r => {
            const row = [`[${r.tipo}] ${r.descripcion} (${r.unidad})`];
            areas.forEach(a => {
                const breakdown = (r.desglose_areas || []).find(da => da.area === a);
                const qty = breakdown ? breakdown.cantidad : 0;
                areaTotals[a] += qty;
                row.push(qty > 0 ? `${qty}` : '—');
            });
            row.push(`${r.cantidad_total} uds`);
            totalGeneralSum += r.cantidad_total;
            matrixBody.push(row);
        });

        // Fila Totales
        const totalsRow = ['TOTALES POR ÁREA:'];
        areas.forEach(a => {
            totalsRow.push(`${areaTotals[a]}`);
        });
        totalsRow.push(`${totalGeneralSum} uds`);
        matrixBody.push(totalsRow);

        doc.autoTable({
            head: [matrixHeaders],
            body: matrixBody,
            startY: 110,
            theme: 'grid',
            styles: { font: 'helvetica', fontSize: 8, cellPadding: 5 },
            headStyles: { fillColor: [41, 128, 185], textColor: [255, 255, 255], fontStyle: 'bold', halign: 'center' },
            columnStyles: {
                0: { halign: 'left', fontStyle: 'semibold', cellWidth: 160 }
            },
            didParseCell: function(cellData) {
                if (cellData.row.index === matrixBody.length - 1) {
                    cellData.cell.styles.fontStyle = 'bold';
                    cellData.cell.styles.fillColor = [240, 240, 240];
                    if (cellData.column.index === matrixHeaders.length - 1) {
                        cellData.cell.styles.fillColor = [44, 62, 80];
                        cellData.cell.styles.textColor = [255, 255, 255];
                    }
                }
                if (cellData.column.index > 0) {
                    cellData.cell.styles.halign = 'center';
                }
            }
        });

        // --- SECCIÓN 2: LISTADO DE ENTREGAS ---
        let startY2 = doc.lastAutoTable.finalY + 35;
        
        // Agregar salto de página si no cabe en el espacio vertical de la hoja Carta (alto: 612 pt)
        if (startY2 > 460) {
            doc.addPage();
            startY2 = 45;
        }

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(12);
        doc.setTextColor(33, 37, 41);
        doc.text("2. Estado de Entrega de Beneficios por Empleado", 40, startY2);

        // Obtener datos filtrados según el estado actual de los inputs en pantalla
        const q = document.getElementById('consolidado-emp-search')?.value.toLowerCase().trim() || '';
        const filterState = document.getElementById('consolidado-emp-filtro-estado')?.value || 'todos';

        const detalles = this.consolidadoDetalles || [];
        const filtrados = detalles.filter(d => {
            const matchQuery = d.empleado_nombre.toLowerCase().includes(q) || 
                               d.empleado_rut.toLowerCase().includes(q) || 
                               d.area.toLowerCase().includes(q) || 
                               (d.empleado_cargo || '').toLowerCase().includes(q);
            
            let matchState = true;
            if (filterState === 'entregado') {
                matchState = d.entregado;
            } else if (filterState === 'pendiente') {
                matchState = !d.entregado;
            }

            return matchQuery && matchState;
        });

        // Encabezados checklist
        const deliveryHeaders = ['RUT', 'Nombre Empleado', 'Área', 'Cargo', 'Producto 1', 'Producto 2', 'Producto 3', 'Producto 4', 'Estado', 'Detalle Entrega'];

        // Cuerpo checklist
        const deliveryBody = filtrados.map(d => {
            const p1 = d.productos && d.productos[0] ? `${d.productos[0].descripcion} (${d.productos[0].unidad})` : '—';
            const p2 = d.productos && d.productos[1] ? `${d.productos[1].descripcion} (${d.productos[1].unidad})` : '—';
            const p3 = d.productos && d.productos[2] ? `${d.productos[2].descripcion} (${d.productos[2].unidad})` : '—';
            const p4 = d.productos && d.productos[3] ? `${d.productos[3].descripcion} (${d.productos[3].unidad})` : '—';

            const statusText = d.entregado ? 'ENTREGADO' : 'PENDIENTE';
            
            let deliveryText = '—';
            if (d.entregado) {
                let dateFormatted = 'N/A';
                if (d.fecha_entrega) {
                    const dateObj = new Date(d.fecha_entrega);
                    if (!isNaN(dateObj.getTime())) {
                        const formattedDatePart = window.formatFechaDDMMYYYY ? window.formatFechaDDMMYYYY(dateObj) : dateObj.toLocaleDateString();
                        const timePart = `${String(dateObj.getHours()).padStart(2, '0')}:${String(dateObj.getMinutes()).padStart(2, '0')}`;
                        dateFormatted = `${formattedDatePart} ${timePart}`;
                    }
                }
                deliveryText = `Por: ${d.usuario_entrega_nombre || 'Sistema'}\nEl: ${dateFormatted}`;
            }

            return [
                d.empleado_rut,
                d.empleado_nombre,
                d.area,
                d.empleado_cargo || 'Sin Cargo',
                p1,
                p2,
                p3,
                p4,
                statusText,
                deliveryText
            ];
        });

        doc.autoTable({
            head: [deliveryHeaders],
            body: deliveryBody,
            startY: startY2 + 15,
            theme: 'grid',
            styles: { font: 'helvetica', fontSize: 7, cellPadding: 4 },
            headStyles: { fillColor: [46, 204, 113], textColor: [255, 255, 255], fontStyle: 'bold', halign: 'center' },
            columnStyles: {
                0: { fontStyle: 'bold', halign: 'center', cellWidth: 52 }, // RUT
                1: { fontStyle: 'semibold' }, // Nombre (auto-estirar)
                2: { cellWidth: 60 }, // Área
                3: { cellWidth: 60 }, // Cargo
                4: { cellWidth: 76 }, // P1
                5: { cellWidth: 76 }, // P2
                6: { cellWidth: 76 }, // P3
                7: { cellWidth: 76 }, // P4
                8: { halign: 'center', fontStyle: 'bold', cellWidth: 52 }, // Estado
                9: { fontSize: 6, cellWidth: 72 } // Detalle
            },
            didParseCell: function(cellData) {
                if (cellData.section === 'body' && cellData.column.index === 8) {
                    if (cellData.cell.raw === 'ENTREGADO') {
                        cellData.cell.styles.textColor = [39, 174, 96];
                    } else {
                        cellData.cell.styles.textColor = [230, 126, 34];
                    }
                }
            }
        });

        doc.save(`consolidado_4_productos_${periodStr}.pdf`);
    }
};

// Logger simple para debug en UI
function logger_ui(msg) {
    console.log(`%c[UI-PRODUCTOS-4] ${msg}`, "color: #10b981; font-weight: bold;");
}

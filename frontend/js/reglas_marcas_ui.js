// ─────────────────────────────────────────────────────────────────────────────
// Reglas de marcaciones (Configuración).
// El motor lee SOLO las reglas encendidas. Todas nacen apagadas y se encienden
// una por una con «Correr esta regla»: recalcula en segundo plano únicamente
// los días del tramo abierto con esa secuencia (jornadas terminadas, sin
// cierres de área) y muestra el antes y el después de cada día que cambió.
// «Apagar esta regla» deshace de la misma forma. Los períodos cerrados no se
// tocan nunca.
// ─────────────────────────────────────────────────────────────────────────────
const ReglasMarcasModule = (() => {
    const API = '/api/configuracion/reglas-marcas/';
    const GRUPOS = ['Bien marcadas', 'Se repite un tipo', 'Falta una marca', 'Una sola marca'];
    const OPCIONES = [
        ['AGREGAR_SALIDA', 'Agregar Salida manual'],
        ['AGREGAR_ENTRADA', 'Agregar Entrada manual'],
        ['RECLASIFICAR', 'Reclasificar marcas'],
        ['CONFIRMAR', 'Confirmar que está bien'],
    ];
    let data = null;
    let tipo = 'CICLO_INTELIGENTE';
    let selId = null;
    let cargando = false;

    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const canEdit = () => (typeof AuthService !== 'undefined') ? AuthService.hasPermission('configuracion.reglas_marcaciones') : false;
    const headers = () => ({ 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` });
    const pretty = (sec) => sec.split('').join(' · ');
    const pct = (n, total) => total > 0 ? (100 * n / total).toLocaleString('es-CL', { maximumFractionDigits: 1 }) : '0';
    const toast = (msg, tipo_) => { if (typeof showToast === 'function') showToast(msg, tipo_ || 'success'); else alert(msg); };

    // Qué papel juega cada marca según la lectura elegida (sin horas: solo posiciones).
    function roles(sec, lectura) {
        const n = sec.length;
        if (lectura === 'NINGUNA') return Array(n).fill(['Sin lectura', 'muted']);
        const r = Array(n).fill(['No se usa', 'muted']);
        if (lectura === 'RELOJ') {
            const pares = [];
            for (let i = 0; i < n; ) {
                if (sec[i] === 'E' && sec[i + 1] === 'S') { pares.push([i, i + 1]); i += 2; } else i++;
            }
            pares.forEach((p, k) => {
                r[p[0]] = [k === 0 ? 'Entrada del día' : 'Regreso de pausa', k === 0 ? 'ent' : 'pausa'];
                r[p[1]] = [k === pares.length - 1 ? 'Salida del día' : 'Salida a pausa', k === pares.length - 1 ? 'sal' : 'pausa'];
            });
            return r;
        }
        // EXTREMOS
        r[0] = [sec[0] === 'E' ? 'Entrada del día' : 'Entrada del día (el reloj dijo Salida)', 'ent'];
        r[n - 1] = [sec[n - 1] === 'S' ? 'Salida del día' : 'Salida del día (el reloj dijo Entrada)', 'sal'];
        for (let j = 1; j < n - 2; ) {
            if (sec[j] === 'S' && sec[j + 1] === 'E') { r[j] = ['Salida a pausa', 'pausa']; r[j + 1] = ['Regreso de pausa', 'pausa']; j += 2; }
            else j++;
        }
        return r;
    }

    function fraseResultado(regla) {
        const partes = [];
        if (regla.lectura === 'NINGUNA') {
            partes.push('El día queda en anomalía y no se calcula hasta que una persona lo resuelva.');
        } else {
            partes.push(regla.lectura === 'EXTREMOS'
                ? 'La primera marca es la Entrada del día y la última la Salida; las del medio solo valen como pausa si son una Salida seguida de una Entrada.'
                : 'Las marcas se leen tal como las rotuló el reloj.');
            partes.push(regla.colacion === 'NINGUNA' ? 'No se descuenta colación.'
                : regla.colacion === 'MEDIDA' ? 'La colación se mide con las marcas de la pausa; sin pausa completa rige la del turno (siempre se descuenta el mayor entre la pactada y la medida).'
                : 'Se descuenta la colación automática del turno asignado.');
        }
        partes.push(regla.accion === 'CALCULA' ? 'No aparece en revisión.'
            : regla.accion === 'CALCULA_Y_REVISA' ? 'El día aparece en «Días por revisar» con un triángulo en la celda.'
            : 'El día aparece en «Días por revisar» y queda en anomalía hasta revisarlo.');
        return partes.join(' ');
    }

    async function init() {
        const cont = $('reglas-marcas-container');
        if (!cont || cargando) return;
        cargando = true;
        try {
            const res = await fetch(`${API}?tipo=${encodeURIComponent(tipo)}`, { headers: headers() });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            data = await res.json();
            if (!selId && data.reglas.length) selId = data.reglas[0].id;
            render();
        } catch (e) {
            cont.innerHTML = `<div class="alert alert-danger">No se pudieron cargar las reglas de marcaciones. ${esc(e.message)}</div>`;
        } finally {
            cargando = false;
        }
    }

    function render() {
        const cont = $('reglas-marcas-container');
        if (!cont || !data) return;
        const tiposBtns = (data.tipos || []).map(t => `
            <button type="button" class="btn btn-sm ${t.tipo === tipo ? 'btn-primary' : 'btn-outline-secondary'}" data-rm-tipo="${esc(t.tipo)}">
                ${esc(t.tipo === 'CICLO_INTELIGENTE' ? 'Ciclo Inteligente' : t.tipo === 'BOLSA_FLEXIBLE' ? 'Bolsa Flexible' : t.tipo)} · ${t.personas} personas
            </button>`).join(' ');
        const activas = data.reglas.filter(r => r.activa).length;
        const diasActivas = data.reglas.filter(r => r.activa).reduce((s, r) => s + r.dias, 0);
        cont.innerHTML = `
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
                <h4 class="mb-0"><i class="bi bi-diagram-3" aria-hidden="true"></i> Reglas de marcaciones</h4>
                <div class="d-flex gap-2 flex-wrap">${tiposBtns}</div>
            </div>
            <div class="alert alert-info py-2 mb-2" style="font-size:.9rem;">
                <i class="bi bi-info-circle" aria-hidden="true"></i>
                El motor usa <strong>solo las reglas encendidas</strong>. «Correr esta regla» la enciende y
                recalcula únicamente los días del tramo abierto con esa secuencia (nunca el día en curso,
                nunca períodos cerrados), mostrando el antes y el después. «Apagar esta regla» lo deshace.
            </div>
            <div id="rm-corrida-aviso"></div>
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3" style="font-size:.88rem;">
                <span class="text-muted">Reglas corridas: <strong>${activas} de ${data.reglas.length}</strong> ·
                    cubren el <strong>${pct(diasActivas, data.total_jornadas)} %</strong> de las ${Number(data.total_jornadas).toLocaleString('es-CL')} jornadas con marcas del reloj</span>
                <span class="text-muted">Rebote (doble toque):
                    <input type="number" id="rm-rebote" class="form-control form-control-sm d-inline-block" style="width:90px" min="0" max="1800"
                           value="${Number(data.rebote_segundos)}" ${canEdit() ? '' : 'disabled'}> segundos
                    ${canEdit() ? '<button type="button" class="btn btn-sm btn-outline-primary" id="rm-rebote-save">Guardar</button>' : ''}
                </span>
            </div>
            ${data.reglas.length ? `
            <div class="d-flex flex-wrap gap-3 align-items-start">
                <div id="rm-lista" class="card border-0 shadow-sm p-2" style="flex:1 1 250px; max-width:360px;"></div>
                <div id="rm-editor" class="card border-0 shadow-sm p-3" style="flex:2 1 420px;"></div>
            </div>` : `
            <div class="card border-0 shadow-sm p-4 text-muted">
                <strong>Sin reglas cargadas para este tipo de horario.</strong><br>
                Bolsa Flexible conserva su lógica actual y esta pestaña no la toca. Si algún día se necesitan
                reglas aquí, se crean aparte, sin copiar las de Ciclo Inteligente.
            </div>`}
            ${(data.secuencias_sin_regla || []).length ? `
            <div class="card border-0 shadow-sm p-3 mt-3">
                <div class="fw-semibold mb-1">Secuencias encontradas sin regla</div>
                <div class="text-muted" style="font-size:.85rem;">Cuando el motor esté conectado irán a revisión. Se les crea su regla en la etapa siguiente.</div>
                <div class="mt-2">${data.secuencias_sin_regla.map(s => `<span class="badge bg-light text-dark border me-1">${pretty(esc(s.secuencia))} · ${s.dias} días</span>`).join(' ')}</div>
            </div>` : ''}
        `;
        cont.querySelectorAll('[data-rm-tipo]').forEach(b => b.addEventListener('click', () => { tipo = b.dataset.rmTipo; selId = null; init(); }));
        const btnReb = $('rm-rebote-save');
        if (btnReb) btnReb.addEventListener('click', guardarRebote);
        if (data.reglas.length) { renderLista(); renderEditor(); }
        if (data.corrida_en_curso && data.corrida_en_curso.estado === 'en_curso') seguirCorrida(data.corrida_en_curso.id);
    }

    function renderLista() {
        const el = $('rm-lista');
        if (!el) return;
        let html = '';
        GRUPOS.forEach(g => {
            const filas = data.reglas.filter(r => r.grupo === g);
            if (!filas.length) return;
            html += `<div class="text-muted px-2 pt-2 pb-1" style="font-size:.78rem;">${esc(g)}</div>`;
            filas.forEach(r => {
                const dot = r.accion === 'CALCULA' ? '#198754' : (r.accion === 'CALCULA_Y_REVISA' ? '#ffc107' : '#dc3545');
                html += `
                <button type="button" data-rm-id="${r.id}" class="btn w-100 text-start d-flex align-items-center gap-2 py-1 px-2 ${r.id === selId ? 'btn-primary' : 'btn-light'}" style="font-size:.86rem;">
                    <span style="width:9px;height:9px;border-radius:50%;background:${dot};flex:none;"></span>
                    <span class="flex-grow-1">${pretty(esc(r.secuencia))}</span>
                    <span class="${r.id === selId ? '' : 'text-muted'}" style="font-size:.78rem;">${Number(r.dias).toLocaleString('es-CL')} · ${pct(r.dias, data.total_jornadas)} %</span>
                </button>`;
            });
        });
        el.innerHTML = html;
        el.querySelectorAll('[data-rm-id]').forEach(b => b.addEventListener('click', () => { selId = parseInt(b.dataset.rmId); renderLista(); renderEditor(); }));
    }

    function renderEditor() {
        const el = $('rm-editor');
        const r = data.reglas.find(x => x.id === selId);
        if (!el || !r) return;
        const rs = roles(r.secuencia, r.lectura);
        const colorChip = { ent: 'background:#d1e7dd;color:#0f5132;', sal: 'background:#cfe2ff;color:#084298;', pausa: 'background:#fff3cd;color:#664d03;', muted: 'background:#f1f3f5;color:#6c757d;' };
        const puede = canEdit();
        const edit = puede && !r.activa;
        el.innerHTML = `
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
                <div class="d-flex gap-1">${r.secuencia.split('').map(c => `<span style="${colorChip[c === 'E' ? 'ent' : 'sal']}width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:600;">${c}</span>`).join('')}</div>
                <span class="text-muted" style="font-size:.82rem;">${Number(r.dias).toLocaleString('es-CL')} jornadas en la historia · ${Number(r.dias_abiertos).toLocaleString('es-CL')} en el tramo abierto · ${pct(r.dias, data.total_jornadas)} % del total</span>
            </div>
            <div style="font-size:.95rem;line-height:2.2;">Cuando el día tenga estas marcas, el sistema debe
                <select id="rm-lectura" class="form-select form-select-sm d-inline-block w-auto" ${edit ? '' : 'disabled'}>
                    <option value="RELOJ" ${r.lectura === 'RELOJ' ? 'selected' : ''}>leerlas como marcó el reloj</option>
                    <option value="EXTREMOS" ${r.lectura === 'EXTREMOS' ? 'selected' : ''}>tomar la primera y la última</option>
                    <option value="NINGUNA" ${r.lectura === 'NINGUNA' ? 'selected' : ''}>no leerlas (anomalía)</option>
                </select> y
                <select id="rm-accion" class="form-select form-select-sm d-inline-block w-auto" ${edit ? '' : 'disabled'}>
                    <option value="CALCULA" ${r.accion === 'CALCULA' ? 'selected' : ''}>no avisar nada</option>
                    <option value="CALCULA_Y_REVISA" ${r.accion === 'CALCULA_Y_REVISA' ? 'selected' : ''}>avisar para revisar (calcula igual)</option>
                    <option value="SOLO_REVISA" ${r.accion === 'SOLO_REVISA' ? 'selected' : ''}>pedir revisión antes de calcular</option>
                </select>.
            </div>
            <div class="d-flex position-relative my-3">
                <div style="position:absolute;left:8%;right:8%;top:13px;height:2px;background:#dee2e6;"></div>
                ${rs.map((x, k) => `
                <div class="flex-fill text-center position-relative px-1">
                    <div style="${colorChip[x[1]]}width:28px;height:28px;border-radius:50%;margin:0 auto;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:600;border:1px solid #ced4da;position:relative;">${k + 1}</div>
                    <div class="text-muted mt-1" style="font-size:.74rem;">${esc(x[0])}</div>
                </div>`).join('')}
            </div>
            <div class="bg-light rounded p-2 mb-2" style="font-size:.86rem;" id="rm-resultado">${esc(fraseResultado(r))}</div>
            <div class="text-muted mb-1" style="font-size:.78rem;">Colación</div>
            <div class="d-flex gap-1 flex-wrap mb-2" id="rm-colacion">
                ${[['TURNO', 'Del turno asignado'], ['MEDIDA', 'Medida con las marcas'], ['NINGUNA', 'Ninguna']].map(c => `
                    <button type="button" data-col="${c[0]}" class="btn btn-sm ${r.colacion === c[0] ? 'btn-primary' : 'btn-outline-secondary'}" ${edit ? '' : 'disabled'}>${c[1]}</button>`).join('')}
            </div>
            <div id="rm-opciones-wrap" ${r.accion === 'CALCULA' ? 'style="opacity:.5;"' : ''}>
                <div class="text-muted mb-1" style="font-size:.78rem;">Al revisar, la persona podrá (el sistema nunca inventa una marca)</div>
                <div class="d-flex gap-1 flex-wrap mb-2" id="rm-opciones">
                    ${OPCIONES.map(o => `<button type="button" data-op="${o[0]}" class="btn btn-sm ${(r.opciones_revision || []).includes(o[0]) ? 'btn-primary' : 'btn-outline-secondary'}" ${edit && r.accion !== 'CALCULA' ? '' : 'disabled'}>${(r.opciones_revision || []).includes(o[0]) ? '✓ ' : ''}${o[1]}</button>`).join('')}
                </div>
            </div>
            <div class="mb-2">
                <input type="text" id="rm-nota" class="form-control form-control-sm" maxlength="300" placeholder="Nota (opcional)" value="${esc(r.nota || '')}" ${edit ? '' : 'disabled'}>
            </div>
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                <span class="badge ${r.activa ? 'bg-success' : 'bg-secondary'}">${r.activa ? 'Encendida: el motor la usa' : 'Apagada: el motor no la usa'}</span>
                <div class="d-flex gap-2">
                    <button type="button" class="btn btn-sm btn-outline-secondary" id="rm-ver-dias">Ver los días con esta secuencia</button>
                    ${puede && data.motor_conectado ? (r.activa
                        ? '<button type="button" class="btn btn-sm btn-outline-danger" id="rm-correr" data-encender="0">Apagar esta regla</button>'
                        : '<button type="button" class="btn btn-sm btn-success" id="rm-correr" data-encender="1">Correr esta regla</button>') : ''}
                    ${edit && !r.activa ? '<button type="button" class="btn btn-sm btn-primary" id="rm-guardar">Guardar</button>' : ''}
                </div>
            </div>
            ${r.activa ? '<div class="text-muted mt-1" style="font-size:.78rem;">Para cambiar una regla encendida, primero apáguela: así el cambio corre con su propio antes y después.</div>' : ''}`;
        // Ediciones locales (solo en memoria hasta Guardar)
        $('rm-lectura').addEventListener('change', (e) => {
            r.lectura = e.target.value;
            if (r.lectura === 'NINGUNA') r.accion = 'SOLO_REVISA';
            renderEditor();
        });
        $('rm-accion').addEventListener('change', (e) => {
            r.accion = e.target.value;
            if (r.accion !== 'SOLO_REVISA' && r.lectura === 'NINGUNA') r.lectura = 'EXTREMOS';
            if (r.accion === 'CALCULA') r.opciones_revision = [];
            renderEditor();
        });
        el.querySelectorAll('#rm-colacion [data-col]').forEach(b => b.addEventListener('click', () => { r.colacion = b.dataset.col; renderEditor(); }));
        el.querySelectorAll('#rm-opciones [data-op]').forEach(b => b.addEventListener('click', () => {
            const op = b.dataset.op;
            const i = (r.opciones_revision = r.opciones_revision || []).indexOf(op);
            if (i >= 0) r.opciones_revision.splice(i, 1); else r.opciones_revision.push(op);
            renderEditor();
        }));
        $('rm-ver-dias').addEventListener('click', () => verDias(r));
        const g = $('rm-guardar');
        if (g) g.addEventListener('click', () => guardar(r));
        const c = $('rm-correr');
        if (c) c.addEventListener('click', () => correrRegla(r, c.dataset.encender === '1'));
    }

    const CAMPOS_TXT = {
        estado: 'Estado', hora_entrada_real: 'Entrada', hora_salida_real: 'Salida',
        horas_trabajadas: 'Horas', minutos_atraso: 'Atraso (min)', minutos_salida_adelantada: 'Salida adelantada (min)',
        minutos_deuda: 'Deuda (min)', minutos_extra_bruto: 'Extra bruto (min)', minutos_colacion: 'Colación (min)',
        observaciones: 'Observaciones',
    };

    async function correrRegla(r, encender) {
        const verbo = encender ? 'Correr' : 'Apagar';
        const nAb = Number(r.dias_abiertos);
        const detalle = encender
            ? `Se encenderá la regla y se recalcularán solo los días del tramo abierto con la secuencia ${pretty(r.secuencia)} (${nAb.toLocaleString('es-CL')} ${nAb === 1 ? 'día' : 'días'} con marcas del reloj, más los que tengan marcas manuales). Nunca el día en curso ni períodos cerrados.`
            : `Se apagará la regla y esos mismos días del tramo abierto se recalcularán de vuelta con la lógica de siempre.`;
        const ok = await Swal.fire({
            title: `${verbo} la regla ${pretty(r.secuencia)}`,
            html: `<div style="font-size:.95rem;text-align:left;">${detalle}<br><br>Al terminar verá el antes y el después de cada día que cambió.</div>`,
            icon: 'question', showCancelButton: true,
            confirmButtonText: `${verbo} ahora`, cancelButtonText: 'Cancelar',
        });
        if (!ok.isConfirmed) return;
        try {
            const res = await fetch(`${API}${r.id}/${encender ? 'correr' : 'apagar'}/`, { method: 'POST', headers: headers() });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) { toast(body.detail || 'No se pudo iniciar la corrida.', 'danger'); return; }
            seguirCorrida(body.id);
        } catch (e) {
            toast('No se pudo iniciar la corrida: sin conexión.', 'danger');
        }
    }

    function seguirCorrida(jobId) {
        const aviso = $('rm-corrida-aviso');
        const pinta = (j) => {
            if (!aviso) return;
            const prog = j.total ? ` · ${j.avance} de ${j.total} días` : '';
            aviso.innerHTML = `<div class="alert alert-warning py-2 mb-2" style="font-size:.88rem;">
                <div class="spinner-border spinner-border-sm me-1" role="status"></div>
                ${j.encender ? 'Corriendo' : 'Apagando'} la regla ${pretty(esc(j.secuencia))}${prog}… No cierre esta pantalla.</div>`;
        };
        const tick = async () => {
            try {
                const res = await fetch(`${API}corridas/${jobId}/`, { headers: headers() });
                const j = await res.json();
                if (!res.ok) throw new Error(j.detail || `HTTP ${res.status}`);
                if (j.estado === 'en_curso') { pinta(j); setTimeout(tick, 2000); return; }
                if (aviso) aviso.innerHTML = '';
                if (j.estado === 'fallo') {
                    abrirModal('La corrida no terminó bien', `<div class="alert alert-danger">${esc(j.error || 'Error desconocido')}</div>`);
                } else {
                    mostrarResultado(j);
                }
                selId = j.regla_id; init();
            } catch (e) {
                if (aviso) aviso.innerHTML = `<div class="alert alert-danger py-2 mb-2" style="font-size:.88rem;">No se pudo seguir la corrida: ${esc(e.message)}. Recargue la pestaña.</div>`;
            }
        };
        tick();
    }

    function mostrarResultado(j) {
        const r = j.resultado || {};
        const filas = (r.detalle || []).map(d => {
            const cambios = Object.entries(d.cambios || {}).filter(([k]) => k !== 'observaciones')
                .map(([k, v]) => `${CAMPOS_TXT[k] || k}: ${esc(String(v.antes ?? '—'))} → ${esc(String(v.despues ?? '—'))}`)
                .join('<br>');
            return `<tr><td>${esc(d.persona)}</td><td>${esc(d.fecha)}</td>
                <td>${d.solo_aviso ? '<span class="badge bg-info text-dark">Solo cambia la anotación (horas iguales)</span>' : (cambios || '—')}</td></tr>`;
        }).join('');
        const cuerpo = `
            <div class="mb-2" style="font-size:.9rem;">
                Regla <strong>${pretty(esc(j.secuencia))}</strong> ${j.encender ? 'encendida' : 'apagada'}.
                Días revisados: <strong>${r.dias_revisados ?? 0}</strong> ·
                cambiaron: <strong>${r.dias_cambiados ?? 0}</strong>
                (${r.dias_con_horas_distintas ?? 0} con horas o estado distinto, ${r.dias_solo_aviso ?? 0} solo con una anotación nueva y las horas iguales).
            </div>
            ${filas ? `<div class="table-responsive"><table class="table table-sm align-middle" style="font-size:.84rem;">
                <thead><tr><th>Persona</th><th>Fecha</th><th>Qué cambió (antes → después)</th></tr></thead>
                <tbody>${filas}</tbody></table></div>`
                : '<div class="text-muted">Ningún día cambió.</div>'}`;
        abrirModal(`Resultado: ${j.encender ? 'correr' : 'apagar'} la regla ${pretty(j.secuencia)}`, cuerpo);
    }

    async function guardar(r) {
        const nota = $('rm-nota') ? $('rm-nota').value.trim() : (r.nota || '');
        try {
            const res = await fetch(`${API}${r.id}/`, {
                method: 'PUT', headers: headers(),
                body: JSON.stringify({ lectura: r.lectura, colacion: r.colacion, accion: r.accion, opciones_revision: r.opciones_revision || [], nota })
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) { toast(body.detail || 'No se pudo guardar la regla.', 'danger'); return; }
            Object.assign(r, body.regla, { dias: r.dias, dias_abiertos: r.dias_abiertos, grupo: r.grupo });
            toast(`Regla ${pretty(r.secuencia)} guardada.`);
            renderLista(); renderEditor();
        } catch (e) {
            toast('No se pudo guardar la regla: sin conexión.', 'danger');
        }
    }

    async function guardarRebote() {
        const segundos = parseInt($('rm-rebote').value, 10);
        try {
            const res = await fetch(`${API}rebote/`, { method: 'PUT', headers: headers(), body: JSON.stringify({ segundos }) });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) { toast(body.detail || 'No se pudo guardar el rebote.', 'danger'); return; }
            data.rebote_segundos = segundos;
            toast('Rebote guardado.');
        } catch (e) {
            toast('No se pudo guardar el rebote: sin conexión.', 'danger');
        }
    }

    async function verDias(r) {
        let cuerpo = '<div class="text-center py-3 text-muted"><div class="spinner-border spinner-border-sm"></div> Buscando…</div>';
        abrirModal(`Días del tramo abierto con la secuencia ${pretty(r.secuencia)}`, cuerpo);
        try {
            const res = await fetch(`${API}${r.id}/dias/`, { headers: headers() });
            const body = await res.json();
            if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
            cuerpo = body.dias.length ? `
                <div class="text-muted mb-2" style="font-size:.82rem;">Desde el ${esc(body.desde)} · ${body.dias.length} ${body.dias.length === 1 ? 'día' : 'días'} · solo lectura (marcas del reloj, sin manuales)</div>
                <div class="table-responsive"><table class="table table-sm align-middle" style="font-size:.84rem;">
                <thead><tr><th>Persona</th><th>Fecha</th><th>Marcas</th><th>Estado</th><th class="text-end">Horas</th><th class="text-end">Deuda (min)</th></tr></thead>
                <tbody>${body.dias.map(d => `<tr><td>${esc(d.persona)}</td><td>${esc(d.fecha)}</td><td>${esc(d.marcas)}</td><td>${esc(d.estado)}</td><td class="text-end">${Number(d.horas).toLocaleString('es-CL')}</td><td class="text-end">${Number(d.deuda).toLocaleString('es-CL')}</td></tr>`).join('')}</tbody>
                </table></div>` :
                '<div class="text-muted py-3">No hay días con esta secuencia en el tramo abierto.</div>';
        } catch (e) {
            cuerpo = `<div class="alert alert-danger">${esc(e.message)}</div>`;
        }
        const mb = document.getElementById('rm-modal-body');
        if (mb) mb.innerHTML = cuerpo;
    }

    function abrirModal(titulo, cuerpo) {
        let m = document.getElementById('rm-modal');
        if (!m) {
            m = document.createElement('div');
            m.id = 'rm-modal';
            m.className = 'modal fade';
            m.tabIndex = -1;
            m.innerHTML = `<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content">
                <div class="modal-header"><h5 class="modal-title" id="rm-modal-title"></h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div>
                <div class="modal-body" id="rm-modal-body"></div></div></div>`;
            document.body.appendChild(m);
        }
        document.getElementById('rm-modal-title').textContent = titulo;
        document.getElementById('rm-modal-body').innerHTML = cuerpo;
        bootstrap.Modal.getOrCreateInstance(m).show();
    }

    return { init };
})();

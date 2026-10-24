// ─────────────────────────────────────────────────────────────────────────────
// Reglas de marcaciones (Configuración) — asistente de una sola página.
// El motor usa SOLO las reglas encendidas. Las reglas no vienen escritas en el
// código: viven en la base, se crean desde la bandeja «Secuencias encontradas sin
// regla» y se configuran aquí. «Correr esta regla» la enciende y recalcula solo
// los días del tramo abierto con esa secuencia (nunca el día en curso ni períodos
// cerrados) y muestra el antes y el después; «Apagar esta regla» lo deshace.
// Las marcas se nombran siempre con la palabra completa: ENTRADA y SALIDA.
// Los textos van con comillas y concatenación (nada de plantillas anidadas): el
// minificador del servidor se come los espacios dentro de ellas.
// ─────────────────────────────────────────────────────────────────────────────
const ReglasMarcasModule = (() => {
    const API = '/api/configuracion/reglas-marcas/';
    const GRUPOS = ['Bien marcadas', 'Se repite un tipo', 'Falta una marca', 'Una sola marca'];
    const PALABRA = { E: 'ENTRADA', S: 'SALIDA' };
    const OPCIONES = [
        ['AGREGAR_SALIDA', 'Escribir la SALIDA que falta'],
        ['AGREGAR_ENTRADA', 'Escribir la ENTRADA que falta'],
        ['RECLASIFICAR', 'Cambiar si una marca es ENTRADA o SALIDA'],
        ['CONFIRMAR', 'Confirmar que está bien'],
    ];
    const CAMPOS_TXT = {
        estado: 'Estado', hora_entrada_real: 'ENTRADA', hora_salida_real: 'SALIDA', horas_trabajadas: 'Horas',
        minutos_atraso: 'Atraso (min)', minutos_salida_adelantada: 'Salida adelantada (min)', minutos_deuda: 'Tiempo que faltó (min)',
        minutos_extra_bruto: 'Extra (min)', minutos_colacion: 'Colación descontada (min)', observaciones: 'Anotación',
    };
    const ESTADO_TXT = { JORNADA_ESPECIAL: 'Jornada especial', ANOMALIA: 'En revisión, sin horas', EN_CURSO: 'En curso' };
    // Cualquier estado del día en palabras (los de arriba con su texto propio; el resto, sin guiones bajos).
    const estadoTxt = (e) => ESTADO_TXT[e] || String(e || '').replace(/_/g, ' ').toLowerCase().replace(/^./, c => c.toUpperCase());

    let data = null;
    let tipo = 'CICLO_INTELIGENTE';
    let selId = null;
    let cargando = false;
    const ejemplos = {};   // regla.id -> { dias, total } · días reales del tramo abierto
    const ensayos = {};    // regla.id -> { clave, estado, res, error } · «cómo quedaría», sin guardar

    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const canEdit = () => (typeof AuthService !== 'undefined') ? AuthService.hasPermission('configuracion.reglas_marcaciones') : false;
    const headers = () => ({ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('access_token') });
    const palabras = (sec) => String(sec || '').split('').map(c => PALABRA[c] || c).join(' · ');
    const num = (x, dec) => Number(x || 0).toLocaleString('es-CL', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    const toast = (msg, tipo_) => { if (typeof showToast === 'function') showToast(msg, tipo_ || 'success'); else alert(msg); };

    function durMin(min) {
        const t = Math.round(Number(min) || 0);
        if (t < 60) return t + ' min';
        const h = Math.floor(t / 60), m = t % 60;
        return m ? h + ' h ' + String(m).padStart(2, '0') : h + ' h';
    }
    const toMin = (t) => { const p = String(t || '').split(':'); return parseInt(p[0], 10) * 60 + parseInt(p[1] || '0', 10); };

    function chipsSecuencia(sec, grande) {
        const sep = grande ? '<span class="rmx-flecha" aria-hidden="true">→</span>' : '<span class="rmx-flecha-ch" aria-hidden="true">›</span>';
        return String(sec || '').split('').map(c => '<span class="rmx-chip ' + (c === 'E' ? 'rmx-chip-in' : 'rmx-chip-out') + (grande ? ' rmx-chip-g' : '') + '">' + (PALABRA[c] || esc(c)) + '</span>').join(sep);
    }

    // ── Estilos propios de la pestaña (prefijo rmx-) ─────────────────────────
    function estilos() {
        if ($('rmx-estilos')) return;
        const css = [
            '.rmx{color:#0f172a}',
            '.rmx-card{background:#fff;border:1px solid #e3e8ef;border-radius:14px}',
            '.rmx-chip{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:999px;font-weight:700;font-size:.66rem;letter-spacing:.3px;white-space:nowrap}',
            '.rmx-chip-g{height:32px;padding:0 13px;font-size:.84rem}',
            '.rmx-chip-in{background:#dcfce7;color:#14532d}.rmx-chip-out{background:#dbeafe;color:#1e3a8a}',
            '.rmx-flecha{color:#94a3b8;margin:0 6px;font-size:1.1rem}.rmx-flecha-ch{color:#94a3b8;margin:0 2px;font-size:.8rem}',
            '.rmx-kicker{font-size:.72rem;font-weight:700;color:#475569;letter-spacing:.6px}',
            '.rmx-pill{display:inline-flex;align-items:center;min-height:28px;padding:0 12px;border-radius:999px;font-size:.78rem;font-weight:600}',
            '.rmx-on{background:#dcfce7;color:#14532d}.rmx-off{background:#f1f5f9;color:#475569}.rmx-warn{background:#fef3c7;color:#92400e}',
            '.rmx-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}',
            '.rmx-stat{background:#f8fafc;border-radius:10px;padding:10px 12px}.rmx-stat b{display:block;font-size:1.3rem;font-weight:800}.rmx-stat span{font-size:.76rem;color:#475569}',
            '.rmx-intro{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}',
            '.rmx-ve{background:#eef2ff;border:1px solid #c7d2fe;border-radius:14px;color:#1e1b4b}',
            '.rmx-dia{display:grid;grid-template-columns:165px minmax(0,1fr) 210px;gap:14px;align-items:center;padding:10px 0;border-bottom:1px solid #eef1f6}',
            '.rmx-dia:last-child{border-bottom:0}',
            '.rmx-res{background:#f8fafc;border-radius:10px;padding:8px 10px;font-size:.78rem;line-height:1.4}.rmx-res b{display:block;font-size:1.12rem;font-weight:800}',
            '.rmx-tl{position:relative;height:104px}',
            '.rmx-ax{position:absolute;left:0;right:0;top:46px;height:6px;border-radius:3px;background:#edf1f6}',
            '.rmx-hor{position:absolute;top:38px;height:22px;border-radius:7px;background:#eef4ff;border:1.5px dashed #93b4f5}',
            '.rmx-seg{position:absolute;top:46px;height:6px;border-radius:3px;background:#86efac}',
            '.rmx-pau{position:absolute;top:46px;height:6px;border-radius:3px;background:#f59e0b}',
            '.rmx-dot{position:absolute;top:40px;width:18px;height:18px;margin-left:-9px;border-radius:50%;border:3px solid #fff;box-shadow:0 0 0 1.5px #475569}',
            '.rmx-dot-s{top:43px;width:12px;height:12px;margin-left:-6px;border-width:2px}',
            '.rmx-dot-in{background:#16a34a}.rmx-dot-out{background:#2563eb}',
            '.rmx-tag{position:absolute;top:0;transform:translateX(-50%);text-align:center;font-size:.64rem;line-height:1.2;white-space:nowrap}.rmx-tag b{display:block;font-size:.76rem}',
            '.rmx-tag-in{color:#14532d}.rmx-tag-out{color:#1e3a8a}',
            '.rmx-ptag{position:absolute;top:64px;transform:translateX(-50%);font-size:.66rem;font-weight:600;color:#92400e;background:#fef3c7;border-radius:999px;padding:1px 8px;white-space:nowrap}',
            '.rmx-mtag{position:absolute;top:64px;transform:translateX(-50%);font-size:.64rem;color:#334155;background:#f1f5f9;border-radius:999px;padding:1px 7px;white-space:nowrap}',
            '.rmx-tick{position:absolute;top:88px;transform:translateX(-50%);font-size:.6rem;color:#64748b}',
            '.rmx-paso{display:grid;grid-template-columns:42px minmax(0,1fr);gap:0 12px}',
            '.rmx-num{width:34px;height:34px;border-radius:50%;background:#1b2f8f;color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;flex:none}',
            '.rmx-rail{width:2px;background:#d8dee8;margin:6px 0 0 16px;flex:1}',
            '.rmx-ops{display:grid;gap:12px}.rmx-c2{grid-template-columns:repeat(2,minmax(0,1fr))}.rmx-c3{grid-template-columns:repeat(3,minmax(0,1fr))}',
            '.rmx-op{display:flex;flex-direction:column;gap:5px;padding:12px 14px;border-radius:12px;border:1.5px solid #e3e8ef;background:#fff;position:relative;cursor:pointer;margin:0;font-size:.84rem;color:#334155}',
            '.rmx-op input{width:17px;height:17px;margin:0;accent-color:#1b2f8f;flex:none}',
            '.rmx-op-sel{border-color:#1b2f8f;background:#f6f8ff;box-shadow:0 0 0 4px rgba(27,47,143,.08)}',
            '.rmx-op-off{background:#f8fafc;color:#64748b;cursor:default}',
            '.rmx-op-t{display:flex;align-items:center;gap:9px;font-weight:700;font-size:.88rem;color:#0f172a}',
            '.rmx-op-off .rmx-op-t{color:#64748b}',
            '.rmx-badge{position:absolute;top:-10px;right:12px;font-size:.64rem;font-weight:700;padding:2px 9px;border-radius:999px;color:#fff}',
            '.rmx-b-sug{background:#15803d}.rmx-b-new{background:#6d28d9}.rmx-b-na{background:#64748b}',
            '.rmx-ef{font-size:.78rem;color:#334155;background:#f8fafc;border-radius:9px;padding:7px 9px}',
            '.rmx-src{display:inline-flex;align-items:center;font-size:.68rem;font-weight:600;color:#334155;background:#f1f5f9;border:1px solid #d8dee8;border-radius:999px;padding:1px 8px;white-space:nowrap}',
            '.rmx-nota{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border-radius:10px;background:#f6f8ff;border:1px solid #c7d4f7;font-size:.84rem}',
            '.rmx-na{font-size:.84rem;color:#64748b;background:#f8fafc;border-radius:10px;padding:10px 12px}',
            '.rmx-tab{width:100%;border-collapse:collapse;font-size:.78rem}.rmx-tab th{color:#475569;font-weight:600;text-align:left;padding:5px 7px;border-bottom:1px solid #e3e8ef}.rmx-tab td{padding:5px 7px;border-bottom:1px solid #f1f4f8}',
            '.rmx-igual{display:inline-flex;min-height:22px;align-items:center;padding:0 9px;border-radius:999px;font-size:.72rem;font-weight:600;background:#f1f5f9;color:#475569}',
            '.rmx-cambia{display:inline-flex;min-height:22px;align-items:center;padding:0 9px;border-radius:999px;font-size:.72rem;font-weight:600;background:#fef3c7;color:#92400e}',
            '.rmx-barra{position:sticky;bottom:0;z-index:5;background:#0f172a;color:#e2e8f0;border-radius:14px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}',
            '.rmx-barra p{margin:0;font-size:.84rem;line-height:1.45;max-width:640px}.rmx-barra b{color:#fff}',
            '.rmx-btn{min-height:40px;padding:0 14px;border-radius:9px;font-weight:700;font-size:.84rem;border:1px solid transparent}',
            '.rmx-btn-sec{background:transparent;border-color:#64748b;color:#e2e8f0}.rmx-btn-pri{background:#1d4ed8;color:#fff}.rmx-btn-ok{background:#16a34a;color:#fff}.rmx-btn-no{background:#dc2626;color:#fff}',
            '.rmx-btn:disabled{opacity:.5}',
            '.rmx-lista td{vertical-align:middle}.rmx-lista tr.rmx-sel td{background:#eef2ff}',
            '.rmx-fila{display:inline-flex;flex-wrap:nowrap;align-items:center;white-space:nowrap}',
            '#rm-lista-det>summary{list-style:none}#rm-lista-det>summary::-webkit-details-marker{display:none}',
            '#rm-lista-det>summary::before{content:"▸";color:#64748b;margin-right:8px;display:inline-block}#rm-lista-det[open]>summary::before{content:"▾"}',
            '@media (max-width: 991px){.rmx-dia{grid-template-columns:1fr}.rmx-intro,.rmx-c2,.rmx-c3,.rmx-stats{grid-template-columns:1fr}}',
        ].join('\n');
        const st = document.createElement('style');
        st.id = 'rmx-estilos';
        st.textContent = css;
        document.head.appendChild(st);
    }

    // ── Foto de lo guardado, para saber si hay cambios sin guardar ───────────
    function _fotoRegla(r) {
        return { lectura: r.lectura, colacion: r.colacion, accion: r.accion, avisa: r.avisa_fuera_de_ciclo ? 1 : 0,
                 opciones: (r.opciones_revision || []).slice().sort().join(',') };
    }
    function _hayCambios(r) {
        if (!r || !r._guardada) return false;
        const a = r._guardada, b = _fotoRegla(r);
        return a.lectura !== b.lectura || a.colacion !== b.colacion || a.accion !== b.accion || a.avisa !== b.avisa || a.opciones !== b.opciones;
    }
    function _revertir(r) {
        const g = r._guardada;
        if (!g) return;
        r.lectura = g.lectura; r.colacion = g.colacion; r.accion = g.accion; r.avisa_fuera_de_ciclo = g.avisa;
        r.opciones_revision = g.opciones ? g.opciones.split(',') : [];
    }

    // ── Lo que ve el sistema: se arma con la forma de la secuencia ───────────
    const alterna = (sec) => /^(ES)+$/.test(String(sec || ''));
    const hayPausaMedible = (sec) => String(sec || '').slice(1, -1).indexOf('SE') >= 0;

    function diagnostico(sec) {
        const s = String(sec || ''), n = s.length;
        if (n === 1) return 'El día tiene una sola marca, una ' + PALABRA[s] + '. Falta la otra: no hay cómo saber cuánto trabajó.';
        if (alterna(s)) {
            const pausas = n / 2 - 1;
            if (pausas === 0) return 'El día tiene dos marcas: una ENTRADA y una SALIDA. La persona no marcó la colación, así que no hay pausa que medir.';
            if (pausas === 1) return 'Cuatro marcas: la ENTRADA, la SALIDA a colación, la ENTRADA de regreso y la SALIDA del día. Hay una sola pausa: esa es la colación.';
            return n + ' marcas con ' + pausas + ' pausas: la más parecida a la colación del horario es la colación; las otras cuentan como permiso.';
        }
        const partes = [n + ' marcas: ' + palabras(s) + '.'];
        if (s[0] === 'S') partes.push('La primera marca dice SALIDA, pero es la primera del día.');
        if (s[n - 1] === 'E') partes.push('La última marca dice ENTRADA: puede faltar la SALIDA del final o estar mal rotulada.');
        for (let i = 1; i < n; i++) {
            if (s[i] === s[i - 1]) { partes.push('Hay dos ' + (s[i] === 'E' ? 'ENTRADAS' : 'SALIDAS') + ' seguidas: puede ser un doble toque o una marca mal rotulada; los minutos entre ellas lo dicen.'); break; }
        }
        if (n % 2 === 1) partes.push('Son ' + n + ' marcas, un número impar: falta una marca o sobra una.');
        return partes.join(' ');
    }

    function papeles(sec, lectura) {
        const s = String(sec || ''), n = s.length;
        if (lectura === 'NINGUNA') return 'No se leen: el día espera a que una persona lo complete.';
        const r = Array(n).fill('no se usa');
        if (lectura === 'RELOJ') {
            const pares = [];
            for (let i = 0; i < n;) { if (s[i] === 'E' && s[i + 1] === 'S') { pares.push([i, i + 1]); i += 2; } else i++; }
            pares.forEach((p, k) => {
                r[p[0]] = k === 0 ? 'ENTRADA del día' : 'ENTRADA de regreso';
                r[p[1]] = k === pares.length - 1 ? 'SALIDA del día' : 'SALIDA a pausa';
            });
        } else {
            r[0] = 'ENTRADA del día' + (s[0] === 'E' ? '' : ' (el reloj dijo SALIDA)');
            r[n - 1] = 'SALIDA del día' + (s[n - 1] === 'S' ? '' : ' (el reloj dijo ENTRADA)');
            for (let j = 1; j < n - 2;) {
                if (s[j] === 'S' && s[j + 1] === 'E') { r[j] = 'SALIDA a pausa'; r[j + 1] = 'ENTRADA de regreso'; j += 2; } else j++;
            }
        }
        return r.map((x, i) => (i + 1) + 'ª ' + x).join(' · ');
    }

    function fraseRegla(r) {
        const sec = palabras(r.secuencia);
        if (r.lectura === 'NINGUNA') {
            const ops = (r.opciones_revision || []).map(o => (OPCIONES.find(x => x[0] === o) || [o, o])[1].toLowerCase());
            return 'Los días ' + sec + ' no se calculan solos: quedan «por revisar» y sin horas hasta que una persona pueda ' + (ops.join(' o ') || 'resolverlo') + '.';
        }
        let f = 'Los días ' + sec + (r.lectura === 'EXTREMOS' ? ' se leen con la primera marca como ENTRADA y la última como SALIDA' : ' se leen como los marcó el reloj') + ', contra el horario asignado de ese día';
        if (r.colacion === 'TURNO') f += '; se descuenta la colación del horario si la persona estuvo al menos el mínimo';
        else if (r.colacion === 'MEDIDA') f += '; se descuenta lo mayor entre la colación del horario y la pausa medida (bajo el mínimo, solo la pausa)';
        else f += '; no se descuenta colación';
        if (r.accion === 'CALCULA') f += r.avisa_fuera_de_ciclo ? '; avisa solo si las marcas no calzan con ningún ciclo del horario' : '; no se avisa';
        else f += '; se calcula y queda en «Días por revisar»';
        return f + '.';
    }

    async function init() {
        const cont = $('reglas-marcas-container');
        if (!cont || cargando) return;
        cargando = true;
        estilos();
        try {
            const res = await fetch(API + '?tipo=' + encodeURIComponent(tipo), { headers: headers() });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            data = await res.json();
            data.reglas.forEach(r => { r.avisa_fuera_de_ciclo = r.avisa_fuera_de_ciclo ? 1 : 0; r._guardada = _fotoRegla(r); });
            Object.keys(ejemplos).forEach(k => delete ejemplos[k]);
            Object.keys(ensayos).forEach(k => delete ensayos[k]);
            if (!selId && data.reglas.length) selId = data.reglas[0].id;
            render();
        } catch (e) {
            cont.innerHTML = '<div class="alert alert-danger">No se pudieron cargar las reglas de marcaciones. ' + esc(e.message) + '</div>';
        } finally {
            cargando = false;
        }
    }

    function render() {
        const cont = $('reglas-marcas-container');
        if (!cont || !data) return;
        const tiposBtns = (data.tipos || []).map(t =>
            '<button type="button" class="btn btn-sm ' + (t.tipo === tipo ? 'btn-primary' : 'btn-outline-secondary') + '" data-rm-tipo="' + esc(t.tipo) + '">'
            + esc(t.tipo === 'CICLO_INTELIGENTE' ? 'Ciclo Inteligente' : t.tipo === 'BOLSA_FLEXIBLE' ? 'Bolsa Flexible' : t.tipo) + ' · ' + t.personas + ' personas</button>').join(' ');
        const activas = data.reglas.filter(r => r.activa).length;
        cont.innerHTML =
            '<div class="rmx">'
            + '<div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">'
            + '<h4 class="mb-0"><i class="bi bi-diagram-3" aria-hidden="true"></i> Reglas de marcaciones</h4>'
            + '<div class="d-flex gap-2 flex-wrap">' + tiposBtns + '</div></div>'
            + '<div class="text-muted mb-2" style="font-size:.86rem;">El cálculo usa <strong>solo las reglas encendidas</strong> (' + activas + ' de ' + data.reglas.length + '). '
            + 'Tramo abierto desde el ' + esc(data.tramo_abierto_desde || '') + ': ' + Number(data.total_jornadas_tramo_abierto || 0).toLocaleString('es-CL') + ' días con marcas del reloj.</div>'
            + '<div id="rm-corrida-aviso"></div>'
            + '<div id="rm-por-revisar" class="mb-2"></div>'
            + '<div id="rm-ajustes" class="mb-3"></div>'
            + (data.reglas.length
                ? '<details id="rm-lista-det" class="rmx-card mb-3"' + (selId ? '' : ' open') + '>'
                  + '<summary id="rm-lista-sum" class="px-3 py-2" style="cursor:pointer;"></summary>'
                  + '<div id="rm-lista" class="px-2 pb-2" style="max-height:440px;overflow:auto;"></div></details>'
                  + '<div id="rm-editor"></div>'
                : '<div class="rmx-card p-4 text-muted"><strong>Sin reglas para este tipo de horario.</strong><br>'
                  + (tipo === 'CICLO_INTELIGENTE' ? 'Cree la regla de cada secuencia desde la bandeja de abajo.' : 'Bolsa Flexible conserva su lógica y esta pestaña no la toca.') + '</div>')
            + bandejaSinRegla()
            + '</div>';
        cont.querySelectorAll('[data-rm-tipo]').forEach(b => b.addEventListener('click', () => { tipo = b.dataset.rmTipo; selId = null; init(); }));
        cont.querySelectorAll('[data-rm-crear]').forEach(b => b.addEventListener('click', () => crearRegla(b.dataset.rmCrear)));
        renderAjustes();
        if (data.reglas.length) { renderLista(); renderEditor(); }
        if (data.corrida_en_curso && data.corrida_en_curso.estado === 'en_curso') seguirCorrida(data.corrida_en_curso.id);
        cargarPorRevisar();
    }

    function bandejaSinRegla() {
        const sin = data.secuencias_sin_regla || [];
        if (!sin.length) return '';
        return '<div class="rmx-card p-3 mt-3"><div class="fw-semibold mb-1">Secuencias encontradas sin regla</div>'
            + '<div class="text-muted" style="font-size:.84rem;">Mientras no tengan regla, el cálculo las lee como siempre. Cree su regla una vez: nace apagada y usted la configura y la corre cuando quiera.</div>'
            + '<div class="mt-2 d-flex flex-wrap gap-2">'
            + sin.map(s => '<span class="rmx-card d-inline-flex align-items-center gap-2 px-2 py-1" style="font-size:.8rem;">' + chipsSecuencia(s.secuencia, false)
                + ' · ' + s.dias + ' días' + (canEdit() ? ' <button type="button" class="btn btn-sm btn-outline-primary py-0" data-rm-crear="' + esc(s.secuencia) + '">Crear regla</button>' : '') + '</span>').join('')
            + '</div></div>';
    }

    // ── Ajustes de la pestaña (valores en la tabla `ajustes`) ────────────────
    function renderAjustes() {
        const el = $('rm-ajustes');
        if (!el) return;
        const desc = data.ajustes_descripcion || {};
        const vals = data.ajustes || {};
        const puede = canEdit();
        const filas = Object.keys(desc).map(clave => {
            const d = desc[clave];
            const unidad = /_segundos$/.test(clave) ? 'segundos' : 'minutos';
            const v = vals[clave];
            return '<div class="d-flex flex-wrap align-items-center gap-2 py-1" style="font-size:.84rem;">'
                + '<label for="rm-aj-' + esc(clave) + '" style="flex:1 1 320px;">' + esc(d.texto) + '</label>'
                + '<span class="d-inline-flex align-items-center gap-1"><input type="number" class="form-control form-control-sm" style="width:96px" id="rm-aj-' + esc(clave) + '" min="' + d.min + '" max="' + d.max + '" value="' + (v == null ? '' : esc(v)) + '"' + (puede ? '' : ' disabled') + '> ' + unidad + '</span>'
                + (puede ? '<button type="button" class="btn btn-sm btn-outline-primary" data-rm-aj="' + esc(clave) + '">Guardar</button>' : '')
                + (v == null ? '<span class="rmx-pill rmx-warn">Sin configurar: no se usa</span>' : '')
                + '</div>';
        }).join('');
        el.innerHTML = '<details class="rmx-card px-3 py-2"><summary class="fw-semibold" style="cursor:pointer;">Ajustes de las reglas <span class="text-muted fw-normal" style="font-size:.82rem;">· valen para todas las secuencias</span></summary>'
            + '<div class="pt-2">' + filas + '</div></details>';
        el.querySelectorAll('[data-rm-aj]').forEach(b => b.addEventListener('click', () => guardarAjuste(b.dataset.rmAj)));
    }

    async function guardarAjuste(clave) {
        const inp = $('rm-aj-' + clave);
        const valor = inp ? parseFloat(inp.value) : NaN;
        try {
            const res = await fetch(API + 'ajustes/', { method: 'PUT', headers: headers(), body: JSON.stringify({ clave: clave, valor: valor }) });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) { toast(body.detail || 'No se pudo guardar el ajuste.', 'danger'); return; }
            data.ajustes[clave] = valor;
            toast('Ajuste guardado.');
            renderAjustes();
        } catch (e) {
            toast('No se pudo guardar el ajuste: sin conexión.', 'danger');
        }
    }

    // ── Lista de secuencias ──────────────────────────────────────────────────
    function renderLista() {
        const el = $('rm-lista');
        if (!el) return;
        const actual = data.reglas.find(x => x.id === selId);
        const sum = $('rm-lista-sum');
        if (sum) sum.innerHTML = '<span class="d-inline-flex align-items-center flex-wrap gap-2" style="vertical-align:middle;">'
            + '<span class="fw-semibold">Secuencia elegida</span>'
            + (actual ? '<span class="rmx-fila">' + chipsSecuencia(actual.secuencia, false) + '</span>' : '<span class="text-muted">ninguna</span>')
            + '<span class="text-muted" style="font-size:.82rem;">· cambiar (' + data.reglas.length + ' secuencias)</span></span>';
        let filas = '';
        GRUPOS.forEach(g => {
            const grupo = data.reglas.filter(r => r.grupo === g);
            if (!grupo.length) return;
            filas += '<tr><td colspan="3" class="text-muted border-0 pt-2 pb-1" style="font-size:.74rem;font-weight:600;">' + esc(g) + '</td></tr>';
            grupo.forEach(r => {
                const sel = r.id === selId;
                filas += '<tr data-rm-id="' + r.id + '" class="' + (sel ? 'rmx-sel' : '') + '" style="cursor:pointer;">'
                    + '<td><span class="rmx-fila">' + chipsSecuencia(r.secuencia, false) + '</span></td>'
                    + '<td class="text-end text-nowrap" style="font-size:.78rem;"><strong>' + Number(r.dias_abiertos).toLocaleString('es-CL') + '</strong><div class="text-muted" style="font-size:.68rem;">' + Number(r.dias).toLocaleString('es-CL') + ' en total</div></td>'
                    + '<td class="text-center">' + (r.activa ? '<i class="bi bi-check-circle-fill text-success" title="Encendida: el cálculo la usa"></i>' : '<span class="text-muted" title="Apagada: el cálculo no la usa">—</span>') + '</td></tr>';
            });
        });
        el.innerHTML = '<div class="table-responsive"><table class="table table-sm table-hover mb-0 rmx-lista">'
            + '<thead><tr class="text-muted" style="font-size:.68rem;"><th class="fw-semibold">SECUENCIA</th><th class="fw-semibold text-end">DÍAS EN EL TRAMO ABIERTO</th><th class="fw-semibold text-center">ENCENDIDA</th></tr></thead>'
            + '<tbody>' + filas + '</tbody></table></div>';
        el.querySelectorAll('[data-rm-id]').forEach(b => b.addEventListener('click', () => {
            const nuevoId = parseInt(b.dataset.rmId, 10);
            if (nuevoId !== selId) {
                const actual = data.reglas.find(x => x.id === selId);
                if (actual && _hayCambios(actual)) {
                    _revertir(actual);
                    toast('La regla ' + palabras(actual.secuencia) + ' tenía cambios sin guardar: se descartaron. Para conservarlos, apriete «Guardar» antes de cambiar de regla.', 'warning');
                }
            }
            selId = nuevoId; renderLista(); renderEditor();
            const det = $('rm-lista-det');
            if (det) det.open = false;
            const ed = $('rm-editor');
            if (ed) ed.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }));
    }

    // ── Días de ejemplo y ensayo ─────────────────────────────────────────────
    const claveEnsayo = (r) => [r.lectura, r.colacion, r.accion, r.avisa_fuera_de_ciclo ? 1 : 0, (r.opciones_revision || []).slice().sort().join('|')].join('~');

    async function cargarEjemplos(r) {
        if (ejemplos[r.id]) return;
        ejemplos[r.id] = { cargando: true };
        try {
            const res = await fetch(API + r.id + '/dias-ejemplo/', { headers: headers() });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.detail || ('HTTP ' + res.status));
            ejemplos[r.id] = { dias: body.dias || [], total: body.total || 0 };
        } catch (e) {
            ejemplos[r.id] = { dias: [], total: 0, error: e.message };
        }
        if (selId === r.id) renderEditor();
    }

    async function ensayar(r) {
        const clave = claveEnsayo(r);
        ensayos[r.id] = { clave: clave, estado: 'corriendo' };
        renderEditor();
        try {
            const res = await fetch(API + r.id + '/ensayo/', {
                method: 'POST', headers: headers(),
                body: JSON.stringify({ lectura: r.lectura, colacion: r.colacion, accion: r.accion,
                                       opciones_revision: r.opciones_revision || [], avisa_fuera_de_ciclo: r.avisa_fuera_de_ciclo ? 1 : 0 })
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(body.detail || ('HTTP ' + res.status));
            ensayos[r.id] = { clave: clave, estado: 'listo', res: body };
        } catch (e) {
            ensayos[r.id] = { clave: clave, estado: 'error', error: e.message };
        }
        if (selId === r.id) renderEditor();
    }

    function minutosDe(fh, fechaBase) {
        const f = String(fh), b = String(fechaBase).slice(0, 10);
        const dia = Date.UTC(+f.slice(0, 4), +f.slice(5, 7) - 1, +f.slice(8, 10));
        const base = Date.UTC(+b.slice(0, 4), +b.slice(5, 7) - 1, +b.slice(8, 10));
        return Math.round((dia - base) / 60000) + parseInt(f.slice(11, 13), 10) * 60 + parseInt(f.slice(14, 16), 10);
    }
    function marcasDe(d) {
        return String(d.marcas_completas || '').split(',').filter(Boolean).map(x => {
            const p = x.split('|');
            return { fh: p[0], t: p[1], min: minutosDe(p[0], d.fecha) };
        });
    }
    function horarioDe(d) {
        if (!d.hora_entrada_teorica || !d.hora_salida_teorica || !(Number(d.horas_teoricas) > 0)) return null;
        const a = toMin(d.hora_entrada_teorica), b = toMin(d.hora_salida_teorica);
        return { a: a, b: b <= a ? b + 1440 : b };
    }
    function ejeDe(dias) {
        let lo = Infinity, hi = -Infinity;
        dias.forEach(d => {
            marcasDe(d).forEach(m => { lo = Math.min(lo, m.min); hi = Math.max(hi, m.min); });
            const h = horarioDe(d);
            if (h) { lo = Math.min(lo, h.a); hi = Math.max(hi, h.b); }
        });
        if (!isFinite(lo)) return null;
        lo = Math.floor((lo - 30) / 120) * 120;
        hi = Math.ceil((hi + 30) / 120) * 120;
        return { lo: lo, hi: Math.max(hi, lo + 480) };
    }
    function lineaTiempo(d, eje) {
        const tot = eje.hi - eje.lo;
        const pos = (m) => ((m - eje.lo) / tot * 100).toFixed(2) + '%';
        const ancho = (a, b) => (Math.max(0.3, (b - a) / tot * 100)).toFixed(2) + '%';
        const ms = marcasDe(d);
        let out = '<div class="rmx-ax"></div>';
        const h = horarioDe(d);
        if (h) out += '<div class="rmx-hor" style="left:' + pos(h.a) + ';width:' + ancho(h.a, h.b) + '"></div>';
        for (let i = 0; i < ms.length - 1; i++) {
            const a = ms[i], b = ms[i + 1];
            out += '<div class="' + (a.t === 'S' && b.t === 'E' ? 'rmx-pau' : 'rmx-seg') + '" style="left:' + pos(a.min) + ';width:' + ancho(a.min, b.min) + '"></div>';
        }
        const enPausa = {};
        for (let i = 1; i < ms.length - 2; i++) {
            if (ms[i].t === 'S' && ms[i + 1].t === 'E') {
                enPausa[i] = enPausa[i + 1] = true;
                const mid = (ms[i].min + ms[i + 1].min) / 2;
                out += '<div class="rmx-ptag" style="left:' + pos(mid) + '">Pausa ' + ms[i].fh.slice(11, 16) + ' → ' + ms[i + 1].fh.slice(11, 16) + ' · ' + durMin(ms[i + 1].min - ms[i].min) + '</div>';
                i++;
            }
        }
        ms.forEach((m, i) => {
            const extremo = (i === 0 || i === ms.length - 1);
            out += '<div class="rmx-dot ' + (m.t === 'E' ? 'rmx-dot-in' : 'rmx-dot-out') + (extremo ? '' : ' rmx-dot-s') + '" style="left:' + pos(m.min) + '"></div>';
            if (extremo) out += '<div class="rmx-tag ' + (m.t === 'E' ? 'rmx-tag-in' : 'rmx-tag-out') + '" style="left:' + pos(m.min) + '"><b>' + m.fh.slice(11, 16) + '</b>' + (PALABRA[m.t] || '') + '</div>';
            else if (!enPausa[i]) out += '<div class="rmx-mtag" style="left:' + pos(m.min) + '">' + m.fh.slice(11, 16) + ' ' + (PALABRA[m.t] || '') + '</div>';
        });
        for (let t = eje.lo; t <= eje.hi; t += 120) {
            out += '<div class="rmx-tick" style="left:' + pos(t) + '">' + String(Math.floor(((t % 1440) + 1440) % 1440 / 60)).padStart(2, '0') + '</div>';
        }
        return '<div class="rmx-tl">' + out + '</div>';
    }
    function resultadoDia(d) {
        const ms = marcasDe(d);
        const estuvo = ms.length > 1 ? (ms[ms.length - 1].min - ms[0].min) / 60 : 0;
        let html = '<b>' + num(d.horas, 2) + ' h</b>';
        html += '<div>Estuvo ' + num(estuvo, 2) + ' h · ' + (Number(d.minutos_colacion) > 0 ? 'colación descontada ' + durMin(d.minutos_colacion) : 'sin colación descontada') + '</div>';
        const avisos = [];
        if (Number(d.minutos_atraso) >= 1) avisos.push('<span style="color:#b91c1c;font-weight:600">Atraso ' + durMin(d.minutos_atraso) + '</span>');
        if (Number(d.minutos_salida_adelantada) >= 1) avisos.push('<span style="color:#b91c1c;font-weight:600">Salida adelantada ' + durMin(d.minutos_salida_adelantada) + '</span>');
        if (Number(d.minutos_exceso_colacion) >= 1) avisos.push('<span style="color:#92400e;font-weight:600">Exceso de colación ' + durMin(d.minutos_exceso_colacion) + '</span>');
        if (Number(d.minutos_extra_bruto) >= 1) avisos.push('<span style="color:#1d4ed8;font-weight:600">' + durMin(d.minutos_extra_bruto) + ' extra</span>');
        if (ESTADO_TXT[d.estado]) avisos.push('<span style="color:#6b21a8;font-weight:600">' + ESTADO_TXT[d.estado] + '</span>');
        html += avisos.length ? '<div>' + avisos.join(' · ') + '</div>' : '<div style="color:#15803d;font-weight:600">Sin atraso ni salida adelantada</div>';
        return html;
    }
    function diaSemana(f) {
        try { return new Date(String(f).slice(0, 10) + 'T12:00:00').toLocaleDateString('es-CL', { weekday: 'long', day: '2-digit', month: '2-digit' }); }
        catch (e) { return String(f); }
    }

    function seccionDias(r) {
        const ej = ejemplos[r.id];
        let cuerpo;
        if (!ej || ej.cargando) cuerpo = '<div class="text-muted py-3"><div class="spinner-border spinner-border-sm"></div> Buscando días reales…</div>';
        else if (ej.error) cuerpo = '<div class="alert alert-warning py-2 mb-0">No se pudieron traer los días: ' + esc(ej.error) + '</div>';
        else if (!ej.dias.length) cuerpo = '<div class="rmx-na">No hay días terminados con estas marcas en el tramo abierto (sin marcas manuales y sin cierres). La regla se puede configurar igual: queda lista para cuando aparezca uno.</div>';
        else {
            const eje = ejeDe(ej.dias);
            cuerpo = ej.dias.map(d => {
                const h = horarioDe(d);
                return '<div class="rmx-dia"><div><div class="fw-bold">' + esc(d.persona) + '</div>'
                    + '<div class="text-muted" style="font-size:.78rem;">' + esc(d.horario || '') + ' · ' + esc(diaSemana(d.fecha)) + '</div>'
                    + '<div style="font-size:.78rem;' + (h ? 'color:#475569' : 'color:#6b21a8;font-weight:600') + '">' + (h ? 'Horario del día ' + esc(String(d.hora_entrada_teorica).slice(0, 5)) + ' – ' + esc(String(d.hora_salida_teorica).slice(0, 5)) : 'Día libre o feriado') + '</div></div>'
                    + (eje ? lineaTiempo(d, eje) : '<div></div>')
                    + '<div class="rmx-res">' + resultadoDia(d) + '</div></div>';
            }).join('');
        }
        const total = ej && ej.total ? ej.total : 0;
        return '<section class="rmx-card p-3">'
            + '<div class="d-flex justify-content-between align-items-baseline flex-wrap gap-2 mb-1"><h5 class="mb-0" style="font-size:1rem;font-weight:700;">Así se ven estos días</h5>'
            + '<span class="text-muted" style="font-size:.78rem;">' + (total ? 'Los ' + Math.min(total, (ej.dias || []).length) + ' más recientes de ' + total + ' en el tramo abierto · ' : '') + 'la franja punteada es el horario asignado de ese día</span></div>'
            + cuerpo + '</section>';
    }

    // ── Los pasos ────────────────────────────────────────────────────────────
    function opcion(nombre, valor, marcado, titulo, texto, extra, opts) {
        const o = opts || {};
        const cls = 'rmx-op' + (marcado ? ' rmx-op-sel' : '') + (o.apagada ? ' rmx-op-off' : '');
        return '<label class="' + cls + '">'
            + (o.badge ? '<span class="rmx-badge ' + o.badge[0] + '">' + o.badge[1] + '</span>' : '')
            + '<span class="rmx-op-t"><input type="' + (o.check ? 'checkbox' : 'radio') + '" name="' + nombre + '" value="' + valor + '"' + (marcado ? ' checked' : '') + (o.disabled ? ' disabled' : '') + '>' + titulo + '</span>'
            + (texto ? '<span>' + texto + '</span>' : '') + (extra || '') + '</label>';
    }
    function paso(n, titulo, explicacion, cuerpo, ultimo) {
        return '<div class="rmx-paso"><div class="d-flex flex-column align-items-start"><div class="rmx-num">' + n + '</div>' + (ultimo ? '' : '<div class="rmx-rail"></div>') + '</div>'
            + '<div class="rmx-card p-3 mb-3 d-flex flex-column gap-3"><div><h5 class="mb-1" style="font-size:1rem;font-weight:700;">' + titulo + '</h5>'
            + (explicacion ? '<div class="text-muted" style="font-size:.84rem;">' + explicacion + '</div>' : '') + '</div>' + cuerpo + '</div></div>';
    }

    function tablaHorarios() {
        const hs = data.horarios || [];
        if (!hs.length) return '';
        return '<table class="rmx-tab"><thead><tr><th>Horario</th><th>Colación</th><th>Mínimo para descontar</th><th>Tolerancia de exceso</th><th>Margen ENTRADA / SALIDA</th></tr></thead><tbody>'
            + hs.map(h => {
                const sinCol = !h.descuento_colacion_auto || !(Number(h.minutos_colacion_auto) > 0);
                const umbral = Number(h.umbral_horas_colacion) || 0;
                return '<tr><td>' + esc(h.nombre) + '</td><td>' + (sinCol ? 'sin colación' : durMin(h.minutos_colacion_auto)) + '</td>'
                    + '<td' + (sinCol || umbral > 0 ? '' : ' style="color:#b45309;font-weight:600"') + '>' + (sinCol ? '—' : (umbral > 0 ? num(umbral, umbral % 1 ? 1 : 0) + ' h' : '0 h: descuenta siempre')) + '</td>'
                    + '<td>' + (Number(h.tolerancia_exceso_colacion_minutos) || 0) + ' min</td>'
                    + '<td>' + (Number(h.anclaje_entrada_minutos) || 0) + ' / ' + (Number(h.anclaje_salida_minutos) || 0) + ' min</td></tr>';
            }).join('') + '</tbody></table>';
    }

    function renderEditor() {
        const el = $('rm-editor');
        const r = data.reglas.find(x => x.id === selId);
        if (!el || !r) return;
        const scrollY = window.scrollY;
        cargarEjemplos(r);
        const puede = canEdit();
        const edit = puede && !r.activa;
        const s = String(r.secuencia), n = s.length;
        const calcula = r.lectura !== 'NINGUNA';
        const equivalente = alterna(s);
        const medible = hayPausaMedible(s);
        const dis = edit ? {} : { disabled: true };

        const cabecera = '<header class="rmx-card p-3 d-flex flex-column gap-3">'
            + '<div class="d-flex justify-content-between align-items-start flex-wrap gap-2"><div class="d-flex flex-column gap-2">'
            + '<div class="rmx-kicker">DÍAS CON ' + n + ' ' + (n === 1 ? 'MARCA' : 'MARCAS') + ' · ' + esc((r.grupo || '').toUpperCase()) + '</div>'
            + '<div class="d-flex align-items-center flex-wrap" style="gap:6px 0;">' + chipsSecuencia(s, true) + '</div></div>'
            + '<span class="rmx-pill ' + (r.activa ? 'rmx-on' : 'rmx-off') + '">' + (r.activa ? 'Encendida · el cálculo la usa' : 'Apagada · el cálculo no la usa') + '</span></div>'
            + '<div class="rmx-stats"><div class="rmx-stat"><b>' + Number(r.dias_abiertos).toLocaleString('es-CL') + '</b><span>días así en el tramo abierto</span></div>'
            + '<div class="rmx-stat"><b>' + Number(r.dias).toLocaleString('es-CL') + '</b><span>días así en todo el historial</span></div>'
            + '<div class="rmx-stat"><b>' + (data.horarios || []).length + '</b><span>horarios de Ciclo Inteligente · Bolsa Flexible no usa reglas</span></div></div></header>';

        const intro = '<section class="rmx-intro">'
            + '<div class="rmx-card p-3 d-flex gap-2" style="font-size:.86rem;line-height:1.5;"><i class="bi bi-info-circle text-secondary" aria-hidden="true" style="font-size:1.2rem;"></i><div><strong>¿Qué es una regla?</strong> Cada día el reloj deja marcas. Cuando un día trae sus marcas en este orden, la regla dice cómo calcularlo. Nunca cambia ni inventa marcas: decide cómo se leen, qué colación se descuenta y si alguien tiene que mirarlo.</div></div>'
            + '<div class="rmx-ve p-3 d-flex gap-2" style="font-size:.86rem;line-height:1.5;"><i class="bi bi-search" aria-hidden="true" style="font-size:1.1rem;"></i><div><strong>Lo que ve el sistema.</strong> ' + esc(diagnostico(s)) + '</div></div>'
            + '</section>';

        // Paso 1: ¿calcula solo?
        const p1 = paso(1, '¿El sistema puede calcular estos días solo?',
            'Si las marcas alcanzan para saber cuándo entró y cuándo salió, calcula solo. Si falta algo, una persona lo completa.',
            '<div class="rmx-ops rmx-c2">'
            + opcion('rmx-p1', 'SI', calcula, 'Sí, que calcule solo',
                n === 1 ? 'Con una sola marca no se puede calcular.' : 'Lee las marcas con el paso 2 y descuenta la colación del paso 3.', '',
                Object.assign({ apagada: n === 1, disabled: n === 1 || !edit }, equivalente ? { badge: ['rmx-b-sug', 'Sugerido'] } : {}))
            + opcion('rmx-p1', 'NO', !calcula, 'No, que una persona lo complete',
                'El día queda «por revisar», sin horas, y bloquea el cierre del área hasta que alguien lo resuelva.', '',
                Object.assign({ disabled: !edit }, n === 1 ? { badge: ['rmx-b-sug', 'Única posible'] } : {}))
            + '</div>');

        // Paso 2: lectura
        let cuerpo2;
        if (!calcula) cuerpo2 = '<div class="rmx-na">No aplica: el día no se calcula hasta que una persona lo complete.</div>';
        else cuerpo2 = '<div class="rmx-ops rmx-c2">'
            + opcion('rmx-p2', 'RELOJ', r.lectura === 'RELOJ', 'Como las marcó el reloj', esc(papeles(s, 'RELOJ')),
                equivalente && r.lectura !== 'RELOJ' ? '<span class="rmx-ef">En esta secuencia da lo mismo que la otra lectura.</span>' : '', dis)
            + opcion('rmx-p2', 'EXTREMOS', r.lectura === 'EXTREMOS', 'La primera es la ENTRADA y la última la SALIDA', esc(papeles(s, 'EXTREMOS')),
                equivalente && r.lectura !== 'EXTREMOS' ? '<span class="rmx-ef">En esta secuencia da lo mismo que la otra lectura.</span>' : '', dis)
            + '</div>';
        const p2 = paso(2, '¿Cómo se leen las marcas?',
            'Se comparan con el horario asignado de ese día y sus márgenes de ENTRADA y SALIDA. <span class="rmx-src">Configuración → Horarios</span>', cuerpo2);

        // Paso 3: colación
        let cuerpo3;
        if (!calcula) cuerpo3 = '<div class="rmx-na">No aplica: sin cálculo no hay colación que descontar.</div>';
        else cuerpo3 = '<div class="rmx-ops rmx-c3">'
            + opcion('rmx-p3', 'TURNO', r.colacion === 'TURNO', 'La del horario asignado', 'Descuenta la colación automática del horario.', '', dis)
            + opcion('rmx-p3', 'MEDIDA', r.colacion === 'MEDIDA', 'Lo mayor entre la del horario y la pausa medida',
                medible ? 'Mide la pausa marcada y descuenta lo que sea mayor.' : 'No hay pausa marcada en esta secuencia: termina usando la del horario.', '',
                Object.assign({}, dis, medible ? {} : { apagada: r.colacion !== 'MEDIDA' }))
            + opcion('rmx-p3', 'NINGUNA', r.colacion === 'NINGUNA', 'Ninguna', 'No descuenta colación. Solo para horarios sin colación.', '', dis)
            + '</div>'
            + '<div class="rmx-nota"><i class="bi bi-check2-circle" aria-hidden="true" style="color:#1d4ed8;font-size:1.1rem;"></i><span><strong>Mínimo de horas:</strong> si la persona estuvo menos que el mínimo de su horario (de la primera ENTRADA a la última SALIDA), no se le exige la colación del horario; si marcó una pausa, se descuenta solo esa pausa.</span></div>'
            + '<div class="rmx-nota"><i class="bi bi-check2-circle" aria-hidden="true" style="color:#1d4ed8;font-size:1.1rem;"></i><span><strong>Día libre o feriado (jornada especial):</strong> la colación se descuenta igual que en un día de trabajo, si estuvo al menos el mínimo.</span></div>'
            + '<div><div class="text-muted mb-1" style="font-size:.78rem;">Lo que tiene cada horario hoy <span class="rmx-src">Configuración → Horarios → Colación, Umbral y Tolerancia de exceso</span></div>' + tablaHorarios() + '</div>';
        const p3 = paso(3, '¿Qué colación se descuenta?', 'Los minutos no viven en la regla: se leen del horario asignado de cada persona.', cuerpo3);

        // Paso 4: aviso
        const umbralCiclo = (data.ajustes || {}).reglas_marcas_fuera_ciclo_minutos;
        const opcionesHtml = (r.accion !== 'CALCULA')
            ? '<div><div class="text-muted mb-1" style="font-size:.78rem;">Al revisar, la persona podrá (el sistema nunca inventa una marca):</div><div class="rmx-ops rmx-c2">'
              + OPCIONES.map(o => opcion('rmx-op-' + o[0], o[0], (r.opciones_revision || []).includes(o[0]), o[1], '', '', Object.assign({ check: true }, dis))).join('') + '</div></div>'
            : '';
        const cuerpo4 = '<div class="rmx-ops rmx-c3">'
            + opcion('rmx-p4', 'CALCULA', r.accion === 'CALCULA', 'No avisar', 'El resultado se ve en la grilla.', '', Object.assign({}, dis, calcula ? {} : { disabled: true, apagada: true }))
            + opcion('rmx-p4', 'CALCULA_Y_REVISA', r.accion === 'CALCULA_Y_REVISA', 'Avisar, pero calcular igual', 'Queda en «Días por revisar» con sus horas.', '', Object.assign({}, dis, calcula ? {} : { disabled: true, apagada: true }))
            + opcion('rmx-p4', 'SOLO_REVISA', r.accion === 'SOLO_REVISA', 'Revisar antes de calcular', 'Queda sin horas hasta que alguien lo vea.', '', dis)
            + '</div>' + opcionesHtml
            + (calcula
                ? opcion('rmx-ciclo', '1', !!r.avisa_fuera_de_ciclo, 'Además, avisar si las marcas no calzan con ningún ciclo del horario',
                    'Compara la ENTRADA con la de cada ciclo del día (mañana, tarde o noche). Si la más cercana queda a más de '
                    + (umbralCiclo == null ? '[sin configurar]' : durMin(umbralCiclo)) + ', el día va a revisión y se calcula igual. Los días libres y feriados no tienen ciclo y no avisan.',
                    umbralCiclo == null ? '<span class="rmx-ef">Configure los minutos en «Ajustes de las reglas», arriba: sin ese valor no avisa.</span>' : '',
                    Object.assign({ check: true, badge: ['rmx-b-new', 'Opción nueva'] }, dis))
                : '');
        const p4 = paso(4, '¿Alguien tiene que mirarlo?', '«Avisar» deja el día en «Días por revisar» con un triángulo en la grilla y bloquea el cierre del área hasta que alguien lo vea.', cuerpo4);

        // Paso 5: ensayo
        const en = ensayos[r.id];
        const claveAct = claveEnsayo(r);
        let ensayoHtml;
        if (en && en.estado === 'corriendo') ensayoHtml = '<div class="text-muted py-2"><div class="spinner-border spinner-border-sm"></div> Calculando los días de ejemplo con lo que está arriba… (nada se guarda)</div>';
        else if (en && en.estado === 'listo' && en.clave === claveAct) {
            const dias = (en.res && en.res.dias) || [];
            ensayoHtml = dias.length
                ? '<table class="rmx-tab" style="font-size:.84rem;"><thead><tr><th>Persona · día</th><th>Hoy</th><th>Con lo configurado arriba</th></tr></thead><tbody>'
                  + dias.map(d => {
                      const c = d.cambios || {};
                      const hoy = num(d.antes && d.antes.horas_trabajadas, 2) + ' h' + (d.antes && d.antes.estado ? ' · ' + esc(estadoTxt(d.antes.estado)) : '');
                      let celda;
                      if (!Object.keys(c).length) celda = '<span class="rmx-igual">Queda igual</span>';
                      else if (d.solo_aviso) celda = '<span class="rmx-cambia">Mismas horas, cambia la anotación</span>';
                      else celda = '<span class="rmx-cambia">' + Object.keys(c).filter(k => k !== 'observaciones').map(k => esc(CAMPOS_TXT[k] || k) + ': ' + esc(c[k].antes == null ? '—' : c[k].antes) + ' → ' + esc(c[k].despues == null ? '—' : c[k].despues)).join(' · ') + '</span>';
                      return '<tr><td>' + esc(d.persona) + ' · ' + esc(String(d.fecha).slice(0, 10)) + '</td><td>' + hoy + '</td><td>' + celda + '</td></tr>';
                  }).join('') + '</tbody></table>'
                : '<div class="rmx-na">No hay días con esta secuencia en el tramo abierto: no hay nada que ensayar.</div>';
        } else if (en && en.estado === 'error') ensayoHtml = '<div class="alert alert-warning py-2 mb-2">El ensayo no se pudo hacer: ' + esc(en.error || '') + '</div><button type="button" class="btn btn-sm btn-outline-success" id="rm-ensayar">Reintentar el ensayo</button>';
        else ensayoHtml = (en && en.clave !== claveAct ? '<div class="text-muted mb-1" style="font-size:.78rem;">La configuración cambió desde el último ensayo.</div>' : '')
            + '<button type="button" class="btn btn-sm btn-outline-success align-self-start" id="rm-ensayar">Ensayar con los días reales (no guarda nada)</button>';
        const p5 = paso(5, 'Así quedan los días reales', 'Ensayo: calcula los días de arriba con lo configurado, sin guardar nada.', ensayoHtml, true);

        const barra = '<div class="rmx-barra"><p><b>En una frase:</b> ' + esc(fraseRegla(r)) + '</p><div class="d-flex gap-2 flex-wrap">'
            + '<button type="button" class="rmx-btn rmx-btn-sec" id="rm-ver-dias">Ver los días</button>'
            + (edit ? '<button type="button" class="rmx-btn rmx-btn-pri" id="rm-guardar"' + (_hayCambios(r) ? '' : ' disabled') + '>' + (_hayCambios(r) ? '1. Guardar cambios' : 'Guardado') + '</button>' : '')
            + (puede && data.motor_conectado
                ? (r.activa ? '<button type="button" class="rmx-btn rmx-btn-no" id="rm-correr" data-encender="0">Apagar esta regla</button>'
                            : '<button type="button" class="rmx-btn rmx-btn-ok" id="rm-correr" data-encender="1">' + (edit ? '2. ' : '') + 'Correr esta regla</button>')
                : '')
            + '</div></div>'
            + (r.activa && puede ? '<div class="text-muted mt-1" style="font-size:.78rem;">Para cambiarla, primero apáguela: así el cambio corre con su propio antes y después.</div>' : '');

        el.innerHTML = '<div class="d-flex flex-column gap-3">' + cabecera + intro + seccionDias(r) + '<section>' + p1 + p2 + p3 + p4 + p5 + '</section>' + barra + '</div>';
        window.scrollTo(0, scrollY);

        // ── Cambios en pantalla (quedan en memoria hasta «Guardar») ──
        const cambiar = (fn) => (ev) => { if (!edit) return; fn(ev.target); renderEditor(); };
        const faltaPorDefecto = () => (n % 2 === 1 && s[n - 1] === 'E') ? 'AGREGAR_SALIDA' : ((n % 2 === 1 && s[0] === 'S') || n === 1 && s === 'S' ? 'AGREGAR_ENTRADA' : 'RECLASIFICAR');
        el.querySelectorAll('input[name="rmx-p1"]').forEach(i => i.addEventListener('change', cambiar(t => {
            if (t.value === 'NO') {
                r._lecturaPrev = r.lectura; r.lectura = 'NINGUNA'; r.accion = 'SOLO_REVISA';
                if (!(r.opciones_revision || []).length) r.opciones_revision = [faltaPorDefecto()];
            } else {
                r.lectura = (r._lecturaPrev && r._lecturaPrev !== 'NINGUNA') ? r._lecturaPrev : (equivalente ? 'RELOJ' : 'EXTREMOS');
                if (r.accion === 'SOLO_REVISA') { r.accion = 'CALCULA'; r.opciones_revision = []; }
            }
        })));
        el.querySelectorAll('input[name="rmx-p2"]').forEach(i => i.addEventListener('change', cambiar(t => { r.lectura = t.value; })));
        el.querySelectorAll('input[name="rmx-p3"]').forEach(i => i.addEventListener('change', cambiar(t => { r.colacion = t.value; })));
        el.querySelectorAll('input[name="rmx-p4"]').forEach(i => i.addEventListener('change', cambiar(t => {
            r.accion = t.value;
            if (r.accion === 'CALCULA') r.opciones_revision = [];
            else if (!(r.opciones_revision || []).length) r.opciones_revision = [r.accion === 'SOLO_REVISA' ? faltaPorDefecto() : 'CONFIRMAR'];
            if (r.accion === 'SOLO_REVISA' && r.lectura !== 'NINGUNA' && n === 1) r.lectura = 'NINGUNA';
        })));
        OPCIONES.forEach(o => el.querySelectorAll('input[name="rmx-op-' + o[0] + '"]').forEach(i => i.addEventListener('change', cambiar(t => {
            const lista = (r.opciones_revision = r.opciones_revision || []);
            const k = lista.indexOf(o[0]);
            if (t.checked && k < 0) lista.push(o[0]);
            if (!t.checked && k >= 0) lista.splice(k, 1);
        }))));
        el.querySelectorAll('input[name="rmx-ciclo"]').forEach(i => i.addEventListener('change', cambiar(t => { r.avisa_fuera_de_ciclo = t.checked ? 1 : 0; })));
        const ens = $('rm-ensayar'); if (ens) ens.addEventListener('click', () => ensayar(r));
        const vd = $('rm-ver-dias'); if (vd) vd.addEventListener('click', () => verDias(r));
        const g = $('rm-guardar'); if (g) g.addEventListener('click', () => guardar(r));
        const c = $('rm-correr'); if (c) c.addEventListener('click', () => correrRegla(r, c.dataset.encender === '1'));
    }

    // ── Días por revisar ─────────────────────────────────────────────────────
    async function cargarPorRevisar() {
        const el = $('rm-por-revisar');
        if (!el) return;
        try {
            const res = await fetch(API + 'por-revisar/', { headers: headers() });
            if (!res.ok) { el.innerHTML = ''; return; }
            const body = await res.json();
            if (!body.total) {
                el.innerHTML = '<div class="alert alert-success py-2 mb-0" style="font-size:.86rem;"><i class="bi bi-check-circle"></i> No hay días por revisar en el tramo abierto.</div>';
                return;
            }
            el.innerHTML = '<div class="rmx-card"><div class="p-3">'
                + '<div class="fw-semibold text-danger mb-1"><i class="bi bi-exclamation-triangle-fill"></i> Días por revisar (' + body.total + ')</div>'
                + '<div class="text-muted mb-2" style="font-size:.82rem;">Una regla dejó estos días en revisión. «Abrir» muestra sus marcas para corregirlas. Mientras queden días aquí, el cierre del tramo de su área está bloqueado.</div>'
                + '<div class="table-responsive" style="max-height:260px;"><table class="table table-sm align-middle mb-0" style="font-size:.82rem;">'
                + '<thead><tr><th>Persona</th><th>Área</th><th>Fecha</th><th>Marcas</th><th>Estado</th><th class="text-end">Horas</th><th></th></tr></thead><tbody>'
                + body.dias.map(d => '<tr><td>' + esc(d.persona) + '</td><td>' + esc(d.area || '') + '</td><td>' + esc(d.fecha) + '</td>'
                    + '<td><span class="rmx-fila">' + chipsSecuencia(d.secuencia || '', false) + '</span></td><td>' + esc(estadoTxt(d.estado)) + '</td>'
                    + '<td class="text-end">' + num(d.horas, 2) + '</td>'
                    + '<td class="text-end"><button type="button" class="btn btn-sm btn-outline-primary py-0" data-rm-abrir="' + d.empleado_id + '|' + esc(d.fecha) + '|' + esc(d.persona) + '">Abrir</button></td></tr>').join('')
                + '</tbody></table></div></div></div>';
            el.querySelectorAll('[data-rm-abrir]').forEach(b => b.addEventListener('click', () => {
                const p = b.dataset.rmAbrir.split('|');
                abrirDiaRevision(parseInt(p[0], 10), p[1], p[2]);
            }));
        } catch (e) {
            el.innerHTML = '';
        }
    }

    // El cuadro de corrección vive en la página de Marcaciones: primero se va allá,
    // se espera a que la grilla cargue y recién entonces se abre el día.
    function abrirDiaRevision(eid, fecha, nombre) {
        if (typeof switchPage === 'function') switchPage('marcaciones');
        let intentos = 0;
        const t = setInterval(() => {
            intentos++;
            const listo = typeof openManualEntryModal === 'function'
                && typeof stateMarcacionesApp !== 'undefined' && stateMarcacionesApp.data && stateMarcacionesApp.data.matrix;
            if (listo) { clearInterval(t); openManualEntryModal(eid, fecha, nombre); }
            else if (intentos > 40) { clearInterval(t); toast('La grilla no terminó de cargar: busque el día en Marcaciones (la celda lleva un triángulo rojo).', 'warning'); }
        }, 350);
    }

    async function crearRegla(secuencia) {
        try {
            const res = await fetch(API, { method: 'POST', headers: headers(), body: JSON.stringify({ secuencia: secuencia }) });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) { toast(body.detail || 'No se pudo crear la regla.', 'danger'); return; }
            toast(body.message || 'Regla creada.');
            if (body.regla && body.regla.id) selId = body.regla.id;
            init();
        } catch (e) {
            toast('No se pudo crear la regla: sin conexión.', 'danger');
        }
    }

    async function correrRegla(r, encender) {
        if (encender && _hayCambios(r)) {
            toast('La regla ' + palabras(r.secuencia) + ' tiene cambios sin guardar: apriete «Guardar» antes de correrla.', 'warning');
            return;
        }
        const verbo = encender ? 'Correr' : 'Apagar';
        const nAb = Number(r.dias_abiertos);
        const detalle = encender
            ? 'Se encenderá la regla y se recalcularán solo los días del tramo abierto con las marcas ' + palabras(r.secuencia) + ' (' + nAb.toLocaleString('es-CL') + (nAb === 1 ? ' día' : ' días') + ' con marcas del reloj, más los que tengan marcas manuales). Nunca el día en curso ni períodos cerrados.'
            : 'Se apagará la regla y esos mismos días del tramo abierto se recalcularán de vuelta con la lógica de siempre.';
        const ok = await Swal.fire({
            title: verbo + ' la regla',
            html: '<div style="font-size:.95rem;text-align:left;">' + esc(detalle) + '<br><br>Al terminar verá el antes y el después de cada día que cambió.</div>',
            icon: 'question', showCancelButton: true, confirmButtonText: verbo + ' ahora', cancelButtonText: 'Cancelar',
        });
        if (!ok.isConfirmed) return;
        try {
            const res = await fetch(API + r.id + '/' + (encender ? 'correr' : 'apagar') + '/', { method: 'POST', headers: headers() });
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
            aviso.innerHTML = '<div class="alert alert-warning py-2 mb-2" style="font-size:.86rem;"><div class="spinner-border spinner-border-sm me-1" role="status"></div>'
                + (j.encender ? 'Corriendo' : 'Apagando') + ' la regla ' + esc(palabras(j.secuencia)) + (j.total ? ' · ' + j.avance + ' de ' + j.total + ' días' : '') + '… No cierre esta pantalla.</div>';
        };
        const tick = async () => {
            try {
                const res = await fetch(API + 'corridas/' + jobId + '/', { headers: headers() });
                const j = await res.json();
                if (!res.ok) throw new Error(j.detail || ('HTTP ' + res.status));
                if (j.estado === 'en_curso') { pinta(j); setTimeout(tick, 2000); return; }
                if (aviso) aviso.innerHTML = '';
                if (j.estado === 'fallo') abrirModal('La corrida no terminó bien', '<div class="alert alert-danger">' + esc(j.error || 'Error desconocido') + '</div>');
                else mostrarResultado(j);
                selId = j.regla_id; init();
            } catch (e) {
                if (aviso) aviso.innerHTML = '<div class="alert alert-danger py-2 mb-2" style="font-size:.86rem;">No se pudo seguir la corrida: ' + esc(e.message) + '. Recargue la pestaña.</div>';
            }
        };
        tick();
    }

    function mostrarResultado(j) {
        const r = j.resultado || {};
        const filas = (r.detalle || []).map(d => {
            const cambios = Object.entries(d.cambios || {}).filter(e => e[0] !== 'observaciones')
                .map(e => esc(CAMPOS_TXT[e[0]] || e[0]) + ': ' + esc(String(e[1].antes == null ? '—' : e[1].antes)) + ' → ' + esc(String(e[1].despues == null ? '—' : e[1].despues))).join('<br>');
            return '<tr><td>' + esc(d.persona) + '</td><td>' + esc(d.fecha) + '</td><td>' + (d.solo_aviso ? '<span class="rmx-igual">Mismas horas, cambia la anotación</span>' : (cambios || '—')) + '</td></tr>';
        }).join('');
        const cuerpo = '<div class="mb-2" style="font-size:.9rem;">Regla ' + esc(palabras(j.secuencia)) + ' ' + (j.encender ? 'encendida' : 'apagada') + '. '
            + 'Días revisados: <strong>' + (r.dias_revisados || 0) + '</strong> · cambiaron: <strong>' + (r.dias_cambiados || 0) + '</strong> ('
            + (r.dias_con_horas_distintas || 0) + ' con horas o estado distinto, ' + (r.dias_solo_aviso || 0) + ' solo con una anotación nueva).</div>'
            + (filas ? '<div class="table-responsive"><table class="table table-sm align-middle" style="font-size:.84rem;"><thead><tr><th>Persona</th><th>Fecha</th><th>Qué cambió (antes → después)</th></tr></thead><tbody>' + filas + '</tbody></table></div>'
                     : '<div class="text-muted">Ningún día cambió.</div>');
        abrirModal('Resultado: ' + (j.encender ? 'correr' : 'apagar') + ' la regla', cuerpo);
    }

    async function guardar(r) {
        try {
            const res = await fetch(API + r.id + '/', {
                method: 'PUT', headers: headers(),
                body: JSON.stringify({ lectura: r.lectura, colacion: r.colacion, accion: r.accion, opciones_revision: r.opciones_revision || [],
                                       avisa_fuera_de_ciclo: r.avisa_fuera_de_ciclo ? 1 : 0, nota: r.nota || '' })
            });
            const body = await res.json().catch(() => ({}));
            if (!res.ok) { toast(body.detail || 'No se pudo guardar la regla.', 'danger'); return; }
            Object.assign(r, body.regla, { dias: r.dias, dias_abiertos: r.dias_abiertos, grupo: r.grupo });
            r.avisa_fuera_de_ciclo = r.avisa_fuera_de_ciclo ? 1 : 0;
            r._guardada = _fotoRegla(r);
            toast('Regla ' + palabras(r.secuencia) + ' guardada.');
            renderLista(); renderEditor();
        } catch (e) {
            toast('No se pudo guardar la regla: sin conexión.', 'danger');
        }
    }

    const marcasChips = (marcas) => String(marcas || '').split(' · ').filter(Boolean).map(m => {
        const esEnt = m.indexOf('Ent') >= 0;
        return '<span class="rmx-chip ' + (esEnt ? 'rmx-chip-in' : 'rmx-chip-out') + '" style="margin:1px 2px 1px 0;">' + (esEnt ? 'ENTRADA' : 'SALIDA') + ' ' + esc(m.slice(0, 5)) + '</span>';
    }).join('');

    async function verDias(r) {
        abrirModal('Días del tramo abierto con las marcas ' + palabras(r.secuencia), '<div class="text-center py-3 text-muted"><div class="spinner-border spinner-border-sm"></div> Buscando…</div>');
        let cuerpo;
        try {
            const res = await fetch(API + r.id + '/dias/', { headers: headers() });
            const body = await res.json();
            if (!res.ok) throw new Error(body.detail || ('HTTP ' + res.status));
            cuerpo = body.dias.length
                ? '<div class="text-muted mb-2" style="font-size:.82rem;">Desde el ' + esc(body.desde) + ' · ' + body.dias.length + (body.dias.length === 1 ? ' día' : ' días') + ' · solo lectura (marcas del reloj, sin manuales)</div>'
                  + '<div class="table-responsive"><table class="table table-sm align-middle" style="font-size:.84rem;"><thead><tr><th>Persona</th><th>Fecha</th><th>Marcas</th><th>Estado</th><th class="text-end">Horas</th><th class="text-end">Faltó (min)</th></tr></thead><tbody>'
                  + body.dias.map(d => '<tr><td>' + esc(d.persona) + '</td><td>' + esc(d.fecha) + '</td><td>' + marcasChips(d.marcas) + '</td><td>' + esc(estadoTxt(d.estado)) + '</td><td class="text-end">' + num(d.horas, 2) + '</td><td class="text-end">' + Number(d.deuda || 0).toLocaleString('es-CL') + '</td></tr>').join('')
                  + '</tbody></table></div>'
                : '<div class="text-muted py-3">No hay días con estas marcas en el tramo abierto.</div>';
        } catch (e) {
            cuerpo = '<div class="alert alert-danger">' + esc(e.message) + '</div>';
        }
        const mb = $('rm-modal-body');
        if (mb) mb.innerHTML = cuerpo;
    }

    function abrirModal(titulo, cuerpo) {
        let m = $('rm-modal');
        if (!m) {
            m = document.createElement('div');
            m.id = 'rm-modal';
            m.className = 'modal fade';
            m.tabIndex = -1;
            m.innerHTML = '<div class="modal-dialog modal-lg modal-dialog-scrollable"><div class="modal-content">'
                + '<div class="modal-header"><h5 class="modal-title" id="rm-modal-title"></h5>'
                + '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div>'
                + '<div class="modal-body" id="rm-modal-body"></div></div></div>';
            document.body.appendChild(m);
        }
        $('rm-modal-title').textContent = titulo;
        $('rm-modal-body').innerHTML = cuerpo;
        bootstrap.Modal.getOrCreateInstance(m).show();
    }

    return { init };
})();

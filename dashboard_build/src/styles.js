// Estilos del Dashboard Analítico (prefijo dx-). Se inyectan una sola vez desde DashboardApp.
// Sistema: neutros teñidos de azul, un acento de marca, color solo para estado (ok/aviso/crítico).
// Movimiento: solo transform/opacity, ease-out fuerte, <=260 ms, desactivado con prefers-reduced-motion.

export const DX_CSS = `
.dx {
  --dx-ink: #14203b;
  --dx-ink-2: #4a5878;
  --dx-ink-3: #77839d;
  --dx-line: #e2e7f0;
  --dx-line-2: #edf0f6;
  --dx-fill: #eef1f7;
  --dx-surface: #ffffff;
  --dx-brand: #1f3a9e;
  --dx-brand-soft: #e8edfb;
  --dx-ok: #157a3f;
  --dx-ok-soft: #e1f4e8;
  --dx-warn: #9a5400;
  --dx-warn-soft: #fcefd9;
  --dx-bad: #b8222d;
  --dx-bad-soft: #fde7e9;
  --dx-info: #1d63a8;
  --dx-info-soft: #e2eefa;
  --dx-ease: cubic-bezier(0.23, 1, 0.32, 1);
  color: var(--dx-ink);
  font-variant-numeric: tabular-nums;
  max-width: 1280px;
  margin: 0 auto;
  padding-bottom: 32px;
  -webkit-tap-highlight-color: transparent;
}
.dx *, .dx *::before, .dx *::after { box-sizing: border-box; }
.dx h1, .dx h2, .dx h3, .dx h4, .dx p { margin: 0; }
.dx button { font: inherit; color: inherit; cursor: pointer; }

/* ── Superficies ───────────────────────────────────────────── */
.dx-panel {
  background: var(--dx-surface);
  border: 1px solid var(--dx-line);
  border-radius: 14px;
  min-width: 0;
}
.dx-grid-2 > *, .dx-grid-eq > *, .dx-hero > * { min-width: 0; }
.dx-sec { margin-top: 20px; }
.dx-sec-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 0 2px 10px; }
.dx-sec-title { font-size: 15px; font-weight: 650; letter-spacing: -0.005em; }
.dx-sec-sub { font-size: 12.5px; color: var(--dx-ink-3); }

/* ── Barra superior ────────────────────────────────────────── */
.dx-bar { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px 16px; margin-bottom: 16px; }
.dx-seg { position: relative; display: inline-grid; grid-template-columns: 1fr 1fr; background: #e7ebf3; border-radius: 11px; padding: 3px; }
.dx-seg button { position: relative; z-index: 1; border: 0; background: none; padding: 9px 18px; border-radius: 8px; font-size: 14px; font-weight: 600; color: var(--dx-ink-2); transition: color 160ms var(--dx-ease), transform 120ms var(--dx-ease); white-space: nowrap; }
.dx-seg button[aria-selected="true"] { color: var(--dx-ink); }
.dx-seg button:active { transform: scale(0.97); }
.dx-seg-thumb { position: absolute; top: 3px; bottom: 3px; left: 3px; width: calc(50% - 3px); background: #fff; border-radius: 8px; box-shadow: 0 1px 2px rgba(20,32,59,.14), 0 0 0 1px rgba(20,32,59,.04); transition: transform 200ms var(--dx-ease); }
.dx-seg[data-active="periodo"] .dx-seg-thumb { transform: translateX(100%); }

.dx-filters { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px; }
.dx-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.dx-field > span { font-size: 12px; font-weight: 600; color: var(--dx-ink-3); }
.dx-input { height: 40px; min-width: 150px; padding: 0 12px; border: 1px solid var(--dx-line); border-radius: 10px; background: #fff; color: var(--dx-ink); font: inherit; font-size: 14px; transition: border-color 140ms var(--dx-ease), box-shadow 140ms var(--dx-ease); }
.dx-input:focus-visible { outline: none; border-color: var(--dx-brand); box-shadow: 0 0 0 3px rgba(31,58,158,.16); }
.dx-iconbtn { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; border: 1px solid var(--dx-line); border-radius: 10px; background: #fff; color: var(--dx-ink-2); font-size: 13px; font-weight: 600; transition: transform 120ms var(--dx-ease), border-color 140ms var(--dx-ease), color 140ms var(--dx-ease); }
.dx-iconbtn:active { transform: scale(0.97); }
.dx-iconbtn:focus-visible { outline: none; box-shadow: 0 0 0 3px rgba(31,58,158,.16); }
.dx-iconbtn i { display: inline-block; font-size: 15px; }
.dx-iconbtn i.dx-spin { animation: dx-spin 700ms linear infinite; }
.dx-stamp { font-size: 12px; color: var(--dx-ink-3); }

/* ── Vista "Hoy": indicador en vivo ────────────────────────── */
.dx-hero { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 12px; }
.dx-live { padding: 20px 22px 22px; display: flex; flex-direction: column; gap: 14px; }
.dx-live-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.dx-livetag { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 600; color: var(--dx-ink-2); }
.dx-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--dx-ok); position: relative; flex: none; }
.dx-dot::after { content: ""; position: absolute; inset: -4px; border-radius: 50%; background: var(--dx-ok); opacity: .25; animation: dx-pulse 2s var(--dx-ease) infinite; }
.dx-big { font-size: clamp(46px, 8vw, 68px); line-height: 1; font-weight: 700; letter-spacing: -0.025em; }
.dx-big small { font-size: .42em; font-weight: 600; color: var(--dx-ink-3); margin-left: 2px; letter-spacing: 0; }
.dx-live p { font-size: 13.5px; color: var(--dx-ink-2); }
.dx-live p b { color: var(--dx-ink); font-weight: 650; }
.dx-meter { height: 8px; border-radius: 99px; background: var(--dx-fill); overflow: hidden; }
.dx-meter > span { display: block; height: 100%; border-radius: inherit; background: var(--dx-brand); transform-origin: left center; transition: transform 500ms var(--dx-ease); }

.dx-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.dx-stat { padding: 18px 18px 16px; display: flex; flex-direction: column; justify-content: space-between; gap: 10px; min-width: 0; }
.dx-stat-label { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--dx-ink-2); }
.dx-stat-num { font-size: clamp(30px, 4.2vw, 40px); line-height: 1; font-weight: 700; letter-spacing: -0.02em; }
.dx-stat-hint { font-size: 12.5px; color: var(--dx-ink-3); line-height: 1.35; }
.dx-mark { width: 8px; height: 8px; border-radius: 3px; flex: none; }
.dx-mark[data-tone="warn"] { background: var(--dx-warn); }
.dx-mark[data-tone="bad"] { background: var(--dx-bad); }
.dx-mark[data-tone="info"] { background: var(--dx-info); }
.dx-mark[data-tone="ok"] { background: var(--dx-ok); }

/* ── Lista de colaboradores ────────────────────────────────── */
.dx-roster-head { padding: 16px 18px 12px; display: flex; flex-direction: column; gap: 12px; }
.dx-roster-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.dx-chips { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin: 0 -2px; padding: 2px; }
.dx-chips::-webkit-scrollbar { display: none; }
.dx-chip { flex: none; display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 12px; border: 1px solid var(--dx-line); border-radius: 99px; background: #fff; font-size: 13px; font-weight: 600; color: var(--dx-ink-2); white-space: nowrap; transition: transform 120ms var(--dx-ease), background-color 150ms var(--dx-ease), color 150ms var(--dx-ease), border-color 150ms var(--dx-ease); }
.dx-chip em { font-style: normal; font-weight: 600; color: var(--dx-ink-3); transition: color 150ms var(--dx-ease); }
.dx-chip:active { transform: scale(0.97); }
.dx-chip[aria-pressed="true"] { background: var(--dx-ink); border-color: var(--dx-ink); color: #fff; }
.dx-chip[aria-pressed="true"] em { color: rgba(255,255,255,.7); }
.dx-chip:focus-visible { outline: none; box-shadow: 0 0 0 3px rgba(31,58,158,.2); }
.dx-search { position: relative; }
.dx-search i { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--dx-ink-3); font-size: 14px; pointer-events: none; }
.dx-search .dx-input { width: 100%; padding-left: 36px; }

.dx-cols, .dx-row { display: grid; grid-template-columns: minmax(0, 2.6fr) minmax(0, 1.5fr) 84px 84px 96px 118px; align-items: center; gap: 12px; padding: 0 18px; }
.dx-cols { height: 36px; border-top: 1px solid var(--dx-line); border-bottom: 1px solid var(--dx-line-2); background: #fafbfd; font-size: 12px; font-weight: 600; color: var(--dx-ink-3); }
.dx-row { min-height: 52px; border-top: 1px solid var(--dx-line-2); font-size: 14px; transition: background-color 120ms var(--dx-ease); }
.dx-row:first-of-type { border-top: 0; }
.dx-name { font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dx-muted { color: var(--dx-ink-2); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dx-num { text-align: right; }
.dx-end { justify-self: end; }
.dx-meta { display: none; }
.dx-late { color: var(--dx-warn); font-weight: 650; }

.dx-state { display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 10px; border-radius: 99px; font-size: 12.5px; font-weight: 650; white-space: nowrap; }
.dx-state::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.dx-state[data-tone="ok"] { background: var(--dx-ok-soft); color: var(--dx-ok); }
.dx-state[data-tone="warn"] { background: var(--dx-warn-soft); color: var(--dx-warn); }
.dx-state[data-tone="bad"] { background: var(--dx-bad-soft); color: var(--dx-bad); }
.dx-state[data-tone="info"] { background: var(--dx-info-soft); color: var(--dx-info); }
.dx-state[data-tone="mute"] { background: var(--dx-fill); color: var(--dx-ink-2); }

.dx-more { display: flex; justify-content: center; padding: 14px; border-top: 1px solid var(--dx-line-2); }
.dx-empty { padding: 36px 18px; text-align: center; color: var(--dx-ink-3); font-size: 14px; }
.dx-empty b { display: block; color: var(--dx-ink-2); font-size: 15px; margin-bottom: 4px; }

/* ── Vista "Período" ───────────────────────────────────────── */
.dx-band { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.dx-cell { padding: 18px 20px 20px; display: flex; flex-direction: column; gap: 10px; min-width: 0; border-left: 1px solid var(--dx-line-2); }
.dx-cell:first-child { border-left: 0; }
.dx-cell-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.dx-cell-label { font-size: 13px; font-weight: 600; color: var(--dx-ink-2); }
.dx-cell-num { font-size: clamp(28px, 3.4vw, 36px); line-height: 1.05; font-weight: 700; letter-spacing: -0.02em; }
.dx-cell-num small { font-size: .45em; font-weight: 600; color: var(--dx-ink-3); margin-left: 4px; letter-spacing: 0; }
.dx-cell-hint { font-size: 12.5px; color: var(--dx-ink-3); line-height: 1.45; }
.dx-cell-hint b { color: var(--dx-ink-2); font-weight: 650; }

.dx-tag { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 99px; font-size: 11.5px; font-weight: 650; white-space: nowrap; }
.dx-tag[data-tone="ok"] { background: var(--dx-ok-soft); color: var(--dx-ok); }
.dx-tag[data-tone="warn"] { background: var(--dx-warn-soft); color: var(--dx-warn); }
.dx-tag[data-tone="bad"] { background: var(--dx-bad-soft); color: var(--dx-bad); }
.dx-tag[data-tone="info"] { background: var(--dx-info-soft); color: var(--dx-info); }
.dx-tag[data-tone="mute"] { background: var(--dx-fill); color: var(--dx-ink-2); }

.dx-notice { display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px; }
.dx-notice[data-tone="warn"] { background: var(--dx-warn-soft); border-color: #f1d9ad; }
.dx-notice[data-tone="ok"] { background: #f4fbf7; border-color: #cfe9d9; }
.dx-notice i { font-size: 18px; line-height: 1.2; }
.dx-notice[data-tone="warn"] i { color: var(--dx-warn); }
.dx-notice[data-tone="ok"] i { color: var(--dx-ok); }
.dx-notice-title { font-size: 14px; font-weight: 650; }
.dx-notice-text { font-size: 13px; color: var(--dx-ink-2); margin-top: 2px; }
.dx-closures { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.dx-closure { background: rgba(255,255,255,.7); border: 1px solid #ecd2a0; border-radius: 10px; padding: 8px 10px; font-size: 12.5px; }
.dx-closure b { font-weight: 650; }
.dx-closure span { color: var(--dx-ink-2); }

.dx-grid-2 { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); gap: 12px; }
.dx-grid-eq { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.dx-card-pad { padding: 18px 20px 20px; }
.dx-chart { width: 100%; height: 260px; margin-top: 8px; }
.dx-legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 4px; font-size: 12.5px; color: var(--dx-ink-2); }
.dx-legend span { display: inline-flex; align-items: center; gap: 6px; }
.dx-legend i { width: 10px; height: 3px; border-radius: 2px; display: inline-block; }

.dx-bars { display: flex; flex-direction: column; gap: 16px; margin-top: 14px; }
.dx-bar-row-top { display: flex; justify-content: space-between; gap: 10px; font-size: 13.5px; margin-bottom: 6px; }
.dx-bar-row-top span:first-child { font-weight: 600; }
.dx-bar-row-top span:last-child { color: var(--dx-ink-3); }
.dx-track { height: 8px; border-radius: 99px; background: var(--dx-fill); overflow: hidden; }
.dx-track > span { display: block; height: 100%; border-radius: inherit; transform-origin: left center; }

.dx-heat-wrap { overflow-x: auto; margin: 10px -4px 0; padding: 0 4px; }
.dx-heat { min-width: 440px; display: grid; grid-template-columns: minmax(96px, 1.5fr) repeat(7, minmax(36px, 1fr)); gap: 3px; font-size: 12.5px; }
.dx-heat-h { padding: 4px 0 6px; text-align: center; color: var(--dx-ink-3); font-weight: 600; }
.dx-heat-h:first-child { text-align: left; }
.dx-heat-area { display: flex; align-items: center; font-weight: 600; padding-right: 8px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dx-heat-c { height: 34px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-weight: 600; background: var(--dx-fill); color: var(--dx-ink-3); }
.dx-scale { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 12px; font-size: 12px; color: var(--dx-ink-3); }
.dx-scale i { display: inline-block; width: 70px; height: 8px; border-radius: 99px; background: linear-gradient(90deg, rgba(184,34,45,.12), rgba(184,34,45,.85)); }

.dx-ranks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 10px; }
.dx-rank-title { font-size: 13px; font-weight: 650; color: var(--dx-ink-2); margin-bottom: 4px; }
.dx-rank { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-top: 1px solid var(--dx-line-2); font-size: 13.5px; }
.dx-rank:first-of-type { border-top: 0; }
.dx-rank-n { width: 20px; flex: none; color: var(--dx-ink-3); font-weight: 600; }
.dx-rank-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.dx-rank-val { font-weight: 650; }
.dx-rank-val[data-tone="bad"] { color: var(--dx-bad); }
.dx-rank-val[data-tone="warn"] { color: var(--dx-warn); }

.dx-demo { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.dx-demo > div { padding: 18px 20px 20px; border-left: 1px solid var(--dx-line-2); min-width: 0; }
.dx-demo > div:first-child { border-left: 0; }
.dx-demo-title { font-size: 13px; font-weight: 650; color: var(--dx-ink-2); margin-bottom: 12px; }
.dx-kv { display: flex; justify-content: space-between; gap: 8px; font-size: 13.5px; padding: 3px 0; }
.dx-kv span:last-child { font-weight: 650; }
.dx-split { display: flex; height: 8px; border-radius: 99px; overflow: hidden; background: var(--dx-fill); margin: 10px 0 6px; }
.dx-split span { display: block; height: 100%; }
.dx-tight { display: grid; grid-template-columns: 56px minmax(0, 1fr) 28px; align-items: center; gap: 8px; padding: 3px 0; font-size: 12.5px; }
.dx-tight span:first-child { color: var(--dx-ink-2); }
.dx-tight span:last-child { text-align: right; font-weight: 650; }
.dx-tight .dx-track { height: 6px; }
.dx-mini { margin-top: 10px; }
.dx-mini + .dx-mini { margin-top: 12px; }
.dx-mini .dx-bar-row-top { font-size: 12.5px; margin-bottom: 5px; }
.dx-donut-row { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
.dx-donut-legend { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; min-width: 0; }
.dx-donut-legend div { display: flex; align-items: center; gap: 7px; min-width: 0; }
.dx-donut-legend i { width: 8px; height: 8px; border-radius: 3px; flex: none; }
.dx-donut-legend b { font-weight: 650; margin-left: auto; padding-left: 8px; }
.dx-donut-legend span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Estados: carga, error, vacío ──────────────────────────── */
.dx-skel { border-radius: 10px; background: linear-gradient(90deg, #eef1f7 25%, #f6f8fc 50%, #eef1f7 75%); background-size: 200% 100%; animation: dx-sk 1.3s linear infinite; }
.dx-alert { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; margin-bottom: 14px; background: var(--dx-bad-soft); border: 1px solid #f4c4c9; border-radius: 12px; color: var(--dx-bad); font-size: 14px; }
.dx-alert b { display: block; font-weight: 650; }
.dx-alert .dx-iconbtn { margin-left: auto; flex: none; height: 34px; }
.dx-fail { padding: 28px 22px; text-align: center; }
.dx-fail h3 { font-size: 16px; font-weight: 650; }
.dx-fail p { font-size: 13.5px; color: var(--dx-ink-2); margin-top: 6px; word-break: break-word; }
.dx-btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 40px; padding: 0 16px; margin-top: 14px; border: 0; border-radius: 10px; background: var(--dx-brand); color: #fff; font-size: 14px; font-weight: 600; transition: transform 120ms var(--dx-ease), background-color 150ms var(--dx-ease); }
.dx-btn:active { transform: scale(0.97); }
.dx-btn.dx-ghost { background: #fff; color: var(--dx-ink); border: 1px solid var(--dx-line); margin-top: 0; }

/* ── Entrada escalonada (corta, solo opacity/transform) ────── */
.dx-in { animation: dx-in 260ms var(--dx-ease) both; animation-delay: calc(var(--i, 0) * 45ms); }

@keyframes dx-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes dx-sk { to { background-position: -200% 0; } }
@keyframes dx-spin { to { transform: rotate(360deg); } }
@keyframes dx-pulse { 0% { transform: scale(.6); opacity: .35; } 70%, 100% { transform: scale(1.5); opacity: 0; } }

/* Hover solo con puntero fino (en táctil provoca falsos positivos) */
@media (hover: hover) and (pointer: fine) {
  .dx-row:hover { background: #f8faff; }
  .dx-chip:hover:not([aria-pressed="true"]) { border-color: #c6cfe0; color: var(--dx-ink); }
  .dx-iconbtn:hover { border-color: #c6cfe0; color: var(--dx-ink); }
  .dx-seg button:hover:not([aria-selected="true"]) { color: var(--dx-ink); }
  .dx-btn:hover { background: #18307f; }
  .dx-btn.dx-ghost:hover { background: #f6f8fc; }
}

/* ── Tablet ────────────────────────────────────────────────── */
@media (max-width: 1040px) {
  .dx-hero { grid-template-columns: 1fr; }
  .dx-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dx-cell:nth-child(3) { border-left: 0; }
  .dx-cell:nth-child(n+3) { border-top: 1px solid var(--dx-line-2); }
  .dx-grid-2, .dx-grid-eq { grid-template-columns: 1fr; }
  .dx-demo { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dx-demo > div:nth-child(3) { border-left: 0; }
  .dx-demo > div:nth-child(n+3) { border-top: 1px solid var(--dx-line-2); }
}

/* ── Teléfono ──────────────────────────────────────────────── */
@media (max-width: 640px) {
  .dx-bar { flex-direction: column; align-items: stretch; gap: 12px; }
  .dx-seg { display: grid; }
  .dx-seg button { padding: 11px 12px; }
  .dx-filters { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .dx-filters .dx-field.dx-wide { grid-column: 1 / -1; }
  .dx-input, .dx-iconbtn { height: 44px; min-width: 0; width: 100%; font-size: 15px; }
  .dx-iconbtn { justify-content: center; }

  .dx-live { padding: 18px 18px 20px; }
  .dx-stats { gap: 8px; }
  .dx-stat { padding: 14px 12px; gap: 8px; }
  .dx-stat-label { font-size: 12px; gap: 6px; }
  .dx-stat-hint { display: none; }

  .dx-cols { display: none; }
  .dx-row { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "name state" "meta meta"; gap: 4px 12px; padding: 12px 16px; min-height: 0; }
  .dx-row > .dx-name { grid-area: name; }
  .dx-row > .dx-state { grid-area: state; }
  .dx-row > .dx-hide-sm { display: none; }
  .dx-meta { display: block; grid-area: meta; font-size: 12.5px; color: var(--dx-ink-3); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dx-meta b { color: var(--dx-ink-2); font-weight: 600; }
  .dx-roster-head { padding: 14px 16px 12px; }

  .dx-cell { padding: 14px 14px 16px; }
  .dx-cell-hint { display: none; }
  .dx-cell-top { flex-direction: column; align-items: flex-start; gap: 6px; }
  .dx-card-pad { padding: 16px 16px 18px; }
  .dx-chart { height: 210px; }
  .dx-heat { min-width: 0; grid-template-columns: minmax(74px, 1.5fr) repeat(7, minmax(26px, 1fr)); gap: 2px; font-size: 11.5px; }
  .dx-heat-area { font-size: 12px; padding-right: 4px; }
  .dx-heat-c { height: 32px; border-radius: 6px; }
  .dx-ranks { grid-template-columns: 1fr; gap: 14px; }
  .dx-demo { grid-template-columns: 1fr; }
  .dx-demo > div { border-left: 0; border-top: 1px solid var(--dx-line-2); padding: 16px; }
  .dx-demo > div:first-child { border-top: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .dx-in { animation: dx-fade 200ms linear both; animation-delay: 0ms; }
  .dx-dot::after, .dx-iconbtn i.dx-spin, .dx-skel { animation: none; }
  .dx-seg-thumb, .dx-meter > span { transition: none; }
}
@keyframes dx-fade { from { opacity: 0; } to { opacity: 1; } }
`;

// Estilos del Dashboard «Lo que falta hacer» (prefijo dp-). Se inyectan una sola vez desde DashboardApp.
// Colores y letras del tema Aguacol (aguacol-theme.css): navy de marca, verde/naranja/rojo solo para estado.
// Movimiento: solo el giro del botón Actualizar y el color al pasar el mouse; nada al cargar.

export const DP_CSS = `
.dp {
  --dp-navy: var(--ag-navy, #1b2f8f);
  --dp-ink: var(--ag-navy-ink, #0d1a52);
  --dp-text: var(--ag-ink, #1a2326);
  --dp-body: var(--ag-body, #3a4a4a);
  --dp-muted: var(--ag-muted, #5a6a6a);
  --dp-line: var(--ag-line, #d5dede);
  --dp-line-soft: var(--ag-line-soft, #eef1f1);
  --dp-ok: var(--ag-green, #4a8f24);
  --dp-warn: var(--ag-orange, #e8890c);
  --dp-bad: var(--ag-red, #d9463a);
  --dp-blue: var(--ag-blue, #3f6fd6);
  --dp-ease: var(--ag-ease-out, cubic-bezier(0.23, 1, 0.32, 1));
  color: var(--dp-text);
  font-family: var(--font-sans, "Barlow", system-ui, sans-serif);
  max-width: 1400px;
  margin: 0 auto;
  padding-bottom: 32px;
  -webkit-tap-highlight-color: transparent;
}
.dp *, .dp *::before, .dp *::after { box-sizing: border-box; }
.dp h1, .dp h2, .dp h3, .dp p { margin: 0; }
.dp button { font: inherit; cursor: pointer; }
.dp .dp-num { font-family: var(--font-mono, "JetBrains Mono", monospace); font-variant-numeric: tabular-nums; }

.dp-top { display: flex; align-items: center; justify-content: space-between; gap: 12px 20px; flex-wrap: wrap; margin-bottom: 18px; }
.dp-top h1 { font: 600 28px/1.15 var(--font-head, "Barlow Semi Condensed", sans-serif); color: var(--dp-ink); }
.dp-tools { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.dp-select { border: 1px solid var(--dp-line); background: #fff; border-radius: 8px; padding: 7px 10px; font-size: 14px; color: var(--dp-text); min-height: 38px; max-width: 220px; }
.dp-stamp { font-size: 13px; color: var(--dp-muted); }
.dp-btn { display: inline-flex; align-items: center; gap: 6px; border-radius: 8px; padding: 7px 12px; font-size: 14px; font-weight: 600; white-space: nowrap; min-height: 36px; border: 1px solid #c6cfe8; background: #fff; color: var(--dp-navy); transition: background-color 150ms var(--dp-ease), border-color 150ms var(--dp-ease); }
.dp-btn:hover { background: #eef2fc; border-color: var(--dp-navy); }
.dp-btn:focus-visible, .dp-select:focus-visible, .dp-today-row:focus-visible { outline: 2px solid var(--dp-blue); outline-offset: 2px; }
.dp-btn.dp-pr { background: var(--dp-navy); border-color: var(--dp-navy); color: #fff; }
.dp-btn.dp-pr:hover { background: var(--ag-navy-deep, #14235c); }
.dp-btn .bi-arrow-clockwise.dp-spin { animation: dp-spin 0.9s linear infinite; display: inline-block; }
@keyframes dp-spin { to { transform: rotate(360deg); } }

.dp-layout { display: grid; grid-template-columns: minmax(0, 1fr) 400px; grid-template-rows: auto 1fr; grid-template-areas: "main hoy" "main tramo"; gap: 18px 22px; align-items: start; }
.dp-a-main { grid-area: main; min-width: 0; display: flex; flex-direction: column; gap: 18px; }
.dp-a-hoy { grid-area: hoy; }
.dp-a-tramo { grid-area: tramo; }
.dp-pair { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 18px; align-items: start; }

.dp-card { background: #fff; border: 1px solid var(--dp-line); border-radius: 12px; padding: 18px 20px; min-width: 0; }
.dp-card-head { display: flex; align-items: baseline; justify-content: space-between; gap: 6px 16px; flex-wrap: wrap; }
.dp-card-head h2 { font: 600 21px/1.2 var(--font-head, "Barlow Semi Condensed", sans-serif); color: var(--dp-ink); }
.dp-card-sub { font-size: 14px; color: var(--dp-muted); }
.dp-foot { margin-top: 12px; }

.dp-chip { display: inline-block; padding: 2px 9px; border-radius: 6px; font-size: 13px; font-weight: 600; white-space: nowrap; }
.dp-chip[data-tone="ok"] { background: #e8f2e1; color: #2f5e16; }
.dp-chip[data-tone="ready"] { background: #e6edfb; color: var(--dp-navy); }
.dp-chip[data-tone="warn"] { background: #fdf0dd; color: #8a4f05; }

.dp-segs { display: flex; gap: 4px; margin: 12px 0 4px; }
.dp-segs span { flex: 1; height: 8px; border-radius: 3px; }
.dp-legend-line { font-size: 13px; color: var(--dp-muted); }

.dp-close-row { display: grid; grid-template-columns: 190px auto minmax(0, 1fr) auto; align-items: center; gap: 8px 16px; padding: 13px 0; border-top: 1px solid var(--dp-line-soft); }
.dp-close-list { margin-top: 10px; }
.dp-close-area { font-size: 16px; font-weight: 600; }
.dp-close-why { font-size: 14px; color: var(--dp-muted); min-width: 0; }

.dp-bar-row { display: grid; grid-template-columns: minmax(0, 170px) minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 7px 0; font-size: 15px; }
.dp-track { height: 10px; background: var(--dp-line-soft); border-radius: 3px; overflow: hidden; }
.dp-track > span { display: block; height: 100%; background: var(--dp-blue); border-radius: 3px; }

.dp-list { margin-top: 10px; }
.dp-list-row { display: flex; align-items: center; gap: 14px; padding: 10px 0; border-top: 1px solid var(--dp-line-soft); font-size: 15px; }
.dp-list-row .dp-grow { flex: 1; min-width: 0; }
.dp-soon { color: #b3352b; }
.dp-when { font-size: 13px; color: var(--dp-muted); white-space: nowrap; }
.dp-when.dp-soon { color: #b3352b; font-weight: 600; }

.dp-quiet { font-size: 14px; color: var(--dp-muted); padding: 0 4px; display: flex; gap: 6px; align-items: center; }
.dp-quiet .bi-check-circle { color: var(--dp-ok); }
.dp-empty { font-size: 14px; color: var(--dp-muted); margin-top: 10px; }

.dp-today-row { width: calc(100% + 12px); text-align: left; border: 0; background: none; padding: 9px 6px; margin: 0 -6px; border-radius: 8px; display: block; color: inherit; transition: background-color 150ms var(--dp-ease); }
.dp-today-row:hover { background: #f4f7f7; }
.dp-today-top { display: flex; justify-content: space-between; gap: 10px; font-size: 15px; }
.dp-stack { display: flex; height: 10px; border-radius: 3px; overflow: hidden; background: var(--dp-line-soft); margin-top: 5px; }
.dp-stack > span { height: 100%; }
.dp-stack > span + span { border-left: 2px solid #fff; }
.dp-today-note { font-size: 12px; color: var(--dp-muted); margin-top: 3px; }
.dp-keys { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--dp-muted); margin-top: 10px; }
.dp-keys i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; }
.dp-today-total { font-size: 15px; color: var(--dp-body); margin-top: 4px; }
.dp-today-total b { color: var(--dp-text); }

.dp-table { width: 100%; border-collapse: collapse; font-size: 15px; margin-top: 8px; }
.dp-table th { font-size: 12px; font-weight: 500; color: var(--dp-muted); text-align: right; padding: 4px 0; }
.dp-table th:first-child { text-align: left; }
.dp-table td { padding: 7px 0; border-top: 1px solid var(--dp-line-soft); text-align: right; }
.dp-table td:first-child { text-align: left; }
.dp-high { color: #a35f00; }

.dp-alert { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; background: #fdecea; border: 1px solid #f3c2bc; color: #7d1f16; border-radius: 10px; padding: 12px 14px; margin-bottom: 16px; }
.dp-skel { background: linear-gradient(90deg, #eef1f1 25%, #f6f8f8 50%, #eef1f1 75%); background-size: 200% 100%; animation: dp-sh 1.2s linear infinite; border-radius: 8px; }
@keyframes dp-sh { to { background-position: -200% 0; } }

@media (prefers-reduced-motion: reduce) {
  .dp-skel, .dp-btn .bi-arrow-clockwise.dp-spin { animation: none; }
}

@media (max-width: 1180px) {
  .dp-layout { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; grid-template-areas: "hoy" "main" "tramo"; }
}
.dp-solo-movil { display: none; }
@media (max-width: 760px) {
  .dp-solo-movil { display: flex; }
  .dp-hoy-areas:not(.dp-open) { display: none; }
  .dp-top h1 { font-size: 24px; }
  .dp-pair { grid-template-columns: minmax(0, 1fr); }
  .dp-card { padding: 14px; }
  .dp-close-row { grid-template-columns: minmax(0, 1fr) auto; }
  .dp-close-why { grid-column: 1 / -1; font-size: 13px; }
  .dp-close-row .dp-btn { grid-column: 1 / -1; justify-self: start; }
  .dp-bar-row { grid-template-columns: minmax(0, 1fr) auto; }
  .dp-bar-row .dp-track { display: none; }
  .dp-tools { width: 100%; }
  .dp-select { flex: 1; max-width: none; }
}
`;

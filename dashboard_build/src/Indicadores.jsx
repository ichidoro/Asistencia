import React, { useEffect, useRef, useState } from 'react';
import { num, fmt, plural, fechaCorta } from './ui';

// Pestaña «Indicadores» (estructura B): lo que más se desvió primero, cada indicador con su tacómetro.
// Lenguaje neutro (pedido del dueño): «Para mejorar» y «En buen camino», nunca «empeoró».
// «Ver detalle» abre un panel con los registros que forman el número (PanelDetalle).
// La aguja marca el tramo elegido; la raya gris, el promedio de los tramos anteriores.

const SECCIONES = [
  ['empeoro', 'Para mejorar', 'bad'],
  ['mejoro', 'En buen camino', 'good'],
  ['igual', 'Igual que su promedio', 'mute'],
  ['sin_comparacion', 'Sin tramos anteriores para comparar', 'mute'],
];

// Tope de la escala: 100 en un porcentaje donde más es mejor; si no, el número «redondo» siguiente a 1,25 veces lo mayor.
export function topeEscala(i) {
  if (i.unidad === '%' && i.mejor === 'alto') return 100;
  const x = 1.25 * Math.max(num(i.valor), num(i.promedio), 0.1);
  const p = Math.pow(10, Math.floor(Math.log10(x)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= x) return m * p;
  return 10 * p;
}

const decimales = (i) => (i.id === 'faltas' ? 0 : 1);
const unidad = (i) => (!i.unidad ? '' : i.unidad === '%' ? ' %' : ` ${i.unidad}`);
export const valorTexto = (i, v, dec) => (v === null || v === undefined ? '–' : `${fmt(v, dec === undefined ? decimales(i) : dec)}${unidad(i)}`);
const mesCorto = (mes) => String(mes || '').split(' ')[0].toLowerCase();

export function textoCambio(i) {
  if (i.estado === 'sin_comparacion') return 'Sin tramos anteriores para comparar';
  if (i.estado === 'igual') return 'Igual a su promedio';
  if (num(i.promedio) === 0) return 'Su promedio era 0';
  const c = num(i.cambio);
  if (Math.abs(c) >= 100) return `${fmt(num(i.valor) / num(i.promedio), 1)} veces su promedio`;
  return `${fmt(Math.abs(c), 0)} % ${c > 0 ? 'sobre' : 'bajo'} su promedio`;
}

export function textoDonde(i) {
  if (i.id === 'rotacion' && i.detalle) {
    return `${plural(i.detalle.bajas, 'baja', 'bajas')} y ${plural(i.detalle.ingresos, 'ingreso', 'ingresos')}`;
  }
  const d = Array.isArray(i.donde) ? i.donde : [];
  if (!d.length) return '';
  if (i.tipo === 'total') return d.map((x) => `${x.area} ${valorTexto(i, x.valor)}`).join(' · ');
  const partes = d.map((x) => `${x.area} ${valorTexto(i, x.valor)} (su promedio ${valorTexto(i, x.promedio, 1)})`);
  return i.estado === 'mejoro' ? `Para mejorar en ${partes.join(' · ')}` : partes.join(' · ');
}

function Tacometro({ i }) {
  const W = 150, H = 90, cx = W / 2, cy = 85, r = 60, sw = 13;
  const max = topeEscala(i);
  const a = (x) => Math.PI * (1 - Math.min(Math.max(num(x) / max, 0), 1));
  const pt = (x, rr) => [cx + rr * Math.cos(a(x)), cy - rr * Math.sin(a(x))];
  const arco = (x1, x2, color) => {
    if (Math.abs(num(x2) - num(x1)) < 1e-9) return null;
    const [p1, q1] = pt(x1, r), [p2, q2] = pt(x2, r);
    return <path d={`M${p1.toFixed(1)} ${q1.toFixed(1)} A${r} ${r} 0 0 1 ${p2.toFixed(1)} ${q2.toFixed(1)}`} stroke={color} strokeWidth={sw} fill="none" />;
  };
  const hayProm = i.promedio !== null && i.promedio !== undefined;
  const BUENO = '#cfe5bf', MALO = '#f6d2a8';
  const zonas = !hayProm ? arco(0, max, '#e3e8e8')
    : i.mejor === 'alto' ? <>{arco(0, i.promedio, MALO)}{arco(i.promedio, max, BUENO)}</>
      : <>{arco(0, i.promedio, BUENO)}{arco(i.promedio, max, MALO)}</>;
  const [m1x, m1y] = pt(i.promedio, r - sw * 0.8), [m2x, m2y] = pt(i.promedio, r + sw * 0.8);
  const [nx, ny] = pt(i.valor, r * 0.82);
  const etiqueta = `${i.nombre}: ${valorTexto(i, i.valor)}${hayProm ? `, promedio ${valorTexto(i, i.promedio)}` : ''}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={etiqueta}>
      <title>{etiqueta}</title>
      {zonas}
      {hayProm ? <line x1={m1x} y1={m1y} x2={m2x} y2={m2y} stroke="#5a6a6a" strokeWidth="2" /> : null}
      {i.valor !== null && i.valor !== undefined ? <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#0d1a52" strokeWidth="2.5" strokeLinecap="round" /> : null}
      <circle cx={cx} cy={cy} r="5" fill="#0d1a52" />
    </svg>
  );
}

function Fila({ i, onDetalle }) {
  const tono = i.estado === 'empeoro' ? 'bad' : i.estado === 'mejoro' ? 'good' : 'mute';
  const donde = textoDonde(i);
  return (
    <div className="dp-ind-row">
      <div className="dp-ind-g"><Tacometro i={i} /></div>
      <div>
        <div className="dp-ind-name">{i.nombre}</div>
        <div className="dp-ind-def">{i.definicion}</div>
        {i.nota ? <div className="dp-ind-nota">{i.nota}</div> : null}
      </div>
      <div>
        <div className="dp-ind-val dp-num">{valorTexto(i, i.valor)}</div>
        <div className="dp-ind-prom">promedio {valorTexto(i, i.promedio, 1)}</div>
      </div>
      <div className="dp-ind-est" data-tone={tono}>
        <i className={`bi ${tono === 'bad' ? 'bi-bullseye' : tono === 'good' ? 'bi-check-circle' : 'bi-dash-circle'}`} aria-hidden="true" /> {textoCambio(i)}
      </div>
      <div className="dp-ind-donde">{donde ? <><span className="dp-ind-lbl">Dónde:</span> {donde}</> : null}</div>
      <button type="button" className="dp-btn" onClick={() => onDetalle(i)}>Ver detalle</button>
    </div>
  );
}

export default function Indicadores({ data, onDetalle }) {
  const lista = Array.isArray(data && data.indicadores) ? data.indicadores : [];
  if (!data || !data.tramo) {
    return <div className="dp-card"><div className="dp-empty">Todavía no hay tramos con días programados para calcular indicadores.</div></div>;
  }
  const n = (e) => lista.filter((i) => i.estado === e).length;
  const comp = data.comparado_con || [];
  const rango = comp.length === 0 ? '' : comp.length === 1 ? mesCorto(comp[0]) : `${mesCorto(comp[0])} a ${mesCorto(comp[comp.length - 1])}`;
  const mes = mesCorto(data.tramo.mes);
  return (
    <div>
      <div className="dp-ind-head">
        <h2>En {mes}{data.tramo.en_curso ? ' (tramo en curso, hasta hoy)' : ''} hay {plural(n('empeoro'), 'indicador', 'indicadores')} para mejorar y {fmt(n('mejoro'))} en buen camino</h2>
        <p>
          La aguja marca {mes}{comp.length ? <> y la raya gris, el promedio de {rango} ({plural(comp.length, 'tramo', 'tramos')})</> : null}.
          {' '}Verde: lado del buen camino · naranjo: lado para mejorar. Cada tramo cerrado guarda el cálculo de su época.
        </p>
      </div>
      {SECCIONES.map(([estado, titulo, tono]) => {
        const filas = lista.filter((i) => i.estado === estado);
        if (!filas.length) return null;
        return (
          <section className="dp-card dp-ind-sec" key={estado}>
            <h3 className="dp-ind-sectitle" data-tone={tono}>{titulo}</h3>
            {filas.map((i) => <Fila key={i.id} i={i} onDetalle={onDetalle} />)}
          </section>
        );
      })}
    </div>
  );
}

// Valor de una celda del detalle: fechas cortas y números con los decimales que traen.
const celda = (id, v) => {
  if (v === null || v === undefined || v === '') return '–';
  if (id === 'fecha') return fechaCorta(v);
  if (typeof v === 'number') return fmt(v, Number.isInteger(v) ? 0 : 1);
  return String(v);
};
const sinTildes = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const PAGINA = 40;

// Panel con los registros de un indicador: un resumen arriba y una fila por persona que se abre
// para ver cada registro (día, hora, quién ingresó la marca...). No cambia nada: solo muestra.
export function PanelDetalle({ i, tramo, area, pedir, onClose, onGrilla }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [buscar, setBuscar] = useState('');
  const [abierta, setAbierta] = useState(null);
  const [limite, setLimite] = useState(PAGINA);
  const cerrarRef = useRef(null);
  const tramoId = tramo ? tramo.id : null;

  useEffect(() => {
    let vivo = true;
    setData(null); setError(null); setAbierta(null); setLimite(PAGINA);
    pedir(i.id, tramoId)
      .then((d) => { if (vivo) setData(d); })
      .catch((e) => { if (vivo) setError(e.message || 'No se pudo armar el detalle.'); });
    return () => { vivo = false; };
  }, [i.id, tramoId, area, pedir]);

  useEffect(() => {
    if (cerrarRef.current) cerrarRef.current.focus();
    const tecla = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', tecla);
    return () => document.removeEventListener('keydown', tecla);
  }, [onClose]);

  const q = sinTildes(buscar.trim());
  const personas = data ? data.personas.filter((p) => !q || sinTildes(p.persona).includes(q)) : [];
  const cols = data ? data.columnas : [];
  const colsR = data ? data.columnas_registro : [];
  const plantilla = `minmax(0, 2fr) repeat(${cols.length}, minmax(0, 1fr))`;
  const plantillaR = `repeat(${colsR.length}, minmax(0, 1fr))`;
  return (
    <div className="dp-det-wrap">
      <div className="dp-det-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="dp-det" role="dialog" aria-modal="true" aria-labelledby="dp-det-titulo">
        <div className="dp-det-head">
          <div style={{ minWidth: 0 }}>
            <h2 id="dp-det-titulo">{i.nombre}</h2>
            <div className="dp-det-sub">
              {tramo ? tramo.mes : ''} · {area && area !== 'Todas' ? area : 'todas las áreas'} · {valorTexto(i, i.valor)} (promedio {valorTexto(i, i.promedio, 1)})
            </div>
            <div className="dp-det-def">{i.definicion}</div>
          </div>
          <button type="button" ref={cerrarRef} className="dp-btn" onClick={onClose} aria-label="Cerrar el detalle"><i className="bi bi-x-lg" aria-hidden="true" /></button>
        </div>
        {error ? <div className="dp-alert" role="alert">{error}</div> : null}
        {!data && !error ? <div className="dp-empty">Cargando el detalle…</div> : null}
        {data ? (
          <>
            <div className="dp-det-res">
              {data.resumen.map((r) => <div key={r.etiqueta}><span>{r.etiqueta}</span><b className="dp-num">{celda('', r.valor)}</b></div>)}
            </div>
            {data.resumen_extra ? (
              <div className="dp-det-extra">
                <span>{data.resumen_extra.titulo}:</span> {data.resumen_extra.items.map((x) => `${x.etiqueta} ${fmt(x.valor)}`).join(' · ')}
              </div>
            ) : null}
            <div className="dp-det-tools">
              <input className="dp-select" type="search" placeholder="Buscar persona" value={buscar}
                onChange={(e) => { setBuscar(e.target.value); setLimite(PAGINA); }} aria-label="Buscar persona" />
              <span className="dp-det-cnt">{plural(personas.length, 'persona', 'personas')}</span>
            </div>
            {personas.length === 0 ? (
              <div className="dp-empty">No hay registros{q ? ' para esa búsqueda' : ' en este tramo'}.</div>
            ) : (
              <div className="dp-det-tabla" role="table" aria-label={`Detalle de ${i.nombre} por persona`}>
                <div className="dp-det-fila dp-det-th" role="row" style={{ gridTemplateColumns: plantilla }}>
                  <span role="columnheader">Persona</span>
                  {cols.map((c) => <span role="columnheader" key={c.id}>{c.titulo}</span>)}
                </div>
                {personas.slice(0, limite).map((p, n) => {
                  const clave = `${p.persona}-${n}`;
                  const abre = p.registros.length > 0;
                  const ab = abierta === clave;
                  return (
                    <div key={clave} className="dp-det-grupo">
                      <button type="button" role="row" className="dp-det-fila" disabled={!abre} aria-expanded={abre ? ab : undefined}
                        onClick={() => setAbierta(ab ? null : clave)} style={{ gridTemplateColumns: plantilla }}>
                        <span className="dp-det-per" role="cell">
                          {abre ? <i className={`bi bi-chevron-${ab ? 'down' : 'right'}`} aria-hidden="true" /> : null}
                          <span><b>{p.persona}</b><small>{p.area}</small></span>
                        </span>
                        {cols.map((c) => <span role="cell" className="dp-num" key={c.id}>{celda(c.id, p.valores[c.id])}</span>)}
                      </button>
                      {ab ? (
                        <div className="dp-det-reg">
                          <div className="dp-det-rfila dp-det-th" style={{ gridTemplateColumns: plantillaR }}>
                            {colsR.map((c) => <span key={c.id}>{c.titulo}</span>)}
                          </div>
                          {p.registros.map((r, k) => (
                            <div className="dp-det-rfila" key={k} style={{ gridTemplateColumns: plantillaR }}>
                              {colsR.map((c) => (
                                <span key={c.id} className={c.id === 'fecha' || typeof r[c.id] === 'number' ? 'dp-num' : ''}>{celda(c.id, r[c.id])}</span>
                              ))}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
                {personas.length > limite ? (
                  <div className="dp-foot">
                    <button type="button" className="dp-btn" onClick={() => setLimite((l) => l + PAGINA)}>Mostrar {Math.min(PAGINA, personas.length - limite)} más</button>
                  </div>
                ) : null}
              </div>
            )}
            <div className="dp-det-pie">
              <button type="button" className="dp-btn" onClick={onGrilla}>{i.accion === 'empleados' ? 'Ir a Empleados' : 'Abrir en la grilla para corregir'}</button>
              <button type="button" className="dp-btn dp-pr" onClick={onClose}>Cerrar</button>
            </div>
          </>
        ) : null}
      </aside>
    </div>
  );
}

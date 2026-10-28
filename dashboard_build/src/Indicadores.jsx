import React from 'react';
import { num, fmt, plural } from './ui';

// Pestaña «Indicadores» (estructura B): lo que empeoró primero, cada indicador con su tacómetro.
// La aguja marca el tramo elegido; la raya gris, el promedio de los tramos anteriores.

const SECCIONES = [
  ['empeoro', 'Empeoraron', 'bad'],
  ['mejoro', 'Mejoraron', 'good'],
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
  const verbo = i.estado === 'empeoro' ? 'Empeoró' : 'Mejoró';
  if (num(i.promedio) === 0) return `${verbo}: su promedio era 0`;
  const c = num(i.cambio);
  if (Math.abs(c) >= 100) return `${verbo}: ${fmt(num(i.valor) / num(i.promedio), 1)} veces su promedio`;
  return `${verbo}: ${c > 0 ? '+' : '−'}${fmt(Math.abs(c), 0)} % vs su promedio`;
}

export function textoDonde(i) {
  if (i.id === 'rotacion' && i.detalle) {
    return `${plural(i.detalle.bajas, 'baja', 'bajas')} y ${plural(i.detalle.ingresos, 'ingreso', 'ingresos')}`;
  }
  const d = Array.isArray(i.donde) ? i.donde : [];
  if (!d.length) return '';
  if (i.tipo === 'total') return d.map((x) => `${x.area} ${valorTexto(i, x.valor)}`).join(' · ');
  const partes = d.map((x) => `${x.area} ${valorTexto(i, x.valor)} (su promedio ${valorTexto(i, x.promedio, 1)})`);
  return i.estado === 'mejoro' ? `Empeoró en ${partes.join(' · ')}` : partes.join(' · ');
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
        <i className={`bi ${tono === 'bad' ? 'bi-exclamation-triangle' : tono === 'good' ? 'bi-graph-up-arrow' : 'bi-dash-circle'}`} aria-hidden="true" /> {textoCambio(i)}
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
        <h2>En {mes}{data.tramo.en_curso ? ' (tramo en curso, hasta hoy)' : ''} empeoraron {plural(n('empeoro'), 'indicador', 'indicadores')} y mejoraron {fmt(n('mejoro'))}</h2>
        <p>
          La aguja marca {mes}{comp.length ? <> y la raya gris, el promedio de {rango} ({plural(comp.length, 'tramo', 'tramos')})</> : null}.
          {' '}Verde: lado mejor que el promedio · naranjo: lado peor. Cada tramo cerrado guarda el cálculo de su época.
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

import React from 'react';

// ── Helpers numéricos / de formato (todo tolerante a null/undefined) ─────────
export const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
export const fmt = (v, digits = 0) =>
  num(v).toLocaleString('es-CL', { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const hrs = (v) => `${fmt(v, Math.abs(num(v)) < 10 && num(v) % 1 !== 0 ? 1 : 0)} h`;
export const hhmm = (v) => (typeof v === 'string' && v.length >= 5 ? v.substring(0, 5) : '–');
export const horaActual = (d) =>
  d ? d.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' }) : '';

// ── Barrera de errores: si algo falla al dibujar, se muestra el motivo y se puede reintentar ──
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[Dashboard] error de render:', error, info && info.componentStack);
  }
  render() {
    if (!this.state.error) return this.props.children;
    const msg = String((this.state.error && this.state.error.message) || this.state.error);
    return (
      <div className="dx-panel dx-fail" role="alert">
        <h3>No se pudo mostrar esta vista</h3>
        <p>Detalle técnico: {msg}</p>
        <button type="button" className="dx-btn" onClick={() => this.setState({ error: null })}>
          Reintentar
        </button>
      </div>
    );
  }
}

// ── Piezas visuales ───────────────────────────────────────────────────────────
export function Seg({ value, onChange, options, label }) {
  return (
    <div className="dx-seg" data-active={value} role="tablist" aria-label={label}>
      <span className="dx-seg-thumb" aria-hidden="true" />
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ h = 16, w = '100%', r = 10, style }) {
  return <div className="dx-skel" style={{ height: h, width: w, borderRadius: r, ...style }} aria-hidden="true" />;
}

export function Tag({ tone = 'mute', children }) {
  return <span className="dx-tag" data-tone={tone}>{children}</span>;
}

export function Meter({ value, tone }) {
  const pct = Math.max(0, Math.min(100, num(value)));
  return (
    <div className="dx-meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
      <span style={{ transform: `scaleX(${pct / 100})`, background: tone || undefined }} />
    </div>
  );
}

// Entrada escalonada: <In i={2}>…</In>
export function In({ i = 0, className = '', children, as: Tagname = 'div', ...rest }) {
  return (
    <Tagname className={`dx-in ${className}`} style={{ '--i': i }} {...rest}>
      {children}
    </Tagname>
  );
}

import React from 'react';

// ── Helpers numéricos / de formato (todo tolerante a null/undefined) ─────────
export const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
export const fmt = (v, digits = 0) =>
  num(v).toLocaleString('es-CL', { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const pct = (v) => (v === null || v === undefined ? '–' : `${fmt(v, num(v) % 1 ? 1 : 0)} %`);
export const plural = (n, uno, varios) => `${fmt(n)} ${num(n) === 1 ? uno : varios}`;

const DIAS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
// '2026-10-30' → 'Vie 30-10' (la fecha se lee como día local, sin zona horaria)
export const fechaCorta = (iso) => {
  const [y, m, d] = String(iso || '').slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return '–';
  const f = new Date(y, m - 1, d);
  return `${DIAS[f.getDay()]} ${String(d).padStart(2, '0')}-${String(m).padStart(2, '0')}`;
};
export const diasHasta = (iso, hoyIso) => {
  const a = String(hoyIso || '').slice(0, 10).split('-').map(Number);
  const b = String(iso || '').slice(0, 10).split('-').map(Number);
  if (a.length < 3 || b.length < 3) return null;
  return Math.round((new Date(b[0], b[1] - 1, b[2]) - new Date(a[0], a[1] - 1, a[2])) / 86400000);
};

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
      <div className="dp-alert" role="alert">
        <div><b>No se pudo mostrar el dashboard.</b> Detalle técnico: {msg}</div>
        <button type="button" className="dp-btn" onClick={() => this.setState({ error: null })}>Reintentar</button>
      </div>
    );
  }
}

export function Skeleton({ h = 16, w = '100%', style }) {
  return <div className="dp-skel" style={{ height: h, width: w, ...style }} aria-hidden="true" />;
}

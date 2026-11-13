import React from 'react';
import ReactDOM from 'react-dom/client';
import DashboardApp from './DashboardApp';

let reactRoot = null;
let visitas = 0;   // cada entrada al Dashboard cuenta una visita y el Dashboard vuelve a pedir sus datos

function initDashboard() {
  const container = document.getElementById('page-dashboard');
  if (container) {
    // If the root div has not been created, replace inner HTML and initialize
    const rootElement = document.getElementById('react-dashboard-root');
    if (!rootElement) {
      container.innerHTML = '<div id="react-dashboard-root" class="w-100 h-100"></div>';
    }
    
    if (!reactRoot) {
      const mountNode = document.getElementById('react-dashboard-root');
      reactRoot = ReactDOM.createRoot(mountNode);
    }
    
    reactRoot.render(
      <React.StrictMode>
        <DashboardApp visita={++visitas} />
      </React.StrictMode>
    );
  }
}

// Expose the function globally so main.js can trigger it when the page changes
window.initDashboard = initDashboard;

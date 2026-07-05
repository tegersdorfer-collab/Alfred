import { describe, it, expect } from 'vitest';
import { renderGauge } from './main';

describe('renderGauge', () => {
  it('rendert ein SVG mit einem Kreis pro Metrik', () => {
    const container = document.createElement('div');
    renderGauge(container, 'System-Status', [
      { label: 'CPU', pct: 45, color: '#00e5ff' },
      { label: 'RAM', pct: 60, color: '#00e5ff' },
    ]);
    expect(container.querySelectorAll('circle.gauge-value').length).toBe(2);
    expect(container.textContent).toContain('System-Status');
  });

  it('rendert 0% als leeren Kreis ohne Fehler', () => {
    const container = document.createElement('div');
    expect(() =>
      renderGauge(container, 'System-Status', [{ label: 'CPU', pct: 0, color: '#00e5ff' }]),
    ).not.toThrow();
  });
});

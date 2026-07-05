import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderGauge, triggerSpeakingState } from './main';

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

describe('triggerSpeakingState', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="hud-ring"></div>';
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fügt die speaking-Klasse sofort hinzu', () => {
    triggerSpeakingState();
    expect(document.getElementById('hud-ring')!.classList.contains('speaking')).toBe(true);
  });

  it('entfernt die speaking-Klasse nach der angegebenen Dauer', () => {
    triggerSpeakingState(2000);
    vi.advanceTimersByTime(2000);
    expect(document.getElementById('hud-ring')!.classList.contains('speaking')).toBe(false);
  });

  it('tut nichts wenn #hud-ring nicht existiert', () => {
    document.body.innerHTML = '';
    expect(() => triggerSpeakingState()).not.toThrow();
  });
});

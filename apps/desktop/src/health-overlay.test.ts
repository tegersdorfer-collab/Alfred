import { describe, it, expect } from 'vitest';
import { overviewHtml, drilldownHtml, widgetHtml } from './health-overlay';

const DATA = {
  narrative: 'Sleep 47. Schwächster Bereich: Sleep — Haupttreiber Schlafdauer.',
  body: { latest: 83.6, delta_30d: -0.8, direction: 'down' },
  today: {
    date: '2026-07-13',
    domains: {
      recovery: { score: null, status: 'insufficient_data', coverage: 0.25, components: [] },
      sleep: { score: 47.2, status: 'ok', coverage: 1.0, components: [] },
      activity: { score: null, status: 'insufficient_data', coverage: 0.25, components: [] },
    },
  },
  days: [],
};

describe('overviewHtml (Ring-Hero)', () => {
  it('zeigt alle Domain-Labels', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('Recovery');
    expect(html).toContain('Sleep');
    expect(html).toContain('Activity');
  });

  it('rendert den echten Score der ok-Domain und "—" bei zu wenig Daten', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('47'); // sleep-Score
    expect(html).toContain('—'); // recovery/activity leer, kein Fake-Score
  });

  it('zeigt den Mantis-Klartext und den Gewichts-Trend', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('Schwächster Bereich: Sleep');
    expect(html).toContain('83.6');
  });
});

describe('widgetHtml (HUD-Glance)', () => {
  it('rendert kompakte Ringe mit Score bzw. "—"', () => {
    const html = widgetHtml({
      domains: {
        recovery: { score: 62, status: 'ok' },
        sleep: { score: null, status: 'insufficient_data' },
        activity: { score: 40, status: 'ok' },
      },
    });
    expect(html).toContain('Health');
    expect(html).toContain('62');
    expect(html).toContain('40');
    expect(html).toContain('—');
  });
});

describe('drilldownHtml', () => {
  const recovery = {
    score: 62.0,
    status: 'ok',
    coverage: 1.0,
    components: [
      { metric: 'hrv', value: 48, score: 40.0, weight: 0.45, used: true },
      { metric: 'resting_hr', value: null, score: null, weight: 0.3, used: false },
    ],
  };

  it('zeigt Domain, Score und Rücklink', () => {
    const html = drilldownHtml('recovery', recovery, []);
    expect(html).toContain('Recovery');
    expect(html).toContain('62');
    expect(html).toContain('Übersicht');
  });

  it('schlüsselt Sub-Metriken mit Score auf, auch fehlende', () => {
    const html = drilldownHtml('recovery', recovery, []);
    expect(html).toContain('HRV');
    expect(html).toContain('40'); // hrv-Subscore
    expect(html).toContain('Ruhepuls'); // fehlende Komponente wird trotzdem gelistet
  });

  it('zeigt den Leer-Zustand ehrlich statt Fake-Score', () => {
    const empty = { score: null, status: 'insufficient_data', coverage: 0.25, components: [] };
    expect(drilldownHtml('recovery', empty, [])).toContain('zu wenig Daten');
  });
});

import { describe, it, expect } from 'vitest';
import { overviewHtml, widgetHtml } from './skilltree-overlay';

const DATA = {
  axes: [
    { axis: 'koerper', label: 'Körper', xp: 400, level: 2, trend: 12 },
    { axis: 'wissen', label: 'Wissen', xp: 100, level: 1, trend: -8 },
  ],
  nodes: [{ key: 'dl_100', label: '100 kg Kreuzheben', axis: 'koerper' }],
  quests: [{ key: 'zettel_5', axis: 'wissen', label: '5 neue Zettel schreiben',
             progress: { count: 2, pct: 0.4, done: false } }],
};

describe('overviewHtml', () => {
  it('zeigt Achsen mit Level', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('Körper');
    expect(html).toContain('Lv2');
    expect(html).toContain('Wissen');
  });
  it('markiert eine rostende Achse (negativer Trend)', () => {
    expect(overviewHtml(DATA)).toContain('↓'); // Wissen trend -8
  });
  it('listet die nächste Quest mit Fortschritt', () => {
    const html = overviewHtml(DATA);
    expect(html).toContain('5 neue Zettel');
    expect(html).toContain('40'); // pct 0.4 → 40%
  });
  it('zeigt freigeschaltete Nodes', () => {
    expect(overviewHtml(DATA)).toContain('100 kg Kreuzheben');
  });
});

describe('widgetHtml', () => {
  it('kompakte Achsen-Glance', () => {
    const html = widgetHtml(DATA);
    expect(html).toContain('Skilltree');
    expect(html).toContain('Körper');
  });
});

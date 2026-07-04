import { describe, it, expect } from 'vitest';
import { deriveHudState } from './hud-state';

describe('deriveHudState', () => {
  it('zeigt online-Zustand mit Cyan-Ring wenn Backend erreichbar', () => {
    const now = new Date('2026-07-04T18:30:00');
    const state = deriveHudState({ ok: true }, now);
    expect(state.ringColor).toBe('#00e5ff');
    expect(state.label).toBe('Alfred ist bereit.');
  });

  it('zeigt offline-Zustand mit gedämpftem Ring wenn Backend nicht erreichbar', () => {
    const now = new Date('2026-07-04T18:30:00');
    const state = deriveHudState({ ok: false }, now);
    expect(state.ringColor).toBe('#334155');
    expect(state.label).toBe('Keine Verbindung zu Alfred.');
  });

  it('formatiert die Uhrzeit in der Statuszeile', () => {
    const now = new Date('2026-07-04T09:05:00');
    const state = deriveHudState({ ok: true }, now);
    expect(state.statusLine).toContain('09:05');
  });
});

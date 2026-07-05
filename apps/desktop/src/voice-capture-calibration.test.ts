import { describe, it, expect } from 'vitest';
import { computeCalibratedThreshold } from './voice-capture';

describe('computeCalibratedThreshold', () => {
  it('setzt den Schwellwert auf das 2.5-fache des mittleren Rauschpegels', () => {
    const samples = [0.01, 0.012, 0.008, 0.01]; // mean = 0.01
    expect(computeCalibratedThreshold(samples)).toBeCloseTo(0.025, 5);
  });

  it('fällt bei sehr leiser Umgebung auf den Mindestwert zurück', () => {
    const samples = [0.0001, 0.0002, 0.0001];
    expect(computeCalibratedThreshold(samples)).toBe(0.006);
  });

  it('wirft nicht bei einem leeren Array — Mindestwert als Fallback', () => {
    expect(computeCalibratedThreshold([])).toBe(0.006);
  });

  it('rundet nicht auf 0 bei exakt lautlosen Samples', () => {
    expect(computeCalibratedThreshold([0, 0, 0])).toBe(0.006);
  });
});

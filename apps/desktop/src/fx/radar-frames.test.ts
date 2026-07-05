import { describe, it, expect, vi } from 'vitest';
import { fetchRadarFrameTimes, radarTileUrl } from './radar-frames';

describe('fetchRadarFrameTimes', () => {
  it('gibt die letzten 4 Zeitstempel aus radar.past zurück', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        radar: { past: [{ time: 1 }, { time: 2 }, { time: 3 }, { time: 4 }, { time: 5 }] },
      }),
    });
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([2, 3, 4, 5]);
  });

  it('gibt alle Zeitstempel zurück wenn weniger als 4 verfügbar sind', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ radar: { past: [{ time: 10 }, { time: 20 }] } }),
    });
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([10, 20]);
  });

  it('gibt ein leeres Array zurück bei Netzwerkfehler statt zu werfen', async () => {
    const fakeFetch = vi.fn().mockRejectedValue(new Error('network down'));
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([]);
  });

  it('gibt ein leeres Array zurück bei unerwarteter Antwortstruktur', async () => {
    const fakeFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ unexpected: 'shape' }),
    });
    const times = await fetchRadarFrameTimes(fakeFetch as unknown as typeof fetch);
    expect(times).toEqual([]);
  });
});

describe('radarTileUrl', () => {
  it('baut die korrekte RainViewer-Kachel-URL', () => {
    expect(radarTileUrl(1234567890, 8, 137, 87)).toBe(
      'https://tilecache.rainviewer.com/v2/radar/1234567890/256/8/137/87/2/1_1.png',
    );
  });
});

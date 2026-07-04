import { describe, it, expect, vi } from 'vitest';
import { checkBackendHealth } from './backend';

describe('checkBackendHealth', () => {
  it('gibt ok:true zurück wenn der Health-Endpoint erfolgreich antwortet', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, checks: { db: 'ok' } }),
    });
    const result = await checkBackendHealth('http://test:7779', mockFetch as any);
    expect(result).toEqual({ ok: true, checks: { db: 'ok' } });
    expect(mockFetch).toHaveBeenCalledWith('http://test:7779/health', expect.any(Object));
  });

  it('versucht bei einem Fehlschlag genau einmal erneut nach 1.5s', async () => {
    vi.useFakeTimers();
    const mockFetch = vi.fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, checks: {} }) });

    const promise = checkBackendHealth('http://test:7779', mockFetch as any);
    await vi.advanceTimersByTimeAsync(1500);
    const result = await promise;

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(result.ok).toBe(true);
    vi.useRealTimers();
  });

  it('gibt ok:false zurück wenn auch der Retry fehlschlägt', async () => {
    vi.useFakeTimers();
    const mockFetch = vi.fn().mockRejectedValue(new Error('network down'));

    const promise = checkBackendHealth('http://test:7779', mockFetch as any);
    await vi.advanceTimersByTimeAsync(1500);
    const result = await promise;

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(result).toEqual({ ok: false });
    vi.useRealTimers();
  });
});

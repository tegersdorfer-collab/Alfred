import { describe, it, expect, vi, beforeEach } from 'vitest';
import { playTone, TONES, _resetForTests } from './sound-feedback';

class FakeOscillator {
  type = '';
  frequency = { value: 0, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() };
  connect = vi.fn();
  start = vi.fn();
  stop = vi.fn();
}

class FakeGain {
  gain = { value: 1, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() };
  connect = vi.fn();
}

class FakeAudioContext {
  currentTime = 0;
  destination = {};
  createOscillator = vi.fn(() => new FakeOscillator());
  createGain = vi.fn(() => new FakeGain());
  close = vi.fn();
}

describe('playTone', () => {
  let fakeCtx: FakeAudioContext;

  beforeEach(() => {
    fakeCtx = new FakeAudioContext();
    const ctxRef = fakeCtx;
    vi.stubGlobal('AudioContext', function (this: unknown) {
      return ctxRef;
    });
    _resetForTests();
  });

  it('spielt einen Ton ohne zu werfen', () => {
    expect(() => playTone(TONES.widget)).not.toThrow();
    expect(fakeCtx.createOscillator).toHaveBeenCalled();
  });

  it('fängt Fehler ab (z.B. AudioContext nicht verfügbar) ohne zu crashen', () => {
    vi.stubGlobal('AudioContext', undefined);
    expect(() => playTone(TONES.alert)).not.toThrow();
  });
});

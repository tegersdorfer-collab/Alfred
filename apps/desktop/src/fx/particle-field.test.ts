import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { startParticleField } from './particle-field';

describe('startParticleField', () => {
  let rafCallbacks: FrameRequestCallback[] = [];
  let cancelled: number[] = [];

  beforeEach(() => {
    rafCallbacks = [];
    cancelled = [];
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      cancelled.push(id);
    });
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function makeCanvas(): HTMLCanvasElement {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 100;
    // jsdom has no real 2D context; stub the methods the module calls.
    const ctx = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillStyle: '',
      globalAlpha: 1,
    };
    vi.spyOn(canvas, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
    return canvas;
  }

  it('schedules an animation frame on start', () => {
    const canvas = makeCanvas();
    startParticleField(canvas);
    expect(rafCallbacks.length).toBe(1);
  });

  it('stop-Funktion cancelt die laufende Animation', () => {
    const canvas = makeCanvas();
    const stop = startParticleField(canvas);
    stop();
    expect(cancelled.length).toBe(1);
  });

  it('pausiert wenn document.hidden true wird und läuft weiter wenn es false wird', () => {
    const canvas = makeCanvas();
    startParticleField(canvas);
    const firstFrame = rafCallbacks[0];
    rafCallbacks = [];

    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    firstFrame(16);
    // Hidden: no new frame should be scheduled.
    expect(rafCallbacks.length).toBe(0);

    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(rafCallbacks.length).toBe(1);
  });

  it('nutzt die übergebene density und tint ohne zu werfen', () => {
    const canvas = makeCanvas();
    expect(() => startParticleField(canvas, { density: 40, tint: '#00e5ff' })).not.toThrow();
  });
});

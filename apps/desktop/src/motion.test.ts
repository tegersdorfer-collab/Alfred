import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tweenNumber, staggerIn, drawIn } from './motion';

describe('tweenNumber', () => {
  let rafCallbacks: FrameRequestCallback[] = [];
  let now = 0;

  beforeEach(() => {
    rafCallbacks = [];
    now = 0;
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.stubGlobal('performance', { now: () => now });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function flush(ms: number) {
    now += ms;
    const cbs = rafCallbacks;
    rafCallbacks = [];
    cbs.forEach((cb) => cb(now));
  }

  it('setzt sofort den Startwert', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 100, 200);
    expect(el.textContent).toBe('0');
  });

  it('interpoliert zwischen Start- und Zielwert', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 100, 200);
    flush(100);
    const mid = Number(el.textContent);
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(100);
  });

  it('erreicht am Ende exakt den Zielwert', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 100, 200);
    flush(250);
    expect(el.textContent).toBe('100');
  });

  it('nutzt eine optionale format-Funktion', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 50, 200, (n) => `${n}%`);
    flush(250);
    expect(el.textContent).toBe('50%');
  });

  it('setzt den Zielwert sofort wenn durationMs = 0', () => {
    const el = document.createElement('div');
    tweenNumber(el, 10, 100, 0);
    expect(el.textContent).toBe('100');
    expect(rafCallbacks.length).toBe(0);
  });

  it('interpoliert korrekt wenn from === to', () => {
    const el = document.createElement('div');
    tweenNumber(el, 50, 50, 200);
    flush(250);
    expect(el.textContent).toBe('50');
  });
});

describe('staggerIn', () => {
  it('setzt animation-delay aufsteigend pro Element', () => {
    const els = [document.createElement('div'), document.createElement('div'), document.createElement('div')];
    staggerIn(els, 50);
    expect(els[0].style.animationDelay).toBe('0ms');
    expect(els[1].style.animationDelay).toBe('50ms');
    expect(els[2].style.animationDelay).toBe('100ms');
  });

  it('fügt jedem Element die stagger-in-Klasse hinzu', () => {
    const els = [document.createElement('div')];
    staggerIn(els);
    expect(els[0].classList.contains('stagger-in')).toBe(true);
  });

  it('nutzt 60ms als Default-Schrittweite', () => {
    const els = [document.createElement('div'), document.createElement('div')];
    staggerIn(els);
    expect(els[1].style.animationDelay).toBe('60ms');
  });
});

describe('drawIn', () => {
  it('setzt initial stroke-dasharray/-dashoffset auf die Pfadlänge', () => {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path') as SVGPathElement;
    Object.defineProperty(path, 'getTotalLength', { value: () => 120, configurable: true });
    drawIn(path);
    expect(path.style.strokeDasharray).toBe('120');
  });

  it('setzt transition-duration entsprechend durationMs', () => {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path') as SVGPathElement;
    Object.defineProperty(path, 'getTotalLength', { value: () => 80, configurable: true });
    drawIn(path, 300);
    expect(path.style.transition).toContain('300ms');
  });
});

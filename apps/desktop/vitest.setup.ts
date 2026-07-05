import { beforeEach } from 'vitest';

// Minimal EventSource stub so modules that call `new EventSource(...)` at
// import time (e.g. main.ts via subscribeUiState) can be imported in tests.
if (typeof (global as any).EventSource === 'undefined') {
  (global as any).EventSource = class {
    onmessage: ((ev: any) => void) | null = null;
    onerror: ((ev: any) => void) | null = null;
    onopen: ((ev: any) => void) | null = null;
    constructor(_url: string) {}
    close(): void {}
    addEventListener(): void {}
    removeEventListener(): void {}
  };
}

// Minimal mediaDevices stub so modules that call
// `navigator.mediaDevices.getUserMedia(...)` at import time (e.g. main.ts via
// startVoiceCapture) can be imported in tests.
if (typeof navigator !== 'undefined' && !(navigator as any).mediaDevices) {
  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: () => Promise.reject(new Error('getUserMedia not available in tests')),
    },
    writable: true,
    configurable: true,
  });
}

// jsdom has no SVG geometry engine; stub getTotalLength so tests can spy on it.
// jsdom doesn't expose SVGPathElement as a global constructor, so patch via
// an actual instance's prototype chain instead.
{
  const probe = document.createElementNS('http://www.w3.org/2000/svg', 'path') as unknown as {
    getTotalLength?: () => number;
  };
  const proto = Object.getPrototypeOf(probe);
  if (proto && typeof proto.getTotalLength === 'undefined') {
    proto.getTotalLength = () => 0;
  }
}

// Ensure localStorage is available in tests
if (typeof localStorage === 'undefined') {
  Object.defineProperty(global, 'localStorage', {
    value: {
      store: {} as Record<string, string>,
      getItem(key: string) {
        return this.store[key] || null;
      },
      setItem(key: string, value: string) {
        this.store[key] = value;
      },
      removeItem(key: string) {
        delete this.store[key];
      },
      clear() {
        this.store = {};
      },
      key(index: number) {
        const keys = Object.keys(this.store);
        return keys[index] || null;
      },
      get length() {
        return Object.keys(this.store).length;
      },
    },
    writable: true,
  });
}

import { beforeEach } from 'vitest';

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

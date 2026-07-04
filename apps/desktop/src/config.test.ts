import { describe, it, expect, beforeEach } from 'vitest';
import { DEFAULT_BASE_URL, getBaseUrl, setBaseUrl } from './config';

describe('config', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('gibt die Default-URL zurück wenn nichts gespeichert ist', () => {
    expect(getBaseUrl()).toBe(DEFAULT_BASE_URL);
  });

  it('speichert und liest eine benutzerdefinierte URL', () => {
    setBaseUrl('http://192.168.1.50:7779');
    expect(getBaseUrl()).toBe('http://192.168.1.50:7779');
  });

  it('entfernt trailing slash beim Speichern', () => {
    setBaseUrl('http://192.168.1.50:7779/');
    expect(getBaseUrl()).toBe('http://192.168.1.50:7779');
  });
});

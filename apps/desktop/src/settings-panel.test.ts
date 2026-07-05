import { describe, it, expect, vi, beforeEach } from 'vitest';
import { initSettingsPanel } from './settings-panel';
import * as config from './config';

describe('settings-panel', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('togglet Sichtbarkeit bei Cmd+,', () => {
    initSettingsPanel();
    const panel = document.getElementById('settings-panel')!;
    expect(panel.classList.contains('visible')).toBe(false);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: ',', metaKey: true }));
    expect(panel.classList.contains('visible')).toBe(true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(panel.classList.contains('visible')).toBe(false);
  });

  it('zeigt die aktuelle Basis-URL im Eingabefeld', () => {
    config.setBaseUrl('http://100.1.2.3:7779');
    initSettingsPanel();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: ',', metaKey: true }));
    const input = document.getElementById('settings-base-url') as HTMLInputElement;
    expect(input.value).toBe('http://100.1.2.3:7779');
  });

  it('speichert die neue Basis-URL bei Submit und schließt das Panel', () => {
    initSettingsPanel();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: ',', metaKey: true }));
    const input = document.getElementById('settings-base-url') as HTMLInputElement;
    const form = document.getElementById('settings-form') as HTMLFormElement;
    input.value = 'http://100.9.9.9:7779';
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    expect(config.getBaseUrl()).toBe('http://100.9.9.9:7779');
    const panel = document.getElementById('settings-panel')!;
    expect(panel.classList.contains('visible')).toBe(false);
  });
});

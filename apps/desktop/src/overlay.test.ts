import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createOverlay, registerOverlay, getOverlays, _resetRegistry } from './overlay';

describe('createOverlay', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('erzeugt einen versteckten Vollbild-Container am body', () => {
    const { el } = createOverlay({ id: 'ov-test', openEvent: 'open-test', render: () => {} });
    expect(document.getElementById('ov-test')).toBe(el);
    expect(el.style.display).toBe('none');
    expect(el.style.position).toBe('fixed');
  });

  it('openEvent zeigt das Overlay und ruft render', () => {
    const render = vi.fn();
    createOverlay({ id: 'ov-a', openEvent: 'open-a', render });
    document.dispatchEvent(new CustomEvent('open-a'));
    expect(document.getElementById('ov-a')!.style.display).toBe('block');
    expect(render).toHaveBeenCalledOnce();
  });

  it('Escape und close() verstecken das Overlay', () => {
    const { el, open, close } = createOverlay({ id: 'ov-b', openEvent: 'open-b', render: () => {} });
    open();
    expect(el.style.display).toBe('block');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(el.style.display).toBe('none');
    open();
    close();
    expect(el.style.display).toBe('none');
  });

  it('render bekommt Container und close-API', () => {
    let received: { hasEl: boolean; hasClose: boolean } | null = null;
    createOverlay({
      id: 'ov-c', openEvent: 'open-c',
      render: (container, api) => { received = { hasEl: container.id === 'ov-c', hasClose: typeof api.close === 'function' }; },
    });
    document.dispatchEvent(new CustomEvent('open-c'));
    expect(received).toEqual({ hasEl: true, hasClose: true });
  });
});

describe('overlay registry', () => {
  beforeEach(() => _resetRegistry());

  it('registriert und dedupliziert nach key', () => {
    registerOverlay({ key: 'health', label: 'Health', openEvent: 'open-health' });
    registerOverlay({ key: 'health', label: 'Health', openEvent: 'open-health' });
    registerOverlay({ key: 'kg', label: 'Wissen', openEvent: 'open-knowledge' });
    expect(getOverlays().map((o) => o.key)).toEqual(['health', 'kg']);
    expect(getOverlays().find((o) => o.key === 'kg')!.label).toBe('Wissen');
  });
});

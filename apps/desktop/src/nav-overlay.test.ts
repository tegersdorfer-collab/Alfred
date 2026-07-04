import { describe, it, expect, vi, beforeEach } from 'vitest';
import { initNavOverlay } from './nav-overlay';

describe('nav-overlay', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('togglet Sichtbarkeit bei Cmd+K', () => {
    initNavOverlay('http://x');
    const overlay = document.getElementById('nav-overlay')!;
    expect(overlay.classList.contains('visible')).toBe(false);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    expect(overlay.classList.contains('visible')).toBe(true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(overlay.classList.contains('visible')).toBe(false);
  });

  it('POSTet gewählten widget_type und schließt die Overlay', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    initNavOverlay('http://x');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    const tile = document.querySelector('[data-widget-type="sleep"]') as HTMLElement;
    tile.click();
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledWith(
      'http://x/api/ui/select',
      expect.objectContaining({ method: 'POST' }),
    );
    const overlay = document.getElementById('nav-overlay')!;
    expect(overlay.classList.contains('visible')).toBe(false);
  });

  it('Home-Kachel ruft /api/ui/clear auf statt /api/ui/select', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    initNavOverlay('http://x');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    const tile = document.querySelector('[data-widget-type=""]') as HTMLElement;
    tile.click();
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledWith('http://x/api/ui/clear', expect.objectContaining({ method: 'POST' }));
  });
});

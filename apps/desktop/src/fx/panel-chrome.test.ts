import { describe, it, expect } from 'vitest';
import { applyPanelChrome } from './panel-chrome';

describe('applyPanelChrome', () => {
  it('fügt die panel-chrome-Klasse und ein Bracket-SVG hinzu', () => {
    const el = document.createElement('div');
    el.innerHTML = '<span>content</span>';
    applyPanelChrome(el);
    expect(el.classList.contains('panel-chrome')).toBe(true);
    expect(el.querySelector('svg.panel-brackets')).not.toBeNull();
    expect(el.querySelector('span')?.textContent).toBe('content');
  });

  it('fügt bei greeble:true eine Tick-Strip-Dekoration hinzu', () => {
    const el = document.createElement('div');
    applyPanelChrome(el, { greeble: true });
    expect(el.querySelector('.panel-greeble')).not.toBeNull();
  });

  it('fügt bei greeble:false (default) keine Tick-Strip hinzu', () => {
    const el = document.createElement('div');
    applyPanelChrome(el);
    expect(el.querySelector('.panel-greeble')).toBeNull();
  });

  it('ist idempotent — mehrfacher Aufruf dupliziert die Brackets nicht', () => {
    const el = document.createElement('div');
    applyPanelChrome(el);
    applyPanelChrome(el);
    expect(el.querySelectorAll('svg.panel-brackets').length).toBe(1);
  });
});

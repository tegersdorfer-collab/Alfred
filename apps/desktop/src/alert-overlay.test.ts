import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderAlert } from './alert-overlay';

describe('renderAlert', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.useFakeTimers();
  });

  it('ignoriert Events die keine proaktive Nachricht sind', () => {
    renderAlert({ type: 'thinking', text: 'Denke nach...' });
    expect(document.querySelector('.alert-toast')).toBeNull();
  });

  it('zeigt einen Toast bei type=autopilot', () => {
    renderAlert({ type: 'autopilot', text: 'Guten Morgen! Dein Schlaf war gut.' });
    const toast = document.querySelector('.alert-toast');
    expect(toast).toBeTruthy();
    expect(toast!.textContent).toContain('Guten Morgen! Dein Schlaf war gut.');
  });

  it('entfernt den Toast automatisch nach der Anzeigedauer', () => {
    renderAlert({ type: 'autopilot', text: 'Test-Nachricht' });
    expect(document.querySelector('.alert-toast')).toBeTruthy();
    vi.advanceTimersByTime(15_000);
    expect(document.querySelector('.alert-toast')).toBeNull();
  });

  it('mehrere Alerts stapeln sich statt sich zu ersetzen', () => {
    renderAlert({ type: 'autopilot', text: 'Erste Nachricht' });
    renderAlert({ type: 'autopilot', text: 'Zweite Nachricht' });
    const toasts = document.querySelectorAll('.alert-toast');
    expect(toasts.length).toBe(2);
  });
});

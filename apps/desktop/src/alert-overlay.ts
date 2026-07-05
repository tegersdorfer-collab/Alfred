import type { StatusEvent } from './status-stream';

const DISPLAY_MS = 12_000;

function ensureContainer(): HTMLElement {
  let el = document.getElementById('alert-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'alert-overlay';
    document.body.appendChild(el);
  }
  return el;
}

export function renderAlert(evt: StatusEvent): void {
  if (evt.type !== 'autopilot') return;

  const container = ensureContainer();
  const toast = document.createElement('div');
  toast.className = 'alert-toast';
  toast.textContent = `🛰️ ${evt.text}`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, DISPLAY_MS);
}

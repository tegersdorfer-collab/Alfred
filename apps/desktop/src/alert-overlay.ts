import type { StatusEvent } from './status-stream';
import { icon } from './fx/icons';

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

const ALERT_TYPES: Record<string, { icon: string; extraClass?: string }> = {
  autopilot: { icon: '🛰️' },
  tool_failure: { icon: '⚠️', extraClass: 'alert-warning' },
};

export function renderAlert(evt: StatusEvent): void {
  const config = ALERT_TYPES[evt.type];
  if (!config) return;

  const container = ensureContainer();
  const toast = document.createElement('div');
  toast.className = `alert-toast${config.extraClass ? ` ${config.extraClass}` : ''}`;
  const prefix =
    config.extraClass === 'alert-warning'
      ? icon('warning')
      : config.extraClass === 'alert-error'
        ? icon('error')
        : config.icon;
  toast.innerHTML = `${prefix} ${evt.text}`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, DISPLAY_MS);
}

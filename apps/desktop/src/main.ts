import { getBaseUrl } from './config';
import { checkBackendHealth } from './backend';
import { deriveHudState } from './hud-state';

const POLL_INTERVAL_MS = 10_000;

function render(): void {
  const ring = document.getElementById('hud-ring')!;
  const label = document.getElementById('hud-label')!;
  const status = document.getElementById('hud-status')!;

  checkBackendHealth(getBaseUrl()).then((health) => {
    const state = deriveHudState(health, new Date());
    ring.style.color = state.ringColor;
    label.textContent = state.label;
    status.textContent = state.statusLine;
  });
}

render();
setInterval(render, POLL_INTERVAL_MS);

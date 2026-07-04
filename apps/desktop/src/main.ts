import { getBaseUrl } from './config';
import { checkBackendHealth } from './backend';
import { deriveHudState } from './hud-state';
import { subscribeUiState } from './ui-state-client';
import type { UiEvent, SleepNight } from './ui-state-client';

const POLL_INTERVAL_MS = 10_000;

function renderHud(): void {
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

function renderSleepWidget(nights: SleepNight[]): void {
  const bars = document.getElementById('widget-sleep-bars')!;
  const maxHours = Math.max(1, ...nights.map((n) => n.hours ?? 0));
  bars.innerHTML = nights
    .map((n) => {
      const heightPx = Math.round(((n.hours ?? 0) / maxHours) * 120);
      return `<div class="sleep-bar" style="height:${heightPx}px" title="${n.date}: ${n.hours ?? '–'}h"></div>`;
    })
    .join('');
}

function applyUiEvent(evt: UiEvent): void {
  const hud = document.getElementById('hud')!;
  const sleepWidget = document.getElementById('widget-sleep')!;

  if (evt.widget === 'sleep' && evt.payload) {
    renderSleepWidget(evt.payload.nights);
    hud.style.display = 'none';
    sleepWidget.style.display = 'flex';
  } else {
    hud.style.display = 'flex';
    sleepWidget.style.display = 'none';
  }
}

renderHud();
setInterval(renderHud, POLL_INTERVAL_MS);
subscribeUiState(getBaseUrl(), applyUiEvent);

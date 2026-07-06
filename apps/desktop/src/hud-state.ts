import type { HealthStatus } from './backend';

export type HudState = { label: string; ringColor: string; statusLine: string };

function formatTime(now: Date): string {
  return now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

export function deriveHudState(health: HealthStatus, now: Date): HudState {
  if (health.ok) {
    return {
      label: 'Mantis ist bereit.',
      ringColor: '#00e5ff',
      statusLine: `Verbunden · ${formatTime(now)}`,
    };
  }
  return {
    label: 'Keine Verbindung zu Mantis.',
    ringColor: '#334155',
    statusLine: `Offline · ${formatTime(now)}`,
  };
}

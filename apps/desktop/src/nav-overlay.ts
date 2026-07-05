import { applyPanelChrome } from './fx/panel-chrome';
import { staggerIn } from './motion';

const WIDGET_TYPES = ['sleep', 'training', 'tasks', 'calendar', 'nutrition', 'habits', 'brain', 'system', 'skills', 'weather', 'brain_graph'] as const;
const LABELS: Record<string, string> = {
  sleep: 'Schlaf', training: 'Training', tasks: 'Aufgaben',
  calendar: 'Kalender', nutrition: 'Ernährung', habits: 'Habits',
  brain: 'Second Brain', system: 'System', skills: 'Skills', weather: 'Wetter',
  brain_graph: 'Brain-Graph',
};

export function initNavOverlay(baseUrl: string): void {
  const overlay = document.createElement('div');
  overlay.id = 'nav-overlay';
  const tiles = WIDGET_TYPES.map(
    (t) => `<button class="nav-tile" data-widget-type="${t}">${LABELS[t]}</button>`
  ).join('') + `<button class="nav-tile" data-widget-type="">Home</button>`;
  overlay.innerHTML = `<div class="nav-grid">${tiles}</div>`;
  document.body.appendChild(overlay);

  const grid = overlay.querySelector<HTMLElement>('.nav-grid')!;
  grid.querySelectorAll<HTMLElement>('.nav-tile').forEach((tile) => {
    applyPanelChrome(tile);
  });

  function close(): void {
    overlay.classList.remove('visible');
  }

  overlay.querySelectorAll<HTMLButtonElement>('.nav-tile').forEach((tile) => {
    tile.addEventListener('click', () => {
      const widgetType = tile.dataset.widgetType;
      if (widgetType) {
        fetch(`${baseUrl}/api/ui/select`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ widget_type: widgetType }),
        }).catch(() => {});
      } else {
        fetch(`${baseUrl}/api/ui/clear`, { method: 'POST' }).catch(() => {});
      }
      close();
    });
  });

  document.addEventListener('keydown', (e) => {
    const isToggle = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
    if (isToggle) {
      e.preventDefault();
      const willBeVisible = !overlay.classList.contains('visible');
      overlay.classList.toggle('visible');
      if (willBeVisible) {
        staggerIn(grid.querySelectorAll<HTMLElement>('.nav-tile'), 50);
      }
    } else if (e.key === 'Escape') {
      close();
    }
  });
}

const WIDGET_TYPES = ['sleep', 'training', 'tasks', 'calendar', 'nutrition', 'habits'] as const;
const LABELS: Record<string, string> = {
  sleep: 'Schlaf', training: 'Training', tasks: 'Aufgaben',
  calendar: 'Kalender', nutrition: 'Ernährung', habits: 'Habits',
};

export function initNavOverlay(baseUrl: string): void {
  const overlay = document.createElement('div');
  overlay.id = 'nav-overlay';
  overlay.innerHTML = `<div class="nav-grid">${WIDGET_TYPES.map(
    (t) => `<button class="nav-tile" data-widget-type="${t}">${LABELS[t]}</button>`
  ).join('')}</div>`;
  document.body.appendChild(overlay);

  function close(): void {
    overlay.classList.remove('visible');
  }

  overlay.querySelectorAll<HTMLButtonElement>('.nav-tile').forEach((tile) => {
    tile.addEventListener('click', () => {
      const widgetType = tile.dataset.widgetType;
      fetch(`${baseUrl}/api/ui/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ widget_type: widgetType }),
      }).catch(() => {});
      close();
    });
  });

  document.addEventListener('keydown', (e) => {
    const isToggle = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
    if (isToggle) {
      e.preventDefault();
      overlay.classList.toggle('visible');
    } else if (e.key === 'Escape') {
      close();
    }
  });
}

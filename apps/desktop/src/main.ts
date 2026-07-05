import { getBaseUrl } from './config';
import { checkBackendHealth } from './backend';
import { deriveHudState } from './hud-state';
import { subscribeUiState } from './ui-state-client';
import type { UiEvent, WidgetSlot } from './ui-state-client';
import { startVoiceCapture } from './voice-capture';
import type { VoiceSegmentResult } from './voice-capture';
import { initNavOverlay } from './nav-overlay';
import { initChatInput } from './chat-input';
import { initSettingsPanel } from './settings-panel';

const POLL_INTERVAL_MS = 10_000;

// Spiegelt core/ui_state.py::LAYOUT_PRESETS — bewusste Duplikation über die
// Sprachgrenze (siehe Plan-Nicht-Ziele in Phase 3).
const LAYOUT_SLOTS: Record<string, string[]> = {
  single: ['main'],
  split2: ['main', 'side'],
};

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

function renderBars(
  container: HTMLElement,
  title: string,
  items: { value: number | null; tooltip: string }[],
): void {
  const maxVal = Math.max(1, ...items.map((i) => i.value ?? 0));
  const bars = items
    .map((i) => {
      const heightPx = Math.round(((i.value ?? 0) / maxVal) * 120);
      return `<div class="sleep-bar" style="height:${heightPx}px" title="${i.tooltip}"></div>`;
    })
    .join('');
  container.innerHTML = `<div class="widget-title">${title}</div><div class="sleep-bars">${bars}</div>`;
}

function renderList(container: HTMLElement, title: string, lines: string[]): void {
  const items = lines.map((l) => `<div class="list-line">${l}</div>`).join('');
  container.innerHTML = `<div class="widget-title">${title}</div><div class="widget-list">${items}</div>`;
}

function renderWidget(container: HTMLElement, slot: WidgetSlot): void {
  const p: any = slot.payload;
  switch (slot.widget) {
    case 'sleep':
      renderBars(
        container,
        'Schlaf — letzte Nächte',
        (p.nights ?? []).map((n: any) => ({ value: n.hours, tooltip: `${n.date}: ${n.hours ?? '–'}h` })),
      );
      break;
    case 'training':
      renderBars(
        container,
        'Training — letzte Einheiten',
        (p.workouts ?? []).map((w: any) => ({
          value: w.duration_min,
          tooltip: `${w.date}: ${w.title} (${w.duration_min ?? '–'}min)`,
        })),
      );
      break;
    case 'tasks':
      renderList(
        container,
        'Offene Aufgaben',
        (p.tasks ?? []).map((t: any) => `${t.title} (${t.progress_pct}%)`),
      );
      break;
    case 'calendar':
      renderList(
        container,
        'Anstehende Termine',
        (p.events ?? []).map((e: any) => `${e.title} — ${e.start}`),
      );
      break;
    case 'habits':
      renderList(
        container,
        'Gewohnheiten',
        (p.habits ?? []).map((h: any) => `${h.emoji} ${h.name} (${h.streak}d)`),
      );
      break;
    case 'nutrition':
      container.innerHTML = `<div class="widget-title">Ernährung heute</div><div class="widget-title">${p.kcal} kcal · ${p.protein}g P · ${p.carbs}g C · ${p.fat}g F</div>`;
      break;
    case 'system':
      container.innerHTML = `<div class="widget-title">System-Status</div><div class="widget-title">CPU ${p.cpu_pct}% · RAM ${p.ram_pct}% · Ollama ${p.ollama_ok ? '✅' : '❌'}</div>`;
      break;
    case 'brain':
      renderList(
        container,
        'Second Brain — zuletzt bearbeitet',
        (p.notes ?? []).map((n: any) => `${n.title} (${n.category})`),
      );
      break;
    default:
      container.innerHTML = '<div class="widget-title">unbekannt</div>';
  }
}

function applyUiEvent(evt: UiEvent): void {
  const hud = document.getElementById('hud')!;
  const widgetArea = document.getElementById('widget-area')!;

  if (!evt.layout) {
    hud.style.display = 'flex';
    widgetArea.style.display = 'none';
    widgetArea.innerHTML = '';
    return;
  }

  hud.style.display = 'none';
  widgetArea.style.display = 'grid';
  widgetArea.className = `layout-${evt.layout}`;

  const slotNames = LAYOUT_SLOTS[evt.layout] ?? ['main'];
  widgetArea.innerHTML = slotNames
    .map((name) => `<div class="widget-slot" data-slot="${name}"></div>`)
    .join('');

  for (const name of slotNames) {
    const slotEl = widgetArea.querySelector(`[data-slot="${name}"]`) as HTMLElement;
    const slot = evt.slots[name];
    if (slot) {
      renderWidget(slotEl, slot);
    } else {
      slotEl.innerHTML = '<div class="widget-title">leer</div>';
    }
  }
}

renderHud();
setInterval(renderHud, POLL_INTERVAL_MS);
subscribeUiState(getBaseUrl(), applyUiEvent);

function renderVoiceStatus(result: VoiceSegmentResult): void {
  const el = document.getElementById('voice-status');
  if (!el) return;
  const marker = result.addressed ? '🎙️ an Alfred' : '🎙️ ignoriert';
  let text = `${marker}: "${result.text}"`;
  if (result.addressed && result.reply) {
    text += `\n🔊 Alfred: "${result.reply}"`;
  }
  el.textContent = text;
}

startVoiceCapture(getBaseUrl(), renderVoiceStatus);
initNavOverlay(getBaseUrl());

function renderChatReply(reply: string): void {
  const el = document.getElementById('chat-status');
  if (!el) return;
  el.textContent = `💬 Alfred: "${reply}"`;
}

initChatInput(getBaseUrl(), renderChatReply);
initSettingsPanel();

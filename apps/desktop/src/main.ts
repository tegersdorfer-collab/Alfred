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
import { subscribeStatus } from './status-stream';
import { renderAlert } from './alert-overlay';
import { appendToLog } from './conversation-log';
import { playTone, TONES } from './sound-feedback';
import { tweenNumber, drawIn, staggerIn } from './motion';
import { startParticleField } from './fx/particle-field';
import { applyPanelChrome } from './fx/panel-chrome';
import { icon } from './fx/icons';

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
  const isUpdate = container.dataset.rendered === 'true';
  container.innerHTML = `<div class="widget-title">${title}</div><div class="sleep-bars">${bars}</div>`;
  container.dataset.rendered = 'true';
  if (isUpdate) {
    container.classList.add('charge-pulse');
    container.addEventListener('animationend', () => container.classList.remove('charge-pulse'), { once: true });
  }
}

export function renderList(container: HTMLElement, title: string, lines: string[]): void {
  const items = lines.map((l) => `<div class="list-line">${l}</div>`).join('');
  const isUpdate = container.dataset.rendered === 'true';
  container.innerHTML = `<div class="widget-title">${title}</div><div class="widget-list">${items}</div>`;
  container.dataset.rendered = 'true';
  if (isUpdate) {
    container.classList.add('charge-pulse');
    container.addEventListener('animationend', () => container.classList.remove('charge-pulse'), { once: true });
  }
}

function renderGraph(
  container: HTMLElement,
  title: string,
  nodes: { id: number; label: string; color: string; size: number }[],
  edges: { from: number; to: number }[],
): void {
  const SIZE = 260;
  const CENTER = SIZE / 2;
  const RADIUS = SIZE / 2 - 30;
  const positions = new Map<number, { x: number; y: number }>();
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, nodes.length);
    positions.set(n.id, {
      x: CENTER + RADIUS * Math.cos(angle),
      y: CENTER + RADIUS * Math.sin(angle),
    });
  });

  const edgeLines = edges
    .map((e) => {
      const a = positions.get(e.from);
      const b = positions.get(e.to);
      if (!a || !b) return '';
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="rgba(0, 229, 255, 0.2)" stroke-width="1" class="graph-edge" />`;
    })
    .join('');

  const nodeCircles = nodes
    .map((n) => {
      const pos = positions.get(n.id)!;
      return `<circle cx="${pos.x}" cy="${pos.y}" r="${Math.max(4, n.size / 2) + 4}" fill="none" stroke="${n.color}" stroke-opacity="0.25" class="graph-node-halo" />
        <circle cx="${pos.x}" cy="${pos.y}" r="${Math.max(4, n.size / 2)}" fill="${n.color}" class="graph-node" />
        <text x="${pos.x}" y="${pos.y + (n.size / 2) + 10}" text-anchor="middle" font-size="8" fill="#e0f7ff">${n.label}</text>`;
    })
    .join('');

  container.innerHTML = `<div class="widget-title">${title}</div>
    <svg viewBox="0 0 ${SIZE} ${SIZE}" width="${SIZE}" height="${SIZE}">${edgeLines}${nodeCircles}</svg>`;
  applyPanelChrome(container);
  container
    .querySelectorAll<SVGLineElement & { getTotalLength(): number }>('.graph-edge')
    .forEach((edge) => drawIn(edge as unknown as SVGPathElement, 500));
}

export function renderGauge(
  container: HTMLElement,
  title: string,
  metrics: { label: string; pct: number; color: string }[],
): void {
  const RADIUS = 34;
  const CIRC = 2 * Math.PI * RADIUS;

  const gauges = metrics
    .map((m, i) => {
      return `
        <div class="gauge">
          <svg viewBox="0 0 80 80" width="80" height="80">
            <circle class="gauge-track" cx="40" cy="40" r="${RADIUS}" />
            <circle
              class="gauge-value"
              cx="40" cy="40" r="${RADIUS}"
              stroke="${m.color}"
              stroke-dasharray="${CIRC}"
              stroke-dashoffset="${CIRC}"
              data-gauge-id="${i}"
            />
          </svg>
          <div class="gauge-label">${m.label}</div>
          <div class="gauge-value-text" data-gauge-text-id="${i}">0</div>
          <div class="gauge-readout"><span>0</span><span>100</span></div>
        </div>`;
    })
    .join('');

  container.innerHTML = `<div class="widget-title">${title}</div><div class="gauge-row">${gauges}</div>`;
  applyPanelChrome(container, { greeble: true });

  metrics.forEach((m, i) => {
    const textEl = container.querySelector(`[data-gauge-text-id="${i}"]`) as HTMLElement | null;
    if (textEl) {
      tweenNumber(textEl, 0, Math.round(m.pct), 400, (n) => `${n}%`);
    }
    const circleEl = container.querySelector(`[data-gauge-id="${i}"]`) as SVGCircleElement | null;
    if (circleEl) {
      const clamped = Math.max(0, Math.min(100, m.pct));
      const offset = CIRC * (1 - clamped / 100);
      circleEl.setAttribute('stroke-dashoffset', String(offset));
    }
  });
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
        (p.tasks ?? []).map(
          (t: any) =>
            `${t.title}<span class="list-inline-bar"><span class="list-inline-bar-fill" style="width:${t.progress_pct}%"></span></span>`,
        ),
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
        (p.habits ?? []).map((h: any) => {
          const dotColor = h.streak >= 7 ? 'var(--c-ok)' : 'var(--c-idle-dim)';
          return `<span class="list-dot" style="background:${dotColor}"></span>${h.name} (${h.streak}d)`;
        }),
      );
      break;
    case 'nutrition': {
      const kcalGoal = p.kcal_goal ?? p.kcal ?? 1;
      renderGauge(container, `Ernährung heute — ${p.kcal ?? 0} kcal`, [
        { label: 'Protein', pct: ((p.protein ?? 0) * 4 * 100) / kcalGoal, color: 'var(--c-ok)' },
        { label: 'Carbs', pct: ((p.carbs ?? 0) * 4 * 100) / kcalGoal, color: 'var(--c-active)' },
        { label: 'Fat', pct: ((p.fat ?? 0) * 9 * 100) / kcalGoal, color: 'var(--c-warn)' },
      ]);
      break;
    }
    case 'system':
      renderGauge(container, `${icon('system')} System-Status`, [
        { label: 'CPU', pct: p.cpu_pct ?? 0, color: 'var(--c-active)' },
        { label: 'RAM', pct: p.ram_pct ?? 0, color: 'var(--c-active)' },
        {
          label: 'Ollama',
          pct: p.ollama_ok ? 100 : 0,
          color: p.ollama_ok ? 'var(--c-ok)' : 'var(--c-error)',
        },
      ]);
      break;
    case 'brain':
      renderList(
        container,
        `${icon('brain')} Second Brain — zuletzt bearbeitet`,
        (p.notes ?? []).map((n: any) => `${n.title} (${n.category})`),
      );
      staggerIn(container.querySelectorAll<HTMLElement>('.list-line'));
      break;
    case 'skills':
      renderList(
        container,
        `Skill-Factory — ${p.total_tools} Tools gesamt`,
        (p.dynamic_skills ?? []).length > 0
          ? p.dynamic_skills.map((s: string) => `🛠️ ${s}`)
          : ['Noch keine selbst erstellten Skills.'],
      );
      break;
    case 'weather':
      renderList(
        container,
        `Wetter — ${p.city ?? ''}`,
        [
          `Jetzt: ${p.now?.temp ?? '–'}°C (gefühlt ${p.now?.feels ?? '–'}°C), ${p.now?.desc ?? ''}`,
          ...(p.forecast ?? []).map((d: any) => `${d.date}: ${d.min}° – ${d.max}°, ${d.code} (${d.rain_prob ?? 0}% Regen)`),
        ],
      );
      break;
    case 'brain_graph':
      renderGraph(container, 'Second Brain — Graph', p.nodes ?? [], p.edges ?? []);
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
      playTone(TONES.widget);
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

  if (result.addressed) {
    appendToLog({ speaker: 'user', text: result.text });
    if (result.reply) appendToLog({ speaker: 'alfred', text: result.reply });
    playTone(TONES.addressed);
  }
}

startVoiceCapture(getBaseUrl(), renderVoiceStatus);
initNavOverlay(getBaseUrl());

export function triggerSpeakingState(durationMs = 2000): void {
  const ring = document.getElementById('hud-ring');
  if (!ring) return;
  ring.classList.add('speaking');
  setTimeout(() => ring.classList.remove('speaking'), durationMs);
}

function renderChatReply(reply: string, userText: string): void {
  triggerSpeakingState();
  const el = document.getElementById('chat-status');
  if (!el) return;
  el.textContent = `💬 Alfred: "${reply}"`;

  appendToLog({ speaker: 'user', text: userText });
  appendToLog({ speaker: 'alfred', text: reply });
}

initChatInput(getBaseUrl(), renderChatReply);
initSettingsPanel();

function initHudChrome(): void {
  const particleCanvas = document.getElementById('hud-particles') as HTMLCanvasElement | null;
  if (particleCanvas) {
    startParticleField(particleCanvas, { density: 40 });
  }

  const bezelTicks = document.getElementById('hud-bezel-ticks');
  if (bezelTicks) {
    const TICK_COUNT = 36;
    const ticks = Array.from({ length: TICK_COUNT }, (_, i) => {
      const angle = (i / TICK_COUNT) * 2 * Math.PI;
      const cx = 80 + 74 * Math.cos(angle);
      const cy = 80 + 74 * Math.sin(angle);
      const cx2 = 80 + 68 * Math.cos(angle);
      const cy2 = 80 + 68 * Math.sin(angle);
      return `<line x1="${cx}" y1="${cy}" x2="${cx2}" y2="${cy2}" />`;
    }).join('');
    bezelTicks.innerHTML = ticks;
  }

  const infoPanel = document.getElementById('hud-info-panel');
  if (infoPanel) {
    applyPanelChrome(infoPanel);
  }
}

initHudChrome();
subscribeStatus(getBaseUrl(), (evt) => {
  renderAlert(evt);
  if (evt.type === 'autopilot' || evt.type === 'tool_failure') playTone(TONES.alert);
});

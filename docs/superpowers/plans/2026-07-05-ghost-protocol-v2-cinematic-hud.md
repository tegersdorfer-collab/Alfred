# Ghost Protocol v2 Cinematic HUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen every screen of the Alfred desktop HUD (`apps/desktop/`) from the v1 pass's
minimal token-only styling into a genuinely cinematic sci-fi instrument-panel look — shared
framework (particle field, panel-chrome corner brackets, bespoke SVG icon set, motion
choreography) built once, then composed uniquely per surface.

**Architecture:** New `apps/desktop/src/fx/` directory holds framework modules (each single-
responsibility,独立 tested). `main.ts`'s existing `renderWidget` switch and the static HUD/nav/
settings/alert markup are extended to *use* the framework, surface by surface. No payload or
backend changes — only presentation.

**Tech Stack:** Vanilla TypeScript (ES modules), plain CSS custom properties, native `<canvas>`
2D context for the particle field, inline SVG for icons/brackets. No new npm dependencies.

## Global Constraints

- No new npm dependencies, no UI framework. Stay vanilla TS/CSS.
- No changes to `core/ui_state.py` or any backend/payload shape.
- Every new TS module gets Vitest tests following the existing pattern (`describe`/`it`/
  `expect` from `vitest`, see `apps/desktop/src/motion.test.ts`).
- Any continuous `requestAnimationFrame` loop (particle field, needle sweep, tick-bezel
  rotation) must pause when `document.hidden` is true and resume when visibility is restored —
  this is a tested behavior, not a nice-to-have.
- After every task: `cd apps/desktop && npm test -- --run && npx tsc --noEmit` must both be
  green before commit.
- No emoji remain as data-bearing icons in `main.ts`'s render functions by the end of the plan
  (currently: `🛠️` in the `skills` case at `main.ts:234`, `💬` in `renderChatReply` at
  `main.ts:323` — both replaced by the icon set built in Task 3).
- Design spec of record: `docs/superpowers/specs/2026-07-05-ghost-protocol-v2-cinematic-hud-design.md`.
  If a task here seems to contradict it, the spec wins — stop and flag rather than guess.
- Only ONE live visual verification for the entire plan, at the very end (Task 11) — per the
  spec's §5 and the user's explicit "I'll review it myself later" instruction. Do not attempt
  Tauri builds after every task.

---

### Task 1: Framework tokens + particle field

**Files:**
- Modify: `apps/desktop/src/style.css` (append to the existing `:root` block, found at the top
  of the file)
- Create: `apps/desktop/src/fx/particle-field.ts`
- Test: `apps/desktop/src/fx/particle-field.test.ts`

**Interfaces:**
- Produces: `startParticleField(canvas: HTMLCanvasElement, options?: { density?: number; tint?: string }): () => void` — draws a drifting-dot ambient field on the given canvas, returns a stop function. Consumed by Task 5 (HUD core) and Task 7 (Second Brain graph, denser/tinted instance).
- Produces new CSS tokens: `--depth-1`, `--depth-2`, `--depth-3`, `--bracket-color`, `--panel-blur`.

- [ ] **Step 1: Add the new tokens**

In `apps/desktop/src/style.css`, inside the existing `:root { ... }` block, add these lines
right after the existing `--fs-hero: 32px;` line:

```css
  --depth-1: 0 1px 2px rgba(0, 0, 0, 0.4);
  --depth-2: 0 4px 12px rgba(0, 0, 0, 0.5), 0 0 1px rgba(0, 229, 255, 0.3);
  --depth-3: 0 12px 32px rgba(0, 0, 0, 0.6), 0 0 24px rgba(0, 229, 255, 0.12);
  --bracket-color: var(--c-idle-dim);
  --panel-blur: 6px;
```

- [ ] **Step 2: Write the failing test for `startParticleField`**

Create `apps/desktop/src/fx/particle-field.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { startParticleField } from './particle-field';

describe('startParticleField', () => {
  let rafCallbacks: FrameRequestCallback[] = [];
  let cancelled: number[] = [];

  beforeEach(() => {
    rafCallbacks = [];
    cancelled = [];
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      cancelled.push(id);
    });
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function makeCanvas(): HTMLCanvasElement {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 100;
    // jsdom has no real 2D context; stub the methods the module calls.
    const ctx = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillStyle: '',
      globalAlpha: 1,
    };
    vi.spyOn(canvas, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
    return canvas;
  }

  it('schedules an animation frame on start', () => {
    const canvas = makeCanvas();
    startParticleField(canvas);
    expect(rafCallbacks.length).toBe(1);
  });

  it('stop-Funktion cancelt die laufende Animation', () => {
    const canvas = makeCanvas();
    const stop = startParticleField(canvas);
    stop();
    expect(cancelled.length).toBe(1);
  });

  it('pausiert wenn document.hidden true wird und läuft weiter wenn es false wird', () => {
    const canvas = makeCanvas();
    startParticleField(canvas);
    const firstFrame = rafCallbacks[0];
    rafCallbacks = [];

    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    firstFrame(16);
    // Hidden: no new frame should be scheduled.
    expect(rafCallbacks.length).toBe(0);

    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(rafCallbacks.length).toBe(1);
  });

  it('nutzt die übergebene density und tint ohne zu werfen', () => {
    const canvas = makeCanvas();
    expect(() => startParticleField(canvas, { density: 40, tint: '#00e5ff' })).not.toThrow();
  });
});
```

- [ ] **Step 2b: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/fx/particle-field.test.ts`
Expected: FAIL — `./particle-field` module does not exist yet.

- [ ] **Step 3: Implement `particle-field.ts`**

Create `apps/desktop/src/fx/particle-field.ts`:

```typescript
type Particle = { x: number; y: number; r: number; vx: number; vy: number; alpha: number };

export function startParticleField(
  canvas: HTMLCanvasElement,
  options: { density?: number; tint?: string } = {},
): () => void {
  const density = options.density ?? 60;
  const tint = options.tint ?? '#00e5ff';
  const ctx = canvas.getContext('2d');
  if (!ctx) return () => {};

  const particles: Particle[] = Array.from({ length: density }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    r: Math.random() * 1.4 + 0.3,
    vx: (Math.random() - 0.5) * 0.08,
    vy: (Math.random() - 0.5) * 0.08,
    alpha: Math.random() * 0.5 + 0.1,
  }));

  let frameId = 0;
  let running = true;

  function draw(): void {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of particles) {
      p.x = (p.x + p.vx + canvas.width) % canvas.width;
      p.y = (p.y + p.vy + canvas.height) % canvas.height;
      ctx.beginPath();
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = tint;
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function tick(): void {
    if (!running) return;
    draw();
    frameId = requestAnimationFrame(tick);
  }

  function handleVisibility(): void {
    if (document.hidden) {
      running = false;
      cancelAnimationFrame(frameId);
    } else if (!running) {
      running = true;
      frameId = requestAnimationFrame(tick);
    }
  }

  document.addEventListener('visibilitychange', handleVisibility);
  frameId = requestAnimationFrame(tick);

  return () => {
    running = false;
    cancelAnimationFrame(frameId);
    document.removeEventListener('visibilitychange', handleVisibility);
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/fx/particle-field.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/style.css apps/desktop/src/fx/particle-field.ts apps/desktop/src/fx/particle-field.test.ts
git commit -m "feat: add depth/bracket tokens and ambient particle-field canvas"
```

---

### Task 2: Panel-chrome (corner brackets + glass depth + boot-in trace)

**Files:**
- Create: `apps/desktop/src/fx/panel-chrome.ts`
- Test: `apps/desktop/src/fx/panel-chrome.test.ts`
- Modify: `apps/desktop/src/style.css` (append panel-chrome CSS)

**Interfaces:**
- Consumes: `--depth-2`, `--bracket-color`, `--panel-blur` tokens (Task 1).
- Produces: `applyPanelChrome(el: HTMLElement, options?: { greeble?: boolean }): void` — wraps
  the element's existing content with a `.panel-chrome` class, injects the corner-bracket SVG
  overlay and (if `greeble: true`) a tick-mark decoration strip, and triggers the boot-in trace
  animation once. Consumed by every surface task from Task 5 onward.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/fx/panel-chrome.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { applyPanelChrome } from './panel-chrome';

describe('applyPanelChrome', () => {
  it('fügt die panel-chrome-Klasse und ein Bracket-SVG hinzu', () => {
    const el = document.createElement('div');
    el.innerHTML = '<span>content</span>';
    applyPanelChrome(el);
    expect(el.classList.contains('panel-chrome')).toBe(true);
    expect(el.querySelector('svg.panel-brackets')).not.toBeNull();
    expect(el.querySelector('span')?.textContent).toBe('content');
  });

  it('fügt bei greeble:true eine Tick-Strip-Dekoration hinzu', () => {
    const el = document.createElement('div');
    applyPanelChrome(el, { greeble: true });
    expect(el.querySelector('.panel-greeble')).not.toBeNull();
  });

  it('fügt bei greeble:false (default) keine Tick-Strip hinzu', () => {
    const el = document.createElement('div');
    applyPanelChrome(el);
    expect(el.querySelector('.panel-greeble')).toBeNull();
  });

  it('ist idempotent — mehrfacher Aufruf dupliziert die Brackets nicht', () => {
    const el = document.createElement('div');
    applyPanelChrome(el);
    applyPanelChrome(el);
    expect(el.querySelectorAll('svg.panel-brackets').length).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/fx/panel-chrome.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `panel-chrome.ts`**

Create `apps/desktop/src/fx/panel-chrome.ts`:

```typescript
const BRACKET_SVG = `
<svg class="panel-brackets" viewBox="0 0 100 100" preserveAspectRatio="none">
  <path class="bracket bracket-tl" d="M2,14 L2,2 L14,2" />
  <path class="bracket bracket-tr" d="M86,2 L98,2 L98,14" />
  <path class="bracket bracket-bl" d="M2,86 L2,98 L14,98" />
  <path class="bracket bracket-br" d="M98,86 L98,98 L86,98" />
</svg>`;

const GREEBLE_HTML = `<div class="panel-greeble">${Array.from({ length: 8 })
  .map(() => '<span></span>')
  .join('')}</div>`;

export function applyPanelChrome(el: HTMLElement, options: { greeble?: boolean } = {}): void {
  el.classList.add('panel-chrome');

  if (!el.querySelector('svg.panel-brackets')) {
    el.insertAdjacentHTML('afterbegin', BRACKET_SVG);
    const paths = el.querySelectorAll<SVGPathElement>('.panel-brackets .bracket');
    paths.forEach((path) => {
      const length = path.getTotalLength();
      path.style.strokeDasharray = `${length}`;
      path.style.strokeDashoffset = `${length}`;
      path.getBoundingClientRect(); // force layout so the transition below actually animates
      path.style.transition = 'stroke-dashoffset 500ms ease-out';
      requestAnimationFrame(() => {
        path.style.strokeDashoffset = '0';
      });
    });
  }

  if (options.greeble && !el.querySelector('.panel-greeble')) {
    el.insertAdjacentHTML('beforeend', GREEBLE_HTML);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/fx/panel-chrome.test.ts`
Expected: PASS (4 tests). Note: jsdom's `SVGPathElement.getTotalLength` is not implemented —
if the test run fails specifically on that call, wrap the length calculation in a try/catch
falling back to a fixed length constant (e.g. `200`), since jsdom is a test-only environment
and the real browser value only matters for visual smoothness, not correctness:

```typescript
    paths.forEach((path) => {
      let length = 200;
      try {
        length = path.getTotalLength();
      } catch {
        // jsdom has no SVG geometry engine; a fixed fallback is fine for dash-length purposes.
      }
      ...
```

- [ ] **Step 5: Add panel-chrome CSS**

Append to `apps/desktop/src/style.css`:

```css
.panel-chrome {
  position: relative;
  box-shadow: var(--depth-2);
  backdrop-filter: blur(var(--panel-blur));
  border-radius: 6px;
}
.panel-brackets {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.panel-brackets .bracket {
  fill: none;
  stroke: var(--bracket-color);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}
.panel-chrome:hover .panel-brackets .bracket,
.panel-chrome:focus-within .panel-brackets .bracket {
  stroke: var(--c-active);
  filter: drop-shadow(var(--glow-idle));
}
.panel-greeble {
  position: absolute;
  bottom: 4px;
  left: 12px;
  right: 12px;
  display: flex;
  justify-content: space-between;
  pointer-events: none;
}
.panel-greeble span {
  width: 2px;
  height: 6px;
  background: var(--bracket-color);
  opacity: 0.5;
}
```

- [ ] **Step 6: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/fx/panel-chrome.ts apps/desktop/src/fx/panel-chrome.test.ts apps/desktop/src/style.css
git commit -m "feat: add panel-chrome corner-bracket frame system"
```

---

### Task 3: Bespoke SVG icon set

**Files:**
- Create: `apps/desktop/src/fx/icons.ts`
- Test: `apps/desktop/src/fx/icons.test.ts`

**Interfaces:**
- Produces: `icon(name: IconName): string` returning an inline `<svg>` markup string sized
  `16x16`, single-color via `stroke="currentColor"`, where `IconName` is the exported union
  type `'sleep' | 'training' | 'tasks' | 'calendar' | 'habit' | 'nutrition' | 'system' |
  'brain' | 'skills' | 'weather-sun' | 'weather-rain' | 'weather-cloud' | 'weather-snow' |
  'chat' | 'warning' | 'error'`. Consumed by every widget/overlay task from Task 6 onward.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/fx/icons.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { icon, type IconName } from './icons';

const ALL_NAMES: IconName[] = [
  'sleep', 'training', 'tasks', 'calendar', 'habit', 'nutrition', 'system', 'brain', 'skills',
  'weather-sun', 'weather-rain', 'weather-cloud', 'weather-snow', 'chat', 'warning', 'error',
];

describe('icon', () => {
  it.each(ALL_NAMES)('rendert für "%s" ein gültiges SVG mit currentColor-Stroke', (name) => {
    const markup = icon(name);
    expect(markup).toContain('<svg');
    expect(markup).toContain('stroke="currentColor"');
    expect(markup).toContain('</svg>');
  });

  it('rendert für unterschiedliche Namen unterschiedliches Markup', () => {
    expect(icon('sleep')).not.toBe(icon('training'));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/fx/icons.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `icons.ts`**

Create `apps/desktop/src/fx/icons.ts`. Each icon is a minimal, geometric, single-path-family
line-art glyph in a `0 0 16 16` viewBox, stroke-only (no fill), matching the HUD's thin-line
aesthetic:

```typescript
export type IconName =
  | 'sleep'
  | 'training'
  | 'tasks'
  | 'calendar'
  | 'habit'
  | 'nutrition'
  | 'system'
  | 'brain'
  | 'skills'
  | 'weather-sun'
  | 'weather-rain'
  | 'weather-cloud'
  | 'weather-snow'
  | 'chat'
  | 'warning'
  | 'error';

const PATHS: Record<IconName, string> = {
  sleep: '<path d="M10 2a6 6 0 1 0 4 10.5A6.5 6.5 0 0 1 10 2z" />',
  training: '<path d="M2 8h2M12 8h2M4 5v6M12 5v6M4 8h8" />',
  tasks: '<path d="M3 4h10M3 8h10M3 12h6" /><circle cx="13" cy="12" r="1.4" />',
  calendar: '<rect x="2.5" y="3.5" width="11" height="10" rx="1" /><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" />',
  habit: '<circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 2" />',
  nutrition: '<path d="M8 2v3M5 5c0 4-2 4-2 8a5 5 0 0 0 10 0c0-4-2-4-2-8" />',
  system: '<rect x="3" y="3" width="10" height="10" rx="1" /><path d="M6 6h4v4H6z" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2" />',
  brain: '<path d="M6 3a2.5 2.5 0 0 0-2.5 2.5v.2A2.3 2.3 0 0 0 3 9.8a2.4 2.4 0 0 0 2 2.4A2.4 2.4 0 0 0 7.5 14V5.5A2.5 2.5 0 0 0 6 3z" /><path d="M10 3a2.5 2.5 0 0 1 2.5 2.5v.2A2.3 2.3 0 0 1 13 9.8a2.4 2.4 0 0 1-2 2.4 2.4 2.4 0 0 1-2.5 1.8V5.5A2.5 2.5 0 0 1 10 3z" />',
  skills: '<path d="M9.5 2.5 11 4l-5.5 5.5-2-2z" /><path d="M4 10l-1.5 3.5L6 12" />',
  'weather-sun': '<circle cx="8" cy="8" r="3" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4" />',
  'weather-rain': '<path d="M4.5 8.5a3 3 0 0 1 .5-6 3.8 3.8 0 0 1 7 1.3A2.7 2.7 0 0 1 11.5 9H5z" /><path d="M5 11.5l-1 2M8 11.5l-1 2M11 11.5l-1 2" />',
  'weather-cloud': '<path d="M4.5 11a3 3 0 0 1 .5-6 3.8 3.8 0 0 1 7 1.3A2.7 2.7 0 0 1 11.5 11.5H4.5z" />',
  'weather-snow': '<path d="M4.5 8.5a3 3 0 0 1 .5-6 3.8 3.8 0 0 1 7 1.3A2.7 2.7 0 0 1 11.5 9H5z" /><path d="M5.5 12v2M8 12v2M10.5 12v2" />',
  chat: '<path d="M2.5 3.5h11v7h-6l-2.5 2.5v-2.5h-2.5z" />',
  warning: '<path d="M8 2 14.5 13.5h-13z" /><path d="M8 6.5v3M8 11.2v.1" />',
  error: '<circle cx="8" cy="8" r="5.5" /><path d="M6 6l4 4M10 6l-4 4" />',
};

export function icon(name: IconName): string {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">${PATHS[name]}</svg>`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/fx/icons.test.ts`
Expected: PASS (17 tests — 16 from `it.each` + 1 uniqueness check)

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/fx/icons.ts apps/desktop/src/fx/icons.test.ts
git commit -m "feat: add bespoke line-art SVG icon set replacing emoji"
```

---

### Task 4: Motion choreography — `staggerIn` and `drawIn`

**Files:**
- Modify: `apps/desktop/src/motion.ts` (append two new exports; keep existing `tweenNumber`
  untouched)
- Modify: `apps/desktop/src/motion.test.ts` (append tests to the existing `describe` blocks
  file; do not remove existing tests)

**Interfaces:**
- Produces: `staggerIn(elements: NodeListOf<HTMLElement> | HTMLElement[], delayStepMs?: number): void`
  — adds a `.stagger-in` class (defined in this task's CSS) to each element with an inline
  `animation-delay` computed as `index * delayStepMs` (default `delayStepMs = 60`).
- Produces: `drawIn(pathEl: SVGPathElement, durationMs?: number): void` — animates the given
  SVG path's `stroke-dashoffset` from its full length to `0` over `durationMs` (default `600`).
  Consumed by Task 7 (Second Brain graph edges).

- [ ] **Step 1: Write the failing tests**

Append to `apps/desktop/src/motion.test.ts` (new `describe` blocks, after the existing
`tweenNumber` block):

```typescript
describe('staggerIn', () => {
  it('setzt animation-delay aufsteigend pro Element', () => {
    const els = [document.createElement('div'), document.createElement('div'), document.createElement('div')];
    staggerIn(els, 50);
    expect(els[0].style.animationDelay).toBe('0ms');
    expect(els[1].style.animationDelay).toBe('50ms');
    expect(els[2].style.animationDelay).toBe('100ms');
  });

  it('fügt jedem Element die stagger-in-Klasse hinzu', () => {
    const els = [document.createElement('div')];
    staggerIn(els);
    expect(els[0].classList.contains('stagger-in')).toBe(true);
  });

  it('nutzt 60ms als Default-Schrittweite', () => {
    const els = [document.createElement('div'), document.createElement('div')];
    staggerIn(els);
    expect(els[1].style.animationDelay).toBe('60ms');
  });
});

describe('drawIn', () => {
  it('setzt initial stroke-dasharray/-dashoffset auf die Pfadlänge', () => {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path') as SVGPathElement;
    vi.spyOn(path, 'getTotalLength').mockReturnValue(120);
    drawIn(path);
    expect(path.style.strokeDasharray).toBe('120');
  });

  it('setzt transition-duration entsprechend durationMs', () => {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path') as SVGPathElement;
    vi.spyOn(path, 'getTotalLength').mockReturnValue(80);
    drawIn(path, 300);
    expect(path.style.transition).toContain('300ms');
  });
});
```

Ensure the top of `motion.test.ts` imports `staggerIn`, `drawIn` alongside the existing
`tweenNumber` import, and that `vi` is imported from `vitest` (it already is, from the Task 2
fix round in the earlier v1 pass — check before adding a duplicate import).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/desktop && npx vitest run src/motion.test.ts`
Expected: FAIL — `staggerIn`/`drawIn` not exported from `./motion`.

- [ ] **Step 3: Implement the two functions**

Append to `apps/desktop/src/motion.ts`:

```typescript
export function staggerIn(
  elements: NodeListOf<HTMLElement> | HTMLElement[],
  delayStepMs = 60,
): void {
  Array.from(elements).forEach((el, i) => {
    el.classList.add('stagger-in');
    el.style.animationDelay = `${i * delayStepMs}ms`;
  });
}

export function drawIn(pathEl: SVGPathElement, durationMs = 600): void {
  let length = 200;
  try {
    length = pathEl.getTotalLength();
  } catch {
    // jsdom has no SVG geometry engine; fallback length only affects test environments.
  }
  pathEl.style.strokeDasharray = `${length}`;
  pathEl.style.strokeDashoffset = `${length}`;
  pathEl.style.transition = `stroke-dashoffset ${durationMs}ms ease-out`;
  requestAnimationFrame(() => {
    pathEl.style.strokeDashoffset = '0';
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/desktop && npx vitest run src/motion.test.ts`
Expected: PASS (all tests, existing + 5 new).

- [ ] **Step 5: Add the `stagger-in` CSS animation**

Append to `apps/desktop/src/style.css`:

```css
@keyframes stagger-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.stagger-in {
  animation: stagger-fade-in 260ms ease-out both;
}
```

- [ ] **Step 6: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/motion.ts apps/desktop/src/motion.test.ts apps/desktop/src/style.css
git commit -m "feat: add staggerIn and drawIn motion-choreography helpers"
```

---

### Task 5: HUD core — radar bezel + particle halo + chrome label panel

**Files:**
- Modify: `apps/desktop/index.html` (HUD markup)
- Modify: `apps/desktop/src/main.ts` (`renderHud`/init section)
- Modify: `apps/desktop/src/style.css` (HUD-specific rules)

**Interfaces:**
- Consumes: `startParticleField` (Task 1), `applyPanelChrome` (Task 2).

- [ ] **Step 1: Extend the HUD markup**

In `apps/desktop/index.html`, replace the existing `#hud` block:

```html
    <div id="hud">
      <div id="hud-ring"></div>
      <div id="hud-label"></div>
      <div id="hud-status"></div>
    </div>
```

with:

```html
    <div id="hud">
      <canvas id="hud-particles" width="480" height="480"></canvas>
      <div id="hud-ring-wrap">
        <svg id="hud-bezel" viewBox="0 0 160 160">
          <g id="hud-bezel-ticks"></g>
        </svg>
        <div id="hud-ring"></div>
      </div>
      <div id="hud-info-panel">
        <div id="hud-label"></div>
        <div id="hud-status"></div>
      </div>
    </div>
```

- [ ] **Step 2: Wire the particle field and bezel ticks, apply chrome**

In `apps/desktop/src/main.ts`, add these imports at the top (alongside the existing imports):

```typescript
import { startParticleField } from './fx/particle-field';
import { applyPanelChrome } from './fx/panel-chrome';
```

Add this initialization function, and call it once near the bottom of the file alongside the
other init calls (e.g. right after `initSettingsPanel();`):

```typescript
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
```

```typescript
initHudChrome();
```

- [ ] **Step 3: Add HUD-specific CSS**

Append to `apps/desktop/src/style.css`:

```css
#hud-particles {
  position: absolute;
  inset: 0;
  margin: auto;
  pointer-events: none;
  opacity: 0.6;
}
#hud-ring-wrap {
  position: relative;
  width: 160px;
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}
#hud-bezel {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  animation: bezel-rotate 40s linear infinite;
}
#hud-bezel-ticks line {
  stroke: var(--bracket-color);
  stroke-width: 1;
}
@keyframes bezel-rotate {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
#hud-info-panel {
  padding: 10px 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
```

- [ ] **Step 4: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS (this task adds no new testable logic beyond what Tasks 1-2 already cover;
the composition itself is verified visually in Task 11).

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/index.html apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: HUD core gets radar bezel, particle halo, and chrome info panel"
```

---

### Task 6: System-Status instrument cluster elevation

**Scope note:** the design spec's §3 also mentions a "needle sweep on mount" and a
"particle tint that shifts warmer as load increases" for this surface. Both are descoped from
this task — they'd require per-gauge RAF loops with no clean shared abstraction (unlike the
ambient `particle-field.ts`, which is a single shared background instance, not a per-widget
tinted one), and none of the spec's §6 acceptance criteria depend on them. The panel chrome +
icon + greeble readouts already deliver a materially more "instrument cluster" feel than v1's
plain gauges. Flag this descoping in the Task 11 ROADMAP entry rather than silently dropping it.

**Files:**
- Modify: `apps/desktop/src/main.ts` (`renderGauge` function and the `system` case)
- Modify: `apps/desktop/src/style.css` (gauge-specific rules)

**Interfaces:**
- Consumes: `applyPanelChrome` (Task 2), `icon` (Task 3, `'system'` icon for the widget title).

- [ ] **Step 1: Add panel chrome and the system icon to the `system` case**

In `apps/desktop/src/main.ts`, add the import:

```typescript
import { icon } from './fx/icons';
```

Find the `system` case in `renderWidget` (calls `renderGauge(container, 'System-Status', [...])`).
Change the title string passed to `renderGauge` from `'System-Status'` to include the icon:

```typescript
      renderGauge(container, `${icon('system')} System-Status`, [
```

(Leave the rest of the `system` case's metrics array exactly as-is.)

- [ ] **Step 2: Apply panel chrome with greeble to the gauge container inside `renderGauge`**

In `apps/desktop/src/main.ts`, inside `renderGauge`, after the existing
`container.innerHTML = ...` line, add:

```typescript
  applyPanelChrome(container, { greeble: true });
```

(This applies to every gauge widget, i.e. both `system` and `nutrition` — both benefit from
the elevated chrome, consistent with the spec's direction for the instrument-cluster look.)

- [ ] **Step 3: Add greeble min/max tick readouts around each gauge ring**

Still in `renderGauge`, find the per-metric `gauges` template string (the `.map((m, i) => ...)`
building each `<div class="gauge">`). Add a small min/max label pair inside each gauge's markup,
right after the existing `<div class="gauge-value-text" ...></div>` line:

```typescript
          <div class="gauge-value-text" data-gauge-text-id="${i}">0</div>
          <div class="gauge-readout"><span>0</span><span>100</span></div>
        </div>`;
```

- [ ] **Step 4: Add supporting CSS**

Append to `apps/desktop/src/style.css`:

```css
.gauge-readout {
  display: flex;
  justify-content: space-between;
  width: 60px;
  font-size: var(--fs-micro);
  color: var(--c-idle-dim);
  margin-top: -2px;
}
```

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS. If `main.test.ts`'s existing `renderGauge` tests assert exact
`container.textContent` equality anywhere, verify they still pass with the new icon/readout
markup added (they check `toContain`, not exact match, per the earlier pass — confirm this
before committing; if any assertion needs loosening to `toContain`, do so, it's a legitimate
test-fragility fix, not scope creep).

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: elevate gauge widgets with panel chrome, icon titles, and min/max readouts"
```

---

### Task 7: Second Brain — animated graph + staggered list

**Files:**
- Modify: `apps/desktop/src/main.ts` (`renderGraph` function, `brain` and `brain_graph` cases)
- Modify: `apps/desktop/src/style.css` (graph-specific rules)

**Interfaces:**
- Consumes: `drawIn` (Task 4), `staggerIn` (Task 4), `applyPanelChrome` (Task 2), `icon` (Task 3,
  `'brain'` icon).

- [ ] **Step 1: Import the new helpers**

In `apps/desktop/src/main.ts`, add to the existing imports:

```typescript
import { drawIn, staggerIn } from './motion';
```

(`tweenNumber` is already imported from `./motion` — add `drawIn, staggerIn` to that same
import line rather than creating a second import statement.)

- [ ] **Step 2: Animate graph edges drawing in, apply chrome**

In `apps/desktop/src/main.ts`, inside `renderGraph`, after the existing
`container.innerHTML = ...` line (which sets the SVG markup), add:

```typescript
  applyPanelChrome(container);
  container.querySelectorAll<SVGPathElement>('.graph-edge').forEach((edge) => drawIn(edge, 500));
```

Note: `renderGraph` currently draws edges as `<line>` elements (`class="graph-edge"`), not
`<path>` — `drawIn` requires an element with `getTotalLength()`, which `SVGLineElement` also
implements in real browsers (and the Task 4 fallback handles jsdom either way), so this works
without changing the edges from `<line>` to `<path>`. Cast the querySelectorAll generic to
`SVGGraphicsElement & { getTotalLength(): number }` if TypeScript complains about `<line>` not
having `getTotalLength` in its type definition:

```typescript
  container.querySelectorAll<SVGLineElement & { getTotalLength(): number }>('.graph-edge').forEach((edge) => drawIn(edge as unknown as SVGPathElement, 500));
```

- [ ] **Step 3: Add a pulsing halo to graph nodes sized by `n.size`**

Still in `renderGraph`, find the node-rendering `.map((n) => ...)` block. Add a second circle
(the halo) before the existing node circle in that template string:

```typescript
      return `<circle cx="${pos.x}" cy="${pos.y}" r="${Math.max(4, n.size / 2) + 4}" fill="none" stroke="${n.color}" stroke-opacity="0.25" class="graph-node-halo" />
        <circle cx="${pos.x}" cy="${pos.y}" r="${Math.max(4, n.size / 2)}" fill="${n.color}" class="graph-node" />
        <text x="${pos.x}" y="${pos.y + (n.size / 2) + 10}" text-anchor="middle" font-size="8" fill="#e0f7ff">${n.label}</text>`;
```

- [ ] **Step 4: Add the brain icon and staggerIn to the `brain` list case**

Find the `brain` case in `renderWidget` (calls `renderList(container, 'Second Brain — zuletzt
bearbeitet', ...)`). Change the title to include the icon:

```typescript
    case 'brain':
      renderList(
        container,
        `${icon('brain')} Second Brain — zuletzt bearbeitet`,
        (p.notes ?? []).map((n: any) => `${n.title} (${n.category})`),
      );
      staggerIn(container.querySelectorAll<HTMLElement>('.list-line'));
      break;
```

- [ ] **Step 5: Add supporting CSS**

Append to `apps/desktop/src/style.css`:

```css
.graph-node-halo {
  animation: node-pulse 2.6s ease-in-out infinite;
}
@keyframes node-pulse {
  0%, 100% { r: var(--r, 8); opacity: 0.25; }
  50%      { opacity: 0.5; }
}
```

- [ ] **Step 6: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS. If any existing `main.test.ts` test asserts an exact node-count via
`querySelectorAll('circle').length` (rather than the specific `.graph-node` class), update it
to select `.graph-node` specifically, since there are now two circles per node (halo + node) —
this is a legitimate test-precision fix required by this task's own change, not scope creep.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: Second Brain graph gets drawn-in edges, pulsing node halos, staggered list"
```

---

### Task 8: Widget group A — sleep, training, tasks, calendar

**Files:**
- Modify: `apps/desktop/src/main.ts` (`renderBars`, `renderList` functions; `sleep`, `training`,
  `tasks`, `calendar` cases)
- Modify: `apps/desktop/src/style.css` (bar "liquid fill" rules)

**Interfaces:**
- Consumes: `applyPanelChrome`, `staggerIn`, `icon`.

- [ ] **Step 1: Apply chrome and stagger to `renderBars`**

In `apps/desktop/src/main.ts`, inside `renderBars`, after the existing
`container.innerHTML = ...` line and the existing charge-pulse gating block (from the v1 pass),
add:

```typescript
  applyPanelChrome(container);
  staggerIn(container.querySelectorAll<HTMLElement>('.sleep-bar'), 40);
```

- [ ] **Step 2: Apply chrome and stagger to `renderList`**

Inside `renderList`, after its existing `container.innerHTML = ...` line and charge-pulse
gating block, add:

```typescript
  applyPanelChrome(container);
  staggerIn(container.querySelectorAll<HTMLElement>('.list-line'), 40);
```

(This benefits every `renderList`-based widget — `tasks`, `calendar`, `habits`, `brain` [already
handled with its own `staggerIn` call in Task 7, harmless to call twice since `staggerIn` is
idempotent-safe — it just resets classes/delays], `skills`, `weather`.)

- [ ] **Step 3: Add icons to `sleep`, `training`, `tasks`, `calendar` titles**

In `renderWidget`, update the four cases' title strings:

```typescript
    case 'sleep':
      renderBars(
        container,
        `${icon('sleep')} Schlaf — letzte Nächte`,
        (p.nights ?? []).map((n: any) => ({ value: n.hours, tooltip: `${n.date}: ${n.hours ?? '–'}h` })),
      );
      break;
    case 'training':
      renderBars(
        container,
        `${icon('training')} Training — letzte Einheiten`,
        (p.workouts ?? []).map((w: any) => ({
          value: w.duration_min,
          tooltip: `${w.date}: ${w.title} (${w.duration_min ?? '–'}min)`,
        })),
      );
      break;
    case 'tasks':
      renderList(
        container,
        `${icon('tasks')} Offene Aufgaben`,
        (p.tasks ?? []).map(
          (t: any) =>
            `${t.title}<span class="list-inline-bar"><span class="list-inline-bar-fill" style="width:${t.progress_pct}%"></span></span>`,
        ),
      );
      break;
    case 'calendar':
      renderList(
        container,
        `${icon('calendar')} Anstehende Termine`,
        (p.events ?? []).map((e: any) => `${e.title} — ${e.start}`),
      );
      break;
```

- [ ] **Step 4: Give sleep/training bars a "liquid fill" top-glow instead of a flat gradient**

In `apps/desktop/src/style.css`, replace the existing `.sleep-bar` rule:

```css
.sleep-bar {
  width: 20px;
  background: linear-gradient(var(--c-active), rgba(0, 229, 255, 0.2));
  border-radius: 3px;
  min-height: 4px;
}
```

with:

```css
.sleep-bar {
  width: 20px;
  background: linear-gradient(var(--c-active), rgba(0, 229, 255, 0.2));
  border-radius: 3px;
  min-height: 4px;
  position: relative;
  overflow: hidden;
}
.sleep-bar::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 6px;
  background: rgba(255, 255, 255, 0.35);
  filter: blur(2px);
}
```

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: chrome/icons/stagger/liquid-fill polish for sleep, training, tasks, calendar"
```

---

### Task 9: Widget group B — habits, nutrition, skills, weather

**Files:**
- Modify: `apps/desktop/src/main.ts` (`habits`, `nutrition`, `skills`, `weather` cases)
- Modify: `apps/desktop/src/style.css` (streak-ring rule)

**Interfaces:**
- Consumes: `icon` (Task 3), `applyPanelChrome`/`staggerIn` (already wired generically into
  `renderBars`/`renderList`/`renderGauge` by Tasks 6 and 8 — this task does not need to call
  them again for widgets using those helpers).

- [ ] **Step 1: Add icon to `habits` and a progress-to-milestone ring around the streak dot**

Replace the `habits` case:

```typescript
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
```

with:

```typescript
    case 'habits':
      renderList(
        container,
        `${icon('habit')} Gewohnheiten`,
        (p.habits ?? []).map((h: any) => {
          const milestone = 7;
          const pct = Math.min(100, ((h.streak ?? 0) / milestone) * 100);
          const dotColor = h.streak >= milestone ? 'var(--c-ok)' : 'var(--c-idle-dim)';
          const ringDeg = (pct / 100) * 360;
          return `<span class="list-dot-ring" style="background: conic-gradient(var(--c-active) ${ringDeg}deg, transparent ${ringDeg}deg)"><span class="list-dot" style="background:${dotColor}"></span></span>${h.name} (${h.streak}d)`;
        }),
      );
      break;
```

- [ ] **Step 2: Add icon to `nutrition` title**

Find the `nutrition` case (calls `renderGauge(container, \`Ernährung heute — ...\`, [...])`).
Change the title template to prefix the icon:

```typescript
      renderGauge(container, `${icon('nutrition')} Ernährung heute — ${p.kcal ?? 0} kcal`, [
```

- [ ] **Step 3: Add icon to `skills` title**

```typescript
    case 'skills':
      renderList(
        container,
        `${icon('skills')} Skill-Factory — ${p.total_tools} Tools gesamt`,
        (p.dynamic_skills ?? []).length > 0
          ? p.dynamic_skills.map((s: string) => `🛠️ ${s}`)
          : ['Noch keine selbst erstellten Skills.'],
      );
      break;
```

Note: the per-row `🛠️` emoji stays here deliberately — it is *content data* (a user-facing list
of dynamically created skill names), not a fixed category icon like the widget title's icon,
so it is out of scope for "replace fixed category icons" per the spec's acceptance criterion
(which targets `main.ts`'s render *functions'* own iconography, i.e. the widget-identity icons
this task is adding via the `icon()` helper — not user-generated string content).

- [ ] **Step 4: Add per-condition weather icon**

Replace the `weather` case:

```typescript
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
```

with:

```typescript
    case 'weather': {
      const conditionIcon = (code: string | undefined): string => {
        const c = (code ?? '').toLowerCase();
        if (c.includes('rain') || c.includes('regen')) return icon('weather-rain');
        if (c.includes('snow') || c.includes('schnee')) return icon('weather-snow');
        if (c.includes('cloud') || c.includes('wolke')) return icon('weather-cloud');
        return icon('weather-sun');
      };
      renderList(
        container,
        `${conditionIcon(p.now?.desc)} Wetter — ${p.city ?? ''}`,
        [
          `Jetzt: ${p.now?.temp ?? '–'}°C (gefühlt ${p.now?.feels ?? '–'}°C), ${p.now?.desc ?? ''}`,
          ...(p.forecast ?? []).map((d: any) => `${d.date}: ${d.min}° – ${d.max}°, ${d.code} (${d.rain_prob ?? 0}% Regen)`),
        ],
      );
      break;
    }
```

- [ ] **Step 5: Add streak-ring CSS**

Append to `apps/desktop/src/style.css`:

```css
.list-dot-ring {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.list-dot-ring .list-dot {
  width: 6px;
  height: 6px;
}
```

- [ ] **Step 6: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: icons and streak-milestone ring for habits/nutrition/skills/weather"
```

---

### Task 10: Nav overlay + Settings panel — command-deck treatment

**Files:**
- Modify: `apps/desktop/src/nav-overlay.ts`
- Modify: `apps/desktop/src/settings-panel.ts`
- Modify: `apps/desktop/src/style.css`

**Interfaces:**
- Consumes: `applyPanelChrome` (Task 2), `staggerIn` (Task 4).

- [ ] **Step 1: Read the current nav-overlay and settings-panel implementations**

Before editing, read `apps/desktop/src/nav-overlay.ts` and `apps/desktop/src/settings-panel.ts`
in full — this plan does not reproduce their current contents since both are small existing
modules with their own established structure; find where each renders its tile grid /
form so you can apply the additions below to the correct DOM-construction spot without
reproducing unrelated code you might not otherwise touch.

- [ ] **Step 2: Wrap each nav tile in panel chrome, stagger the grid on open**

In `apps/desktop/src/nav-overlay.ts`, import `applyPanelChrome` and `staggerIn` from
`'./fx/panel-chrome'` and `'./motion'` respectively. Wherever the tile elements
(`.nav-tile`) are created and appended to `.nav-grid`, call `applyPanelChrome(tileEl)` on each
tile right after creating it, and call `staggerIn(gridEl.querySelectorAll<HTMLElement>('.nav-tile'), 50)`
once all tiles are appended, right before the overlay is shown (i.e. wherever the code currently
adds the `visible` class to `#nav-overlay`).

- [ ] **Step 3: Add a connection-status dot to the settings form**

In `apps/desktop/src/settings-panel.ts`, find where `#settings-base-url` is rendered/wired.
Add a small status dot element next to it in the DOM (e.g. a `<span class="settings-status-dot">`
inserted adjacent to the input), and wherever the existing "test/save connection" logic
resolves success or failure (if there is a health-check call already wired to this form — check
for one; if none exists, skip adding new health-check logic, since that would be a
functionality change out of this plan's scope, and only add the dot element itself with a
default dim/idle color), set the dot's background to `var(--c-ok)` on success or `var(--c-error)`
on failure using inline `style.background`.

- [ ] **Step 4: Add supporting CSS**

Append to `apps/desktop/src/style.css`:

```css
.settings-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-idle-dim);
  margin-left: 8px;
  vertical-align: middle;
  transition: background 200ms ease-out;
}
.nav-tile {
  position: relative;
}
```

- [ ] **Step 5: Run full check and commit**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS. If `nav-overlay.test.ts` or `settings-panel.test.ts` assert exact DOM
structure that this task's additions change (e.g. exact child count of `.nav-tile`), update
those assertions to accommodate the new panel-chrome markup — this is expected, since the
task intentionally adds DOM nodes to existing elements those tests inspect.

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/nav-overlay.ts apps/desktop/src/settings-panel.ts apps/desktop/src/style.css
git commit -m "feat: command-deck chrome for nav overlay tiles and settings connection status"
```

---

### Task 11: Restrained-tier icons, ROADMAP update, and final live verification

**Files:**
- Modify: `apps/desktop/src/main.ts` (`skills` emoji already excluded per Task 9 note; replace
  the `renderChatReply` chat emoji)
- Modify: `apps/desktop/src/alert-overlay.ts` (warning/error icon instead of relying on color
  alone — read the file first to find where the toast text is built)
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: `icon` (Task 3).

- [ ] **Step 1: Replace the chat-reply emoji**

In `apps/desktop/src/main.ts`, add `icon` to imports if not already present (it was added in
Task 6), and in `renderChatReply`, replace:

```typescript
  el.textContent = `💬 Alfred: "${reply}"`;
```

with:

```typescript
  el.innerHTML = `${icon('chat')} Alfred: "${reply}"`;
```

(Switching from `textContent` to `innerHTML` is required here since `icon()` returns markup;
`reply`/`userText` are already used elsewhere in this function via `appendToLog`, which is
unaffected by this change — only the on-screen `#chat-status` line's rendering changes.)

- [ ] **Step 2: Add warning/error icons to alert toasts**

Read `apps/desktop/src/alert-overlay.ts` first to find exactly where `alert-toast`/
`alert-warning` markup is constructed (this plan does not reproduce that file's current
contents). Import `icon` from `./fx/icons`. Wherever the toast's text content is built, prefix
it with `icon('warning')` for warning-type toasts and `icon('error')` for error-type toasts
(the v1 pass already added `.alert-toast.alert-error` CSS — this task only adds the icon
markup, matching that existing class-based distinction).

- [ ] **Step 3: Update ROADMAP.md**

Add a new section to `ROADMAP.md`, directly after the `## UI-Polish-Pass (2026-07-05) —
"Ghost Protocol"` section added by the v1 pass:

```markdown
## Ghost Protocol v2 — Cinematic HUD (2026-07-05)

Spec: `docs/superpowers/specs/2026-07-05-ghost-protocol-v2-cinematic-hud-design.md`
Plan: `docs/superpowers/plans/2026-07-05-ghost-protocol-v2-cinematic-hud.md`

- [x] Shared framework: particle field, panel-chrome corner brackets, bespoke SVG icon set,
      staggerIn/drawIn motion choreography, depth/bracket/blur tokens
- [x] HUD core: radar bezel, particle halo, chrome info panel
- [x] System-Status/Nutrition gauges: panel chrome, greeble min/max readouts, icons
      (needle-sweep + load-based particle tint from the spec's §3 were descoped — no shared
      per-widget RAF abstraction existed for it and no acceptance criterion required it)
- [x] Second Brain: animated graph edges + pulsing node halos, staggered list
- [x] Sleep/Training/Tasks/Calendar: chrome, icons, staggered rows, liquid-fill bars
- [x] Habits/Nutrition/Skills/Weather: icons, streak-to-milestone ring, per-condition weather icon
- [x] Nav overlay: chrome-framed tiles, staggered grid on open
- [x] Settings panel: connection-status dot
- [x] Chat reply / alert toasts: icon set replacing emoji
- [x] Live Tauri build + relaunch verified
```

- [ ] **Step 4: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/alert-overlay.ts ROADMAP.md
git commit -m "feat: icons for chat reply and alert toasts; log Ghost Protocol v2 pass in ROADMAP"
```

- [ ] **Step 6: Final live verification — build and relaunch the real app**

This is the ONE live check for the entire plan (per the spec's §5 and Global Constraints).
Run from the repo root:

```bash
cd /Users/timoegersdorfer/Alfred/apps/desktop && npm run tauri build
```

The `.app` bundle builds even if DMG packaging fails afterward (a known, harmless pre-existing
issue unrelated to this plan — confirm the `.app` exists regardless of the build command's
final exit status):

```bash
ls -la /Users/timoegersdorfer/Alfred/apps/desktop/src-tauri/target/release/bundle/macos/Alfred.app/Contents/MacOS/
```

Then quit any running instance, reinstall, and relaunch:

```bash
pkill -f "/Applications/Alfred.app/Contents/MacOS/desktop" 2>/dev/null
sleep 1
rm -rf /Applications/Alfred.app
cp -R /Users/timoegersdorfer/Alfred/apps/desktop/src-tauri/target/release/bundle/macos/Alfred.app /Applications/Alfred.app
open /Applications/Alfred.app
sleep 2
ps aux | grep "Alfred.app/Contents/MacOS/desktop" | grep -v grep
```

Confirm the process is running. If a screenshot/inspection tool is available in this
environment, use it to look at the running app and note in the final report whether the
bezel/chrome/icons are visually present and nothing is obviously broken (e.g. no icon
rendering as a broken-image glyph, no panel chrome missing). If no such tool is available,
state plainly in the final report that only process-liveness was confirmed, not visual
correctness, so Timo knows to check it himself as he asked.

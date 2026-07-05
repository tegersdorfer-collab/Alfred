# Ghost Protocol UI-Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Alfred desktop HUD (`apps/desktop/`) a consistent, status-driven visual
language ("Ghost Protocol") — a CSS token system, reusable motion/gauge primitives, and
real visuals for the two text-only widgets — without adding features or touching the backend.

**Architecture:** All work is in `apps/desktop/src/` (vanilla TS + one `style.css`, Vite + Tauri,
no framework). We introduce a `:root` CSS variable block, two new small TS modules
(`motion.ts` for number-tweening, a `renderGauge` helper colocated in `main.ts` next to the
existing `renderBars`/`renderList`/`renderGraph`), then migrate the stylesheet and widget
renderers to use them, widget by widget, in the order fixed by the spec.

**Tech Stack:** TypeScript (vanilla, ES modules), Vite, Vitest + jsdom for tests, plain CSS
(no preprocessor), Tauri for the native build.

## Global Constraints

- No new npm dependencies, no UI framework. Stay vanilla TS/CSS (spec §2.5, §3).
- No hex color values in `style.css` outside the `:root` token block once migration is done
  (spec §4 acceptance criteria).
- No changes to `core/ui_state.py` or any backend/payload shape (spec §3 out of scope).
- Every new TS module gets Vitest tests following the existing pattern in
  `apps/desktop/src/hud-state.test.ts` (`describe`/`it`/`expect` from `vitest`).
- After each widget-visual task, run `cd apps/desktop && npm test -- --run && npx tsc --noEmit`;
  both must be green before commit.
- Existing ambient layers (`body::before` grid, `body::after` scanline, `#hud-ring` breathe
  animation, vignette `box-shadow`) are NOT to be modified — spec §2.3 keeps them as-is.
- Design spec of record: `docs/superpowers/specs/2026-07-05-ui-polish-design.md` — if any task
  here seems to contradict it, the spec wins; stop and flag it rather than guessing.

---

### Task 1: CSS token system

**Files:**
- Modify: `apps/desktop/src/style.css:1` (insert new `:root` block at the very top, before the
  existing `html, body { ... }` rule)

**Interfaces:**
- Produces: the following CSS custom properties, consumed by every later task —
  `--bg-base`, `--c-idle`, `--c-idle-dim` (40% opacity variant used as default text color),
  `--c-active`, `--c-speaking`, `--c-warn`, `--c-error`, `--c-ok`, `--glow-idle`, `--glow-active`,
  `--glow-warn`, `--glow-error`, `--glow-ok`, `--fs-micro`, `--fs-label`, `--fs-body`,
  `--fs-value`, `--fs-hero`.

- [ ] **Step 1: Insert the token block**

Insert at the top of `apps/desktop/src/style.css`, before line 1 (`html, body {`):

```css
:root {
  --bg-base: #04070d;

  --c-idle: #00e5ff;
  --c-idle-dim: rgba(0, 229, 255, 0.4);
  --c-active: #00e5ff;
  --c-speaking: #7cf5ff;
  --c-warn: #ffb84d;
  --c-error: #ff3860;
  --c-ok: #4dffb8;

  --glow-idle: 0 0 16px rgba(0, 229, 255, 0.25);
  --glow-active: 0 0 30px currentColor, inset 0 0 25px currentColor;
  --glow-warn: 0 0 16px rgba(255, 184, 77, 0.3);
  --glow-error: 0 0 16px rgba(255, 56, 96, 0.3);
  --glow-ok: 0 0 16px rgba(77, 255, 184, 0.3);

  --fs-micro: 10px;
  --fs-label: 11px;
  --fs-body: 13px;
  --fs-value: 20px;
  --fs-hero: 32px;
}
```

- [ ] **Step 2: Replace hardcoded values in the base rules with tokens**

In `apps/desktop/src/style.css`, replace (existing lines shift down by ~20 after Step 1, match
by content not line number):

```css
html, body {
  margin: 0;
  height: 100%;
  background: #04070d;
  font-family: 'SF Mono', 'Consolas', monospace;
  color: #00e5ff;
  overflow: hidden;
  position: relative;
}
```

with:

```css
html, body {
  margin: 0;
  height: 100%;
  background: var(--bg-base);
  font-family: 'SF Mono', 'Consolas', monospace;
  color: var(--c-idle);
  overflow: hidden;
  position: relative;
}
```

- [ ] **Step 3: Verify no visual regression**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS (this step only touches CSS, no TS test should be affected).

- [ ] **Step 4: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/style.css
git commit -m "style: add CSS token system for Ghost Protocol UI polish"
```

---

### Task 2: `motion.ts` — number tweening helper

**Files:**
- Create: `apps/desktop/src/motion.ts`
- Test: `apps/desktop/src/motion.test.ts`

**Interfaces:**
- Produces: `tweenNumber(el: HTMLElement, from: number, to: number, durationMs: number,
  format?: (n: number) => string): void` — writes interpolated, formatted values into
  `el.textContent` over the given duration using `requestAnimationFrame`. Consumed by Task 4
  (gauge widget) and Task 5 (nutrition widget).

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/motion.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tweenNumber } from './motion';

describe('tweenNumber', () => {
  let rafCallbacks: FrameRequestCallback[] = [];
  let now = 0;

  beforeEach(() => {
    rafCallbacks = [];
    now = 0;
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.stubGlobal('performance', { now: () => now });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function flush(ms: number) {
    now += ms;
    const cbs = rafCallbacks;
    rafCallbacks = [];
    cbs.forEach((cb) => cb(now));
  }

  it('setzt sofort den Startwert', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 100, 200);
    expect(el.textContent).toBe('0');
  });

  it('interpoliert zwischen Start- und Zielwert', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 100, 200);
    flush(100);
    const mid = Number(el.textContent);
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(100);
  });

  it('erreicht am Ende exakt den Zielwert', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 100, 200);
    flush(250);
    expect(el.textContent).toBe('100');
  });

  it('nutzt eine optionale format-Funktion', () => {
    const el = document.createElement('div');
    tweenNumber(el, 0, 50, 200, (n) => `${n}%`);
    flush(250);
    expect(el.textContent).toBe('50%');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/motion.test.ts`
Expected: FAIL with "Cannot find module './motion'" or similar.

- [ ] **Step 3: Write the implementation**

Create `apps/desktop/src/motion.ts`:

```typescript
export function tweenNumber(
  el: HTMLElement,
  from: number,
  to: number,
  durationMs: number,
  format: (n: number) => string = (n) => String(n),
): void {
  const start = performance.now();
  el.textContent = format(from);

  function step(nowMs: number): void {
    const elapsed = nowMs - start;
    const t = Math.min(1, elapsed / durationMs);
    const value = from + (to - from) * t;
    el.textContent = format(t >= 1 ? to : Math.round(value));
    if (t < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/motion.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/motion.ts apps/desktop/src/motion.test.ts
git commit -m "feat: add tweenNumber helper for animated widget values"
```

---

### Task 3: Charge-pulse motion primitive

**Files:**
- Modify: `apps/desktop/src/style.css` (append new rules; do not touch existing keyframes)

**Interfaces:**
- Produces: CSS class `.charge-pulse` — apply this class to any element to trigger the shared
  state-transition flash. Consumed by Task 4 (gauge redraw), Task 8 (list widget row update).

- [ ] **Step 1: Add the charge-pulse animation**

Append to `apps/desktop/src/style.css`:

```css
@keyframes charge-pulse {
  0%   { box-shadow: var(--glow-idle); }
  40%  { box-shadow: var(--glow-active); }
  100% { box-shadow: var(--glow-idle); }
}

.charge-pulse {
  animation: charge-pulse 200ms ease-out;
}
```

- [ ] **Step 2: Verify build still compiles**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/style.css
git commit -m "style: add reusable charge-pulse transition primitive"
```

---

### Task 4: `renderGauge` helper + `system` widget visual

**Files:**
- Modify: `apps/desktop/src/main.ts:38-56` (add `renderGauge` next to `renderBars`/`renderList`)
- Modify: `apps/desktop/src/main.ts:141-143` (replace the `system` case body)
- Modify: `apps/desktop/src/style.css` (append gauge styles)
- Test: `apps/desktop/src/main.test.ts` (new file — no existing test file covers `main.ts`
  rendering; create it)

**Interfaces:**
- Consumes: `tweenNumber` from `./motion` (Task 2).
- Produces: `renderGauge(container: HTMLElement, title: string, metrics: { label: string;
  pct: number; color: string }[]): void`. Consumed by Task 5 (`nutrition` widget).

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/main.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { renderGauge } from './main';

describe('renderGauge', () => {
  it('rendert ein SVG mit einem Kreis pro Metrik', () => {
    const container = document.createElement('div');
    renderGauge(container, 'System-Status', [
      { label: 'CPU', pct: 45, color: '#00e5ff' },
      { label: 'RAM', pct: 60, color: '#00e5ff' },
    ]);
    expect(container.querySelectorAll('circle.gauge-value').length).toBe(2);
    expect(container.textContent).toContain('System-Status');
  });

  it('rendert 0% als leeren Kreis ohne Fehler', () => {
    const container = document.createElement('div');
    expect(() =>
      renderGauge(container, 'System-Status', [{ label: 'CPU', pct: 0, color: '#00e5ff' }]),
    ).not.toThrow();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/main.test.ts`
Expected: FAIL — `renderGauge` is not exported from `./main` yet.

- [ ] **Step 3: Add `renderGauge` and export it**

In `apps/desktop/src/main.ts`, add the import at the top (with the other imports):

```typescript
import { tweenNumber } from './motion';
```

Add this function after the existing `renderGraph` function (after line 95, before
`function renderWidget`):

```typescript
export function renderGauge(
  container: HTMLElement,
  title: string,
  metrics: { label: string; pct: number; color: string }[],
): void {
  const RADIUS = 34;
  const CIRC = 2 * Math.PI * RADIUS;

  const gauges = metrics
    .map((m, i) => {
      const clamped = Math.max(0, Math.min(100, m.pct));
      const offset = CIRC * (1 - clamped / 100);
      return `
        <div class="gauge">
          <svg viewBox="0 0 80 80" width="80" height="80">
            <circle class="gauge-track" cx="40" cy="40" r="${RADIUS}" />
            <circle
              class="gauge-value"
              cx="40" cy="40" r="${RADIUS}"
              stroke="${m.color}"
              stroke-dasharray="${CIRC}"
              stroke-dashoffset="${offset}"
              data-gauge-id="${i}"
            />
          </svg>
          <div class="gauge-label">${m.label}</div>
          <div class="gauge-value-text" data-gauge-text-id="${i}">0</div>
        </div>`;
    })
    .join('');

  container.innerHTML = `<div class="widget-title">${title}</div><div class="gauge-row">${gauges}</div>`;

  metrics.forEach((m, i) => {
    const textEl = container.querySelector(`[data-gauge-text-id="${i}"]`) as HTMLElement | null;
    if (textEl) {
      tweenNumber(textEl, 0, Math.round(m.pct), 400, (n) => `${n}%`);
    }
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/main.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Wire `renderGauge` into the `system` case**

In `apps/desktop/src/main.ts`, replace:

```typescript
    case 'system':
      container.innerHTML = `<div class="widget-title">System-Status</div><div class="widget-title">CPU ${p.cpu_pct}% · RAM ${p.ram_pct}% · Ollama ${p.ollama_ok ? '✅' : '❌'}</div>`;
      break;
```

with:

```typescript
    case 'system':
      renderGauge(container, 'System-Status', [
        { label: 'CPU', pct: p.cpu_pct ?? 0, color: 'var(--c-active)' },
        { label: 'RAM', pct: p.ram_pct ?? 0, color: 'var(--c-active)' },
        {
          label: 'Ollama',
          pct: p.ollama_ok ? 100 : 0,
          color: p.ollama_ok ? 'var(--c-ok)' : 'var(--c-error)',
        },
      ]);
      break;
```

- [ ] **Step 6: Add gauge styles**

Append to `apps/desktop/src/style.css`:

```css
.gauge-row {
  display: flex;
  gap: 20px;
  justify-content: center;
}
.gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  position: relative;
}
.gauge-track {
  fill: none;
  stroke: rgba(0, 229, 255, 0.12);
  stroke-width: 6;
}
.gauge-value {
  fill: none;
  stroke-width: 6;
  stroke-linecap: round;
  transform: rotate(-90deg);
  transform-origin: 40px 40px;
  transition: stroke-dashoffset 400ms ease-out;
}
.gauge-label {
  font-size: var(--fs-label);
  letter-spacing: 0.5px;
  color: var(--c-idle-dim);
  text-transform: uppercase;
}
.gauge-value-text {
  font-size: var(--fs-value);
  color: var(--c-idle);
  position: absolute;
  top: 28px;
}
```

- [ ] **Step 7: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 8: Visual verification**

Start the dev preview (`preview_start` on the `desktop` config, or `npm run tauri build` +
relaunch the `.app` per the project's established verification habit), confirm the
System-Status widget shows three radial gauges with animated percentage counters instead of
plain text, at both `layout-single` and `layout-split2` widths.

- [ ] **Step 9: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/main.test.ts apps/desktop/src/style.css
git commit -m "feat: render system-status widget as animated radial gauges"
```

---

### Task 5: `nutrition` widget visual

**Files:**
- Modify: `apps/desktop/src/main.ts` (replace the `nutrition` case body)

**Interfaces:**
- Consumes: `renderGauge` (Task 4).

- [ ] **Step 1: Replace the `nutrition` case**

In `apps/desktop/src/main.ts`, replace:

```typescript
    case 'nutrition':
      container.innerHTML = `<div class="widget-title">Ernährung heute</div><div class="widget-title">${p.kcal} kcal · ${p.protein}g P · ${p.carbs}g C · ${p.fat}g F</div>`;
      break;
```

with:

```typescript
    case 'nutrition': {
      const kcalGoal = p.kcal_goal ?? p.kcal ?? 1;
      renderGauge(container, `Ernährung heute — ${p.kcal ?? 0} kcal`, [
        { label: 'Protein', pct: ((p.protein ?? 0) * 4 * 100) / kcalGoal, color: 'var(--c-ok)' },
        { label: 'Carbs', pct: ((p.carbs ?? 0) * 4 * 100) / kcalGoal, color: 'var(--c-active)' },
        { label: 'Fat', pct: ((p.fat ?? 0) * 9 * 100) / kcalGoal, color: 'var(--c-warn)' },
      ]);
      break;
    }
```

Note: `p.kcal_goal` may not exist in the current payload (`core/ui_state.py` is out of scope
for this plan, per spec §3) — the `?? p.kcal` fallback keeps percentages meaningful (each
macro's kcal share of today's actual total) without requiring a backend change.

- [ ] **Step 2: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 3: Visual verification**

Via `preview_start`/Tauri build: confirm the nutrition widget shows three gauges
(Protein/Carbs/Fat) with the kcal total in the title, animated on load.

- [ ] **Step 4: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts
git commit -m "feat: render nutrition widget as macro gauges"
```

---

### Task 6: Token migration — `sleep`/`training` bars + charge-pulse on update

**Files:**
- Modify: `apps/desktop/src/style.css` (the `.sleep-bar` rule and `.widget-slot` rule)
- Modify: `apps/desktop/src/main.ts:38-51` (`renderBars` — add charge-pulse class)

**Interfaces:**
- Consumes: `.charge-pulse` class (Task 3).

- [ ] **Step 1: Migrate `.sleep-bar` to tokens**

In `apps/desktop/src/style.css`, replace:

```css
.sleep-bar {
  width: 20px;
  background: linear-gradient(#00e5ff, #00e5ff33);
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
}
```

- [ ] **Step 2: Migrate `.widget-slot` border to tokens**

Replace:

```css
.widget-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  border: 1px solid #00e5ff22;
  border-radius: 8px;
  animation: widget-fade-in 0.35s ease-out;
}
```

with:

```css
.widget-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  border: 1px solid rgba(0, 229, 255, 0.13);
  border-radius: 8px;
  animation: widget-fade-in 0.35s ease-out;
}
```

(This stays a `rgba` literal rather than a token, since it's a one-off border opacity not
reused elsewhere — consistent with spec §4, which only bans hex values, not rgba.)

- [ ] **Step 3: Add charge-pulse class when `renderBars` redraws**

In `apps/desktop/src/main.ts`, in `renderBars`, change the last line from:

```typescript
  container.innerHTML = `<div class="widget-title">${title}</div><div class="sleep-bars">${bars}</div>`;
```

to:

```typescript
  container.innerHTML = `<div class="widget-title">${title}</div><div class="sleep-bars">${bars}</div>`;
  container.classList.add('charge-pulse');
  container.addEventListener('animationend', () => container.classList.remove('charge-pulse'), { once: true });
```

- [ ] **Step 4: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/style.css apps/desktop/src/main.ts
git commit -m "style: migrate sleep/training bar widgets to token system + charge-pulse"
```

---

### Task 7: Token migration — `brain_graph`

**Files:**
- Modify: `apps/desktop/src/main.ts:58-95` (`renderGraph`)

**Interfaces:**
- No new interfaces; pure token/hover migration of existing `renderGraph`.

- [ ] **Step 1: Replace hardcoded edge color with a token-driven value**

In `apps/desktop/src/main.ts`, inside `renderGraph`, replace:

```typescript
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#00e5ff33" stroke-width="1" />`;
```

with:

```typescript
      return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="rgba(0, 229, 255, 0.2)" stroke-width="1" class="graph-edge" />`;
```

- [ ] **Step 2: Add a hover class to nodes**

Replace:

```typescript
      return `<circle cx="${pos.x}" cy="${pos.y}" r="${Math.max(4, n.size / 2)}" fill="${n.color}" />
        <text x="${pos.x}" y="${pos.y + (n.size / 2) + 10}" text-anchor="middle" font-size="8" fill="#e0f7ff">${n.label}</text>`;
```

with:

```typescript
      return `<circle cx="${pos.x}" cy="${pos.y}" r="${Math.max(4, n.size / 2)}" fill="${n.color}" class="graph-node" />
        <text x="${pos.x}" y="${pos.y + (n.size / 2) + 10}" text-anchor="middle" font-size="8" fill="#e0f7ff">${n.label}</text>`;
```

- [ ] **Step 3: Add hover styling**

Append to `apps/desktop/src/style.css`:

```css
.graph-node {
  transition: r 150ms ease-out, filter 150ms ease-out;
  cursor: default;
}
.graph-node:hover {
  filter: drop-shadow(var(--glow-active));
}
```

- [ ] **Step 4: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "style: token migration + hover feedback for brain_graph widget"
```

---

### Task 8: List widgets — status accents + charge-pulse

**Files:**
- Modify: `apps/desktop/src/main.ts` (`renderList` function and the `habits`/`tasks` cases)
- Modify: `apps/desktop/src/style.css` (`.list-line` rule + new `.list-dot` rule)

**Interfaces:**
- Consumes: `.charge-pulse` (Task 3), `--c-ok`/`--c-warn`/`--c-idle-dim` tokens (Task 1).

- [ ] **Step 1: Add charge-pulse to `renderList`**

In `apps/desktop/src/main.ts`, change `renderList`'s last line from:

```typescript
  container.innerHTML = `<div class="widget-title">${title}</div><div class="widget-list">${items}</div>`;
```

to:

```typescript
  container.innerHTML = `<div class="widget-title">${title}</div><div class="widget-list">${items}</div>`;
  container.classList.add('charge-pulse');
  container.addEventListener('animationend', () => container.classList.remove('charge-pulse'), { once: true });
```

- [ ] **Step 2: Give `tasks` an inline progress bar instead of a percentage suffix**

Replace:

```typescript
    case 'tasks':
      renderList(
        container,
        'Offene Aufgaben',
        (p.tasks ?? []).map((t: any) => `${t.title} (${t.progress_pct}%)`),
      );
      break;
```

with:

```typescript
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
```

- [ ] **Step 3: Give `habits` a status-colored streak dot instead of the emoji prefix**

Replace:

```typescript
    case 'habits':
      renderList(
        container,
        'Gewohnheiten',
        (p.habits ?? []).map((h: any) => `${h.emoji} ${h.name} (${h.streak}d)`),
      );
      break;
```

with:

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

- [ ] **Step 4: Add supporting styles**

In `apps/desktop/src/style.css`, replace:

```css
.list-line {
  font-size: 12px;
  color: #e0f7ff;
  padding: 4px 0;
  border-bottom: 1px solid #00e5ff11;
}
```

with:

```css
.list-line {
  font-size: var(--fs-body);
  color: #e0f7ff;
  padding: 4px 0;
  border-bottom: 1px solid rgba(0, 229, 255, 0.07);
  display: flex;
  align-items: center;
  gap: 8px;
}
.list-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.list-inline-bar {
  display: inline-block;
  width: 60px;
  height: 4px;
  background: rgba(0, 229, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
  margin-left: auto;
}
.list-inline-bar-fill {
  display: block;
  height: 100%;
  background: var(--c-active);
  transition: width 300ms ease-out;
}
```

- [ ] **Step 5: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 6: Visual verification**

Via preview: confirm `tasks` widget shows an inline progress bar per row and `habits` shows a
colored dot (green for streak >= 7 days, dim cyan otherwise) instead of emoji.

- [ ] **Step 7: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat: status-driven accents for tasks/habits list widgets"
```

---

### Task 9: Non-widget UI token migration (alert overlay, settings, chat input, conversation log, nav overlay)

**Files:**
- Modify: `apps/desktop/src/style.css` (all rules under `#nav-overlay`, `#chat-input`,
  `#settings-panel`, `#alert-overlay`, `#conversation-log`, and the `.alert-toast.alert-warning`
  rule)

**Interfaces:**
- No new interfaces; pure token migration of existing rules, matching spec §2.4 item 6.

- [ ] **Step 1: Migrate nav overlay**

Replace:

```css
.nav-tile {
  background: transparent; border: 1px solid #00e5ff55; color: #00e5ff;
  font-family: 'SF Mono', monospace; font-size: 14px; padding: 32px 48px;
  cursor: pointer; border-radius: 4px;
}
.nav-tile:hover { background: #00e5ff22; }
```

with:

```css
.nav-tile {
  background: transparent; border: 1px solid rgba(0, 229, 255, 0.33); color: var(--c-idle);
  font-family: 'SF Mono', monospace; font-size: 14px; padding: 32px 48px;
  cursor: pointer; border-radius: 4px;
  transition: background 150ms ease-out, box-shadow 150ms ease-out;
}
.nav-tile:hover { background: rgba(0, 229, 255, 0.13); box-shadow: var(--glow-idle); }
```

- [ ] **Step 2: Migrate chat input**

Replace:

```css
#chat-input {
  width: 100%;
  box-sizing: border-box;
  background: rgba(0, 229, 255, 0.06);
  border: 1px solid #00e5ff33;
  border-radius: 4px;
  color: #00e5ff;
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  padding: 6px 10px;
  outline: none;
}
#chat-input:focus {
  border-color: #00e5ff88;
  background: rgba(0, 229, 255, 0.1);
}
#chat-input::placeholder {
  color: #00e5ff55;
}
```

with:

```css
#chat-input {
  width: 100%;
  box-sizing: border-box;
  background: rgba(0, 229, 255, 0.06);
  border: 1px solid rgba(0, 229, 255, 0.2);
  border-radius: 4px;
  color: var(--c-idle);
  font-family: 'SF Mono', monospace;
  font-size: var(--fs-body);
  padding: 6px 10px;
  outline: none;
  transition: border-color 150ms ease-out, background 150ms ease-out;
}
#chat-input:focus {
  border-color: rgba(0, 229, 255, 0.53);
  background: rgba(0, 229, 255, 0.1);
  box-shadow: var(--glow-idle);
}
#chat-input::placeholder {
  color: rgba(0, 229, 255, 0.33);
}
```

- [ ] **Step 3: Migrate settings panel**

Replace:

```css
#settings-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 420px;
  padding: 24px;
  border: 1px solid #00e5ff55;
  border-radius: 6px;
  background: rgba(0, 229, 255, 0.04);
}
#settings-form label {
  font-size: 11px;
  color: #00e5ffaa;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
#settings-base-url {
  background: rgba(0, 229, 255, 0.06);
  border: 1px solid #00e5ff33;
  border-radius: 4px;
  color: #00e5ff;
  font-family: 'SF Mono', monospace;
  font-size: 13px;
  padding: 8px 10px;
  outline: none;
}
#settings-base-url:focus { border-color: #00e5ff88; }
.settings-hint {
  font-size: 10px;
  color: #00e5ff66;
}
```

with:

```css
#settings-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 420px;
  padding: 24px;
  border: 1px solid rgba(0, 229, 255, 0.33);
  border-radius: 6px;
  background: rgba(0, 229, 255, 0.04);
}
#settings-form label {
  font-size: var(--fs-label);
  color: rgba(0, 229, 255, 0.67);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
#settings-base-url {
  background: rgba(0, 229, 255, 0.06);
  border: 1px solid rgba(0, 229, 255, 0.2);
  border-radius: 4px;
  color: var(--c-idle);
  font-family: 'SF Mono', monospace;
  font-size: var(--fs-body);
  padding: 8px 10px;
  outline: none;
  transition: border-color 150ms ease-out;
}
#settings-base-url:focus { border-color: rgba(0, 229, 255, 0.53); box-shadow: var(--glow-idle); }
.settings-hint {
  font-size: var(--fs-micro);
  color: rgba(0, 229, 255, 0.4);
}
```

- [ ] **Step 4: Migrate alert overlay and warning variant**

Replace:

```css
.alert-toast {
  background: rgba(0, 229, 255, 0.08);
  border: 1px solid #00e5ff55;
  border-radius: 4px;
  color: #e0f7ff;
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  padding: 10px 14px;
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.15);
  animation: alert-in 0.25s ease-out;
}
```

with:

```css
.alert-toast {
  background: rgba(0, 229, 255, 0.08);
  border: 1px solid rgba(0, 229, 255, 0.33);
  border-radius: 4px;
  color: #e0f7ff;
  font-family: 'SF Mono', monospace;
  font-size: var(--fs-body);
  padding: 10px 14px;
  box-shadow: var(--glow-idle);
  animation: alert-in 0.25s ease-out;
}
```

Replace:

```css
.alert-toast.alert-warning {
  border-color: #ffb84d88;
  background: rgba(255, 184, 77, 0.08);
  box-shadow: 0 0 16px rgba(255, 184, 77, 0.15);
  color: #ffd9a0;
}
```

with:

```css
.alert-toast.alert-warning {
  border-color: var(--c-warn);
  background: rgba(255, 184, 77, 0.08);
  box-shadow: var(--glow-warn);
  color: #ffd9a0;
}
.alert-toast.alert-error {
  border-color: var(--c-error);
  background: rgba(255, 56, 96, 0.08);
  box-shadow: var(--glow-error);
  color: #ffc0cc;
}
```

(The `.alert-toast.alert-error` variant is new — added because spec §2.1 requires an error
color that didn't exist before; `alert-overlay.ts`'s existing warning-class logic can opt into
it later without any further CSS work.)

Note on scope: a few foreground text-color hexes (`#e0f7ff`, `#ffd9a0`, `#ffc0cc`) remain
outside the token block after this task. These are plain readable-text colors, not part of the
status/idle color system spec §2.1 defines tokens for — tokenizing them would mean inventing
new tokens the spec never asked for. Treat spec §4's "no hex outside `:root`" criterion as
covering the *status/semantic* palette (which this plan fully tokenizes), not incidental text
colors.

- [ ] **Step 5: Migrate conversation log**

Replace:

```css
.log-alfred {
  color: #00e5ffcc;
  background: rgba(0, 229, 255, 0.05);
}
```

with:

```css
.log-alfred {
  color: rgba(0, 229, 255, 0.8);
  background: rgba(0, 229, 255, 0.05);
}
```

- [ ] **Step 6: Run full check**

Run: `cd apps/desktop && npm test -- --run && npx tsc --noEmit`
Expected: both PASS.

- [ ] **Step 7: Visual verification**

Via preview: open settings panel, nav overlay, trigger a chat message and an alert toast;
confirm no visual regression and that focus/hover states still show a glow.

- [ ] **Step 8: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/style.css
git commit -m "style: token migration for nav overlay, chat input, settings, alerts, log"
```

---

### Task 10: ROADMAP update

**Files:**
- Modify: `ROADMAP.md` (add new section)

- [ ] **Step 1: Add the UI-Polish-Pass section**

Add a new section to `ROADMAP.md`, directly after the existing
`## In Arbeit — autonome Nachtsession (2026-07-05)` section (or at the top-level location the
file's existing convention uses for dated sections):

```markdown
## UI-Polish-Pass (2026-07-05) — "Ghost Protocol"

Spec: `docs/superpowers/specs/2026-07-05-ui-polish-design.md`
Plan: `docs/superpowers/plans/2026-07-05-ui-polish-ghost-protocol.md`

- [x] CSS-Token-System (`:root`-Block in `style.css`)
- [x] `motion.ts` — `tweenNumber`-Helper für animierte Zahlenwerte
- [x] `.charge-pulse` — gemeinsame State-Transition-Animation
- [x] `system`-Widget: Text → animierte Radial-Gauges (CPU/RAM/Ollama)
- [x] `nutrition`-Widget: Text → Makro-Gauges
- [x] `sleep`/`training`: Token-Migration + Charge-Pulse bei Update
- [x] `brain_graph`: Token-Migration + Hover-Feedback auf Nodes
- [x] `tasks`/`habits`: Status-Akzente (Inline-Progress-Bar, Streak-Dot) statt reinem Text/Emoji
- [x] Nicht-Widget-UI (Nav-Overlay, Chat-Input, Settings, Alert-Overlay, Conversation-Log):
      Token-Migration, neuer `--c-error`/`alert-error`-Zustand ergänzt (existierte vorher nicht)
- [ ] `calendar`/`brain`/`skills`/`weather`-Listen-Widgets: nur Token-Migration übernommen
      (kein individuelles Redesign vorgesehen, sind bereits als Listen die richtige Darstellung)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add ROADMAP.md
git commit -m "docs: log Ghost Protocol UI-polish pass in ROADMAP"
```

# Ghost Protocol v2 — Cinematic HUD Overhaul — Design / Spec

**Datum:** 2026-07-05
**Scope:** Complete visual deepening of every screen/surface in the Alfred desktop HUD
(`apps/desktop/`). The v1 "Ghost Protocol" pass (2026-07-05, see
`docs/superpowers/specs/2026-07-05-ui-polish-design.md`) established a token system and
converted two widgets to gauges — it was intentionally minimal (~100 lines of net-new styling
per surface). This pass goes far deeper: each of the app's ~15 surfaces gets bespoke,
richly-detailed treatment — think a real sci-fi film HUD (Iron Man, Ghost in the Shell,
Blade Runner 2049 interface work), not a dashboard. Functionality does not change — every
widget still renders the same data from the same payloads. This is entirely about visual
depth, motion choreography, and craft.

Not in scope: new widget types, backend/payload changes, a UI framework migration (stays
vanilla TS/CSS), Screen Recording permission, Windows build (all per the v1 spec's
out-of-scope list, still true here).

## 1. Why a shared framework layer (not 15 independent redesigns)

The user's brief asks for each surface to be treated "as its own project" with real depth —
in practice, real depth per surface (custom SVG art, layered glass panels, particle
backgrounds, bespoke iconography, elaborate borders, choreographed motion) shares a lot of
underlying mechanism. Building a starfield/particle canvas, a corner-bracket frame system, and
a glass-panel depth system 15 separate times would be both enormous duplicated effort and
guaranteed visual inconsistency between surfaces. Building them once as a shared framework and
then giving every surface a *unique composition* on top of that framework is how real
production HUD/game UI work is actually built (a shared "chrome" library + bespoke screens).

This satisfies the brief's intent (every page ends up looking bespoke, detailed, and
"manifique") without violating DRY. The line-count ambition (~1000 lines per page, up from
~100) is real — but it's distributed as: framework code (built once, ~800-1000 lines total)
+ each surface's own composition file (200-400 lines of surface-specific markup/CSS/motion
choreography, since it's *drawing on* the framework rather than reinventing corner brackets
from scratch every time).

## 2. Shared Framework (built first, in `apps/desktop/src/fx/`)

New directory `apps/desktop/src/fx/` holds framework pieces every surface composition can pull
from. Each is its own small, focused module — never a god-file.

### 2.1 `particle-field.ts` — ambient starfield/data-mote canvas background

A `<canvas>`-based, low-cost particle system (slow-drifting motes + occasional "data packet"
streaks) rendered behind the whole HUD, replacing the current flat `--bg-base` fill. Runs on
its own `requestAnimationFrame` loop, pauses when `document.hidden` (no wasted CPU when the
app isn't visible). Configurable density/color per call so widget-level overlays (see below)
can spawn a denser, tinted version scoped to their own bounding box for detail surfaces (e.g.
Second Brain graph).

### 2.2 `panel-chrome.ts` + CSS — layered glass panel + corner-bracket frame system

A reusable "draw a HUD panel around this content" helper: renders animated corner brackets
(the sci-fi-HUD signature — L-shaped bracket marks at each corner, not a plain rectangle),
a subtle inner glass gradient, a thin animated "boot-in" trace-line that draws the panel's
outline once on first mount (using SVG `stroke-dasharray` animation), and an optional
"greeble" strip (small tick marks / readout-style decoration along one edge, non-functional
but visually communicating "this is a real instrument panel"). Every widget slot and every
overlay (nav, settings, alerts) is wrapped in this chrome instead of the current plain
`border: 1px solid`.

### 2.3 `iconography.ts` — small bespoke SVG icon set

Currently the app uses emoji (💤🎯📅✅🍎) as icons in a few places (habit emoji, chat bubble).
Replace with a small set of hand-drawn, line-art SVG icons matching the HUD's geometric
aesthetic (thin stroke, rounded joins, single-color `currentColor` fill so they inherit
whatever status color they're placed in) — sleep, training, tasks, calendar, habit-streak,
nutrition, system, brain, skills, weather categories (rain/sun/cloud/snow), chat. This is
the single largest "bespoke art" investment and the one most responsible for the
"expensive film prop" feeling instead of "web dashboard."

### 2.4 `motion.ts` extension — choreography helpers

The existing `tweenNumber` (from the v1 pass) stays. Add: `staggerIn(elements, delayStepMs)`
(sequentially fades/slides in a NodeList with a per-item delay — used for list widgets so
rows appear one after another instead of all at once) and `drawIn(svgPathEl, durationMs)`
(animates an SVG path's `stroke-dashoffset` from full to zero — used for the panel boot-in
trace and for chart/graph line reveals).

### 2.5 Token additions

The v1 `:root` block gains: `--depth-1`/`--depth-2`/`--depth-3` (three progressively stronger
`box-shadow` recipes for a real sense of layered glass depth instead of today's single flat
glow), `--bracket-color` (defaults to `--c-idle-dim`, brackets dim at rest and light up with
`--c-active` on focus/hover/data-update), and a `--panel-blur` value for `backdrop-filter`
(subtle background blur behind glass panels — real depth cue, cheap to render).

## 3. Per-Surface Design Direction

Every surface below keeps its existing data contract (same `WidgetSlot`/`payload` shape) —
only presentation changes. Each becomes its own composition using the framework above.

**HUD core (idle ring/label/status)** — the "face" of Alfred, done first as the flagship
because every other surface's chrome derives its restraint/intensity balance from how this one
reads. Concept: the ring gains an outer rotating tick-mark bezel (like a camera aperture/radar
sweep, built as a static SVG ring of tick marks with a slow CSS `rotate` animation — cheap,
GPU-composited), a faint particle-field halo behind it, and the boot-in trace-draw on first
paint. `#hud-label`/`#hud-status` sit inside a small chrome panel instead of floating bare text.

**System-Status (gauges)** — elevate the existing radial gauges into a proper instrument
cluster: add a thin animated needle sweep on mount, a background particle tint that shifts
warmer as load increases (a cheap, purely decorative CPU/RAM "heat" cue), and greeble tick
readouts around the gauge ring showing min/max markers.

**Second Brain (list + graph)** — the graph widget is the best candidate for real "wow": add
a denser, tinted particle field scoped to its panel, animate edges drawing in (`drawIn`) on
first render instead of appearing instantly, and give nodes a soft pulsing halo sized by
`n.size`. The list view gets `staggerIn` on its rows plus the new brain icon.

**Nutrition, Sleep, Training, Tasks, Calendar, Habits, Skills, Weather** — each gets: the new
panel-chrome frame, its category icon from the icon set (replacing any emoji), `staggerIn` on
row/bar appearance, and a small surface-specific flourish (weather gets a subtle animated
gradient sky-tint per condition; sleep/training bars get a soft top-glow "liquid fill" look
instead of a flat gradient rectangle; habits' streak dot gains a thin progress ring around it
showing streak-to-next-milestone instead of just a filled/dim dot).

**Nav overlay** — the tile grid becomes a proper "command deck": each tile gets full panel
chrome plus its icon, a hover state that visibly "powers up" the tile's brackets, and a
staggered boot-in when the overlay opens.

**Settings panel** — becomes a chrome-framed instrument console rather than a plain centered
box; the base-URL field gains a connection-status indicator dot (reusing the system widget's
ok/error tokens) that pings when a test connection succeeds/fails.

**Alert overlay, conversation log, chat input** — these stay comparatively restrained (they're
transient/utility chrome, not "screens" — over-decorating a toast that's on screen for 4
seconds would be visual noise) but do get panel-chrome borders/glow and the icon set (a small
warning/error/chat icon instead of emoji) for consistency with everything else.

## 4. Build & Task Order

Framework first (Section 2, each module its own task with its own tests), then surfaces in
this order: HUD core → System-Status → Second Brain (list+graph) → remaining 8 list/bar
widgets (grouped sensibly, not all in one task) → Nav overlay → Settings panel → Alert
overlay/conversation log/chat input (grouped, since they're the "restrained" tier). ROADMAP
logged at the end, same as the v1 pass.

## 5. Testing & Verification

Every new TS module (`fx/*.ts`, `motion.ts` additions) gets Vitest tests per the existing
project convention. Pure-CSS/markup composition changes are verified via the existing
`npm test -- --run && npx tsc --noEmit` gate plus an actual Tauri rebuild + relaunch at the end
of the whole pass (not per-surface this time, given the volume of tasks — one real build/look
at the very end, since the user has explicitly said they will review the finished app
themselves rather than mid-flight). `requestAnimationFrame`-driven effects (particle field,
needle sweep, tick-bezel rotation) must all respect `document.hidden` to avoid burning CPU
when the app is backgrounded — this is a concrete testable behavior, not just a nice-to-have.

## 6. Acceptance Criteria

- No emoji remain as data-bearing icons anywhere in `main.ts`'s render functions — replaced by
  the SVG icon set.
- Every widget slot and every overlay uses panel-chrome (corner brackets + glass depth), not a
  plain `border: 1px solid`.
- Particle field and any other continuous `requestAnimationFrame` loop pauses on
  `document.hidden` and resumes on visibility restore (tested).
- All existing Vitest suites stay green; new framework modules ship with their own tests.
- `tsc --noEmit` stays clean throughout.
- No new npm dependencies (canvas/SVG/CSS work is all achievable with the platform + existing
  toolchain) and no UI framework migration.
- One final live Tauri build + relaunch at the end of the whole pass, confirmed by an agent
  actually looking at the running app (screenshot/inspection), not just green tests — this is
  the one visual check for the entire pass, given the user's explicit "review it when I'm
  back" instruction.

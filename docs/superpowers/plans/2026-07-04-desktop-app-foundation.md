# Desktop-App-Grundgerüst (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein lauffähiges Tauri-Desktop-App-Grundgerüst unter `apps/desktop/`, das sich mit dem
bestehenden Alfred-Backend verbindet (Health-Check + Retry, analog zum `AlfredClient`-Pattern
der iOS-Apps) und einen minimalen Ruhezustand-HUD-Screen zeigt, der den echten Verbindungsstatus
und die aktuelle Zeit anzeigt.

**Architecture:** Tauri v2 mit `vanilla-ts`-Template (kein Frontend-Framework, passt zum
bisherigen Vanilla-JS-Stil der PWA). Reine Frontend-Logik (Konfiguration, Health-Check,
HUD-Zustandsableitung) liegt in testbaren TypeScript-Modulen; Rendering ist dünne DOM-Manipulation
darüber. Die Rust-Seite (`src-tauri/`) bleibt in Phase 1 unverändert (Standard-Tauri-Fenster),
Plattform-spezifische Bridges kommen erst in späteren Phasen.

**Tech Stack:** Tauri v2, TypeScript, Vitest (Unit-Tests), npm.

## Global Constraints

- Projektverzeichnis: `apps/desktop/` (Geschwister von `apps/BodyOS` etc.)
- Backend-Basis-URL ist konfigurierbar (Tailscale-Hostname), Default:
  `http://macbook-air-von-timo.tail7e29ff.ts.net:7779` — analog zum `alfred_base_url`-Pattern
  der iOS-Apps.
- Verbindungsverhalten mirrort das bestehende `AlfredClient`-Pattern: bei Nichterreichbarkeit
  EIN Retry nach 1.5s, danach als "offline" markieren (kein endloses Hämmern).
- Phase 1 wird ausschließlich über `npm run tauri dev` auf der aktuellen Entwicklungsmaschine
  (macOS) verifiziert. Ein gebautes Windows-`.exe`/`.msi` ist NICHT Teil dieser Phase — das
  braucht entweder eine Windows-Maschine oder eine CI-Pipeline und wird in Phase 5
  (Packaging) geplant.
- Optik folgt dem Holographic-HUD-Stil aus der Spec: Cyan (`#00e5ff`) auf sehr dunklem
  Hintergrund (`#04070d`), Ring-Element, Monospace-Akzentschrift.

---

### Task 1: Toolchain installieren + Tauri-Projekt scaffolden

**Files:**
- Create: `apps/desktop/` (komplettes Tauri-Projekt, generiert)

**Interfaces:**
- Produces: lauffähiges `npm run tauri dev` in `apps/desktop/`

- [ ] **Step 1: Rust-Toolchain installieren**

Run: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y`

Danach neue Shell öffnen oder: `source "$HOME/.cargo/env"`

Verify: `rustc --version` gibt eine Versionsnummer aus (z.B. `rustc 1.8x.x`).

- [ ] **Step 2: Tauri-Projekt scaffolden**

Von `/Users/timoegersdorfer/Alfred/apps/` aus ausführen:

```bash
cd /Users/timoegersdorfer/Alfred/apps
npm create tauri-app@latest desktop -- --manager npm --template vanilla-ts --identifier com.alfred.desktop --yes
```

Erwartete Ausgabe: `create-tauri-app` legt `apps/desktop/` mit `src/`, `src-tauri/`,
`package.json`, `index.html` an.

- [ ] **Step 3: Dependencies installieren + Dev-Server verifizieren**

```bash
cd /Users/timoegersdorfer/Alfred/apps/desktop
npm install
npm run tauri dev
```

Erwartete Ausgabe: Ein Fenster mit dem Standard-Tauri-Template öffnet sich (Rust kompiliert
beim ersten Mal einige Minuten). Fenster schließen (Ctrl+C im Terminal) um fortzufahren.

- [ ] **Step 4: Vitest für Unit-Tests hinzufügen**

```bash
npm install -D vitest
```

In `apps/desktop/package.json` im `"scripts"`-Block ergänzen:

```json
"test": "vitest run"
```

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop
git commit -m "feat(desktop): Tauri-Projekt-Grundgerüst scaffolden

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend-Konfiguration (Basis-URL, persistiert)

**Files:**
- Create: `apps/desktop/src/config.ts`
- Test: `apps/desktop/src/config.test.ts`

**Interfaces:**
- Produces:
  - `DEFAULT_BASE_URL: string`
  - `getBaseUrl(): string`
  - `setBaseUrl(url: string): void`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `apps/desktop/src/config.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { DEFAULT_BASE_URL, getBaseUrl, setBaseUrl } from './config';

describe('config', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('gibt die Default-URL zurück wenn nichts gespeichert ist', () => {
    expect(getBaseUrl()).toBe(DEFAULT_BASE_URL);
  });

  it('speichert und liest eine benutzerdefinierte URL', () => {
    setBaseUrl('http://192.168.1.50:7779');
    expect(getBaseUrl()).toBe('http://192.168.1.50:7779');
  });

  it('entfernt trailing slash beim Speichern', () => {
    setBaseUrl('http://192.168.1.50:7779/');
    expect(getBaseUrl()).toBe('http://192.168.1.50:7779');
  });
});
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd apps/desktop && npm test`
Expected: FAIL — `Cannot find module './config'`

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `apps/desktop/src/config.ts`:

```typescript
export const DEFAULT_BASE_URL = 'http://macbook-air-von-timo.tail7e29ff.ts.net:7779';

const STORAGE_KEY = 'alfred_base_url';

export function getBaseUrl(): string {
  return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_BASE_URL;
}

export function setBaseUrl(url: string): void {
  localStorage.setItem(STORAGE_KEY, url.replace(/\/+$/, ''));
}
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd apps/desktop && npm test`
Expected: PASS (3 Tests)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/config.ts apps/desktop/src/config.test.ts
git commit -m "feat(desktop): konfigurierbare Backend-Basis-URL mit localStorage-Persistenz

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Health-Check-Client mit Retry (AlfredClient-Pattern)

**Files:**
- Create: `apps/desktop/src/backend.ts`
- Test: `apps/desktop/src/backend.test.ts`

**Interfaces:**
- Consumes: `getBaseUrl()` aus `./config`
- Produces:
  - `type HealthStatus = { ok: boolean; checks?: Record<string, string> }`
  - `checkBackendHealth(baseUrl: string, fetchImpl?: typeof fetch): Promise<HealthStatus>`
    — EIN Retry nach 1.5s bei Fehler, danach `{ ok: false }`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `apps/desktop/src/backend.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { checkBackendHealth } from './backend';

describe('checkBackendHealth', () => {
  it('gibt ok:true zurück wenn der Health-Endpoint erfolgreich antwortet', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, checks: { db: 'ok' } }),
    });
    const result = await checkBackendHealth('http://test:7779', mockFetch as any);
    expect(result).toEqual({ ok: true, checks: { db: 'ok' } });
    expect(mockFetch).toHaveBeenCalledWith('http://test:7779/health', expect.any(Object));
  });

  it('versucht bei einem Fehlschlag genau einmal erneut nach 1.5s', async () => {
    vi.useFakeTimers();
    const mockFetch = vi.fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, checks: {} }) });

    const promise = checkBackendHealth('http://test:7779', mockFetch as any);
    await vi.advanceTimersByTimeAsync(1500);
    const result = await promise;

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(result.ok).toBe(true);
    vi.useRealTimers();
  });

  it('gibt ok:false zurück wenn auch der Retry fehlschlägt', async () => {
    vi.useFakeTimers();
    const mockFetch = vi.fn().mockRejectedValue(new Error('network down'));

    const promise = checkBackendHealth('http://test:7779', mockFetch as any);
    await vi.advanceTimersByTimeAsync(1500);
    const result = await promise;

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(result).toEqual({ ok: false });
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd apps/desktop && npm test`
Expected: FAIL — `Cannot find module './backend'`

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `apps/desktop/src/backend.ts`:

```typescript
export type HealthStatus = { ok: boolean; checks?: Record<string, string> };

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tryFetchHealth(
  baseUrl: string,
  fetchImpl: typeof fetch,
): Promise<HealthStatus> {
  const res = await fetchImpl(`${baseUrl}/health`, { method: 'GET' });
  const data = await res.json();
  return { ok: !!data.ok, checks: data.checks };
}

export async function checkBackendHealth(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
): Promise<HealthStatus> {
  try {
    return await tryFetchHealth(baseUrl, fetchImpl);
  } catch {
    await delay(1500);
    try {
      return await tryFetchHealth(baseUrl, fetchImpl);
    } catch {
      return { ok: false };
    }
  }
}
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd apps/desktop && npm test`
Expected: PASS (3 Tests)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/backend.ts apps/desktop/src/backend.test.ts
git commit -m "feat(desktop): Health-Check-Client mit Einzel-Retry (AlfredClient-Pattern)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: HUD-Zustand ableiten (reine Logik)

**Files:**
- Create: `apps/desktop/src/hud-state.ts`
- Test: `apps/desktop/src/hud-state.test.ts`

**Interfaces:**
- Consumes: `HealthStatus` aus `./backend`
- Produces:
  - `type HudState = { label: string; ringColor: string; statusLine: string }`
  - `deriveHudState(health: HealthStatus, now: Date): HudState`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `apps/desktop/src/hud-state.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { deriveHudState } from './hud-state';

describe('deriveHudState', () => {
  it('zeigt online-Zustand mit Cyan-Ring wenn Backend erreichbar', () => {
    const now = new Date('2026-07-04T18:30:00');
    const state = deriveHudState({ ok: true }, now);
    expect(state.ringColor).toBe('#00e5ff');
    expect(state.label).toBe('Alfred ist bereit.');
  });

  it('zeigt offline-Zustand mit gedämpftem Ring wenn Backend nicht erreichbar', () => {
    const now = new Date('2026-07-04T18:30:00');
    const state = deriveHudState({ ok: false }, now);
    expect(state.ringColor).toBe('#334155');
    expect(state.label).toBe('Keine Verbindung zu Alfred.');
  });

  it('formatiert die Uhrzeit in der Statuszeile', () => {
    const now = new Date('2026-07-04T09:05:00');
    const state = deriveHudState({ ok: true }, now);
    expect(state.statusLine).toContain('09:05');
  });
});
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd apps/desktop && npm test`
Expected: FAIL — `Cannot find module './hud-state'`

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `apps/desktop/src/hud-state.ts`:

```typescript
import type { HealthStatus } from './backend';

export type HudState = { label: string; ringColor: string; statusLine: string };

function formatTime(now: Date): string {
  return now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

export function deriveHudState(health: HealthStatus, now: Date): HudState {
  if (health.ok) {
    return {
      label: 'Alfred ist bereit.',
      ringColor: '#00e5ff',
      statusLine: `Verbunden · ${formatTime(now)}`,
    };
  }
  return {
    label: 'Keine Verbindung zu Alfred.',
    ringColor: '#334155',
    statusLine: `Offline · ${formatTime(now)}`,
  };
}
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd apps/desktop && npm test`
Expected: PASS (3 Tests)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/hud-state.ts apps/desktop/src/hud-state.test.ts
git commit -m "feat(desktop): HUD-Zustandsableitung aus Health-Status + Uhrzeit

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Ruhezustand-HUD-Screen rendern + verkabeln

**Files:**
- Modify: `apps/desktop/index.html` (kompletter Ersatz des Template-Inhalts)
- Modify: `apps/desktop/src/main.ts` (kompletter Ersatz des Template-Inhalts)
- Create: `apps/desktop/src/style.css` (kompletter Ersatz, falls vom Template vorhanden)

**Interfaces:**
- Consumes: `getBaseUrl()` aus `./config`, `checkBackendHealth()` aus `./backend`,
  `deriveHudState()` aus `./hud-state`
- Produces: gerenderter HUD-Screen im Tauri-Fenster, Polling alle 10s

- [ ] **Step 1: HTML-Grundgerüst schreiben**

Datei `apps/desktop/index.html`:

```html
<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <title>Alfred</title>
    <link rel="stylesheet" href="/src/style.css" />
  </head>
  <body>
    <div id="hud">
      <div id="hud-ring"></div>
      <div id="hud-label"></div>
      <div id="hud-status"></div>
    </div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 2: CSS im HUD-Stil schreiben**

Datei `apps/desktop/src/style.css`:

```css
html, body {
  margin: 0;
  height: 100%;
  background: #04070d;
  font-family: 'SF Mono', 'Consolas', monospace;
  color: #00e5ff;
  overflow: hidden;
}

#hud {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

#hud-ring {
  width: 140px;
  height: 140px;
  border-radius: 50%;
  border: 2px solid #00e5ff;
  box-shadow: 0 0 30px currentColor, inset 0 0 25px currentColor;
  transition: color 0.6s ease;
}

#hud-label {
  font-size: 13px;
  letter-spacing: 0.5px;
}

#hud-status {
  font-size: 11px;
  opacity: 0.6;
}
```

- [ ] **Step 3: main.ts mit Polling-Loop schreiben**

Datei `apps/desktop/src/main.ts`:

```typescript
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
```

- [ ] **Step 4: Manuell verifizieren**

Run: `cd apps/desktop && npm run tauri dev`

Erwartet:
- Fenster zeigt einen Cyan-glühenden Ring, Text "Alfred ist bereit." und Uhrzeit, WENN
  der Alfred-Backend-Prozess erreichbar ist (auf dem Mac läuft er unter `localhost:7779` —
  für den lokalen Test in `apps/desktop/src/config.ts` `DEFAULT_BASE_URL` temporär auf
  `http://localhost:7779` setzen, falls Tailscale-Hostname vom Dev-Rechner aus nicht auflöst).
- Alfred-Prozess stoppen (`kill $(cat /tmp/alfred.pid)`) → Ring wird nach max. 10s gedämpft
  grau, Text wechselt zu "Keine Verbindung zu Alfred."
- Alfred-Prozess neu starten (`launchctl kickstart -k gui/501/com.alfred.assistant`) → Ring
  wird nach max. 10s wieder Cyan.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/index.html apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat(desktop): Ruhezustand-HUD-Screen mit Live-Verbindungsstatus

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec-Abdeckung (Abschnitt 1-2 der Spec, Grundlage für alles Weitere):**
- Ein-Backend-Architektur (Abschnitt 1): App verbindet sich nur als Client, kein eigenes
  Backend/DB in der Desktop-App → erfüllt (kein Server-Code in `apps/desktop`).
- Tauri, eine Codebasis (Abschnitt 2): `vanilla-ts`-Template, plattformneutral → erfüllt.
  Windows-Build selbst ist explizit auf Phase 5 verschoben (Global Constraints).
- Adaptiver Screen/HUD-Optik (Abschnitt 3): Ruhezustand-Ring in Holographic-HUD-Farben
  umgesetzt (Task 5). Der eigentliche Kontext-Wechsel (Widgets) ist Phase 2 — hier bewusst
  nur der Ruhezustand.
- Abschnitte 4-7 (UI-Steuerung, Sprache, Layout, versteckte Navigation): bewusst NICHT Teil
  von Phase 1, siehe Phasen-Aufteilung in der Plan-Ankündigung.

**Platzhalter-Scan:** Keine TBD/TODO, jeder Schritt enthält vollständigen Code oder exakte
Befehle mit erwarteter Ausgabe.

**Typ-Konsistenz:** `HealthStatus` (Task 3) wird identisch in `hud-state.ts` (Task 4) und
`main.ts` (Task 5) verwendet; `HudState`-Feldnamen (`label`, `ringColor`, `statusLine`) sind
in Task 4 und Task 5 deckungsgleich.

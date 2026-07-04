# Plan: Phase 6 — Versteckte manuelle Navigation

Bezug: Abschnitt 7 der Spec `docs/superpowers/specs/2026-07-04-multi-device-jarvis-ui-design.md`.
Eine Tastenkombination öffnet eine Vollbild-Übersicht mit vorkonfigurierten Unterscreens; Klick
setzt einen davon als neuen Hauptscreen. Reiner Fallback/Escape-Hatch — kein Agent, keine KI
involviert. Die Spec lässt die genaue Tastenkombination offen; dieser Plan legt sie fest:
**Cmd+K (macOS) / Ctrl+K (Windows)**, Toggle (nochmaliges Drücken oder Escape schließt).

Aus Scope-Gründen (kein Over-Engineering) deckt die Übersicht genau die 6 bereits existierenden
Widget-Typen ab (`WIDGET_TYPES` aus `core/ui_state.py`: sleep, training, tasks, calendar,
nutrition, habits) — keine Platzhalter-Kacheln für nicht existierende Widgets.

## Task 1: Backend — manuelle Widget-Auswahl ohne Agent

**Files:**
- Modify: `web/routers/ui_state.py`
- Test: `tests/test_ui_state_router.py`

**Interfaces:**
- Produces: `POST /api/ui/select` mit Body `{"widget_type": str}` → baut Payload über
  `build_widget_payload`, ruft `UI_BUS.show_widget(widget_type, payload, slot="main")` auf,
  gibt `UI_BUS.current` zurück. Bei unbekanntem `widget_type`: HTTP 400 mit Fehlermeldung.

Test (Auszug, TDD zuerst schreiben):
```python
def test_select_setzt_widget_direkt_ohne_agent(self):
    client = _make_client()
    with patch("web.routers.ui_state.build_widget_payload", return_value={"nights": []}):
        resp = client.post("/api/ui/select", json={"widget_type": "sleep"})
    assert resp.status_code == 200
    assert resp.json()["slots"]["main"]["widget"] == "sleep"

def test_select_unbekannter_typ_gibt_400(self):
    client = _make_client()
    resp = client.post("/api/ui/select", json={"widget_type": "quatsch"})
    assert resp.status_code == 400
```

Implementierung in `web/routers/ui_state.py` (Pydantic-Body oder einfaches `dict`-Parsing,
konsistent mit dem Rest des Routers — kein extra Framework):
```python
from fastapi import HTTPException
from core.ui_state import UI_BUS, build_widget_payload, WIDGET_TYPES

@router.post("/api/ui/select")
async def ui_select(body: dict):
    widget_type = body.get("widget_type")
    if widget_type not in WIDGET_TYPES:
        raise HTTPException(status_code=400, detail=f"Unbekannter widget_type: {widget_type}")
    payload = build_widget_payload(widget_type)
    UI_BUS.show_widget(widget_type, payload, slot="main")
    return UI_BUS.current
```

Volle Suite danach ausführen (`python3 -m pytest tests/ -q`), committen.

## Task 2: Frontend — Vollbild-Grid-Overlay + Hotkey

**Files:**
- Create: `apps/desktop/src/nav-overlay.ts`
- Modify: `apps/desktop/index.html`
- Modify: `apps/desktop/src/style.css`
- Modify: `apps/desktop/src/main.ts`

**Interfaces:**
- Produces: `initNavOverlay(baseUrl: string): void` — registriert einen `keydown`-Listener
  (Cmd/Ctrl+K togglet die Overlay-Sichtbarkeit, Escape schließt sie), rendert ein Grid mit 6
  Kacheln (eine pro `WIDGET_TYPE`), Klick auf eine Kachel ruft `POST {baseUrl}/api/ui/select`
  mit `{widget_type}` auf und schließt die Overlay.

Kein automatisierter Test für den `keydown`-Listener selbst nötig (reine DOM-Verkabelung,
analog zu bestehenden Mustern in `main.ts`) — aber die Kachel-Liste und der Klick-Handler
(Body-Konstruktion, Fetch-Aufruf) sollten mit einem einfachen DOM-Test in jsdom abdeckbar sein,
da hier keine Browser-only-APIs (Mic, MediaRecorder) im Spiel sind. Test:

`apps/desktop/src/nav-overlay.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { initNavOverlay } from './nav-overlay';

describe('nav-overlay', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('togglet Sichtbarkeit bei Cmd+K', () => {
    initNavOverlay('http://x');
    const overlay = document.getElementById('nav-overlay')!;
    expect(overlay.classList.contains('visible')).toBe(false);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    expect(overlay.classList.contains('visible')).toBe(true);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(overlay.classList.contains('visible')).toBe(false);
  });

  it('POSTet gewählten widget_type und schließt die Overlay', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    initNavOverlay('http://x');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }));
    const tile = document.querySelector('[data-widget-type="sleep"]') as HTMLElement;
    tile.click();
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledWith(
      'http://x/api/ui/select',
      expect.objectContaining({ method: 'POST' }),
    );
    const overlay = document.getElementById('nav-overlay')!;
    expect(overlay.classList.contains('visible')).toBe(false);
  });
});
```

`apps/desktop/src/nav-overlay.ts`:
```typescript
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
```

`apps/desktop/src/style.css` ergänzen (Grid-Overlay, standardmäßig unsichtbar):
```css
#nav-overlay {
  display: none;
  position: fixed; inset: 0;
  background: rgba(4, 7, 13, 0.96);
  z-index: 1000;
}
#nav-overlay.visible { display: flex; align-items: center; justify-content: center; }
.nav-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;
}
.nav-tile {
  background: transparent; border: 1px solid #00e5ff55; color: #00e5ff;
  font-family: 'SF Mono', monospace; font-size: 14px; padding: 32px 48px;
  cursor: pointer; border-radius: 4px;
}
.nav-tile:hover { background: #00e5ff22; }
```

`apps/desktop/src/main.ts`: Import + Aufruf ergänzen (Import oben bei den anderen, Aufruf am
Dateiende neben `startVoiceCapture(...)`):
```typescript
import { initNavOverlay } from './nav-overlay';
// ...
initNavOverlay(getBaseUrl());
```

Verifikation: `cd apps/desktop && npm test && npx tsc --noEmit` — erwarte 15/15 (13 bestehend +
2 neue), tsc clean. Danach `npm run tauri dev` kurz starten/beenden (kein Absturz).

Commit:
```bash
git add web/routers/ui_state.py tests/test_ui_state_router.py \
  apps/desktop/src/nav-overlay.ts apps/desktop/src/nav-overlay.test.ts \
  apps/desktop/index.html apps/desktop/src/style.css apps/desktop/src/main.ts
git commit -m "feat: versteckte manuelle Navigation (Cmd/Ctrl+K Grid-Overlay, Phase 6)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

## Self-Review
**Spec-Abdeckung:** Deckt Abschnitt 7 vollständig ab — Hotkey, Vollbild-Grid, Klick setzt
Hauptscreen, kein Agent involviert.
**Platzhalter-Scan:** Keine TBD/TODO. Grid zeigt bewusst nur die 6 existierenden Widget-Typen,
keine Fake-Kacheln für Ungebautes.
**Konsistenz:** `POST /api/ui/select` nutzt exakt dieselbe `build_widget_payload` +
`UI_BUS.show_widget`-Kette wie die bestehenden Agent-Tools (`core/skills/ui.py`) — keine
Duplikation der Widget-Bau-Logik.

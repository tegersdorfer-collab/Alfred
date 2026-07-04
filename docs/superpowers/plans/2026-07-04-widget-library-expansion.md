# Widget-Bibliothek erweitern (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Widget-Bibliothek von nur `"sleep"` auf sechs Typen erweitern (sleep, training,
tasks, calendar, nutrition, habits) — konsolidiert über eine einzige Dispatch-Funktion, damit die
bisher duplizierte Builder-Logik (in `maybe_update_ui` und `core/skills/ui.py`) an einer Stelle
lebt.

**Architecture:** Jeder Widget-Typ bekommt einen eigenen Payload-Builder in `core/ui_state.py`,
der direkt aus dem zugehörigen `domains.*`-Modul strukturierte Daten holt (unabhängig vom
LLM-Text-Ergebnis des jeweiligen Tools, wie bei `sleep` bereits etabliert). Eine neue Funktion
`build_widget_payload(widget_type)` ist die EINZIGE Stelle, die weiß welcher Builder zu welchem
Typ gehört — sowohl `maybe_update_ui` (automatischer Pfad) als auch `core/skills/ui.py::_show_widget`
(expliziter Pfad) rufen nur noch diese eine Funktion auf. Frontend: eine generische `renderWidget()`
ersetzt die bisher sleep-spezifische Rendering-Funktion.

**Tech Stack:** Python (Backend, wie Phase 1-3), TypeScript/Vitest (Frontend, apps/desktop).

## Global Constraints

- Sechs Widget-Typen in dieser Phase: `sleep`, `training`, `tasks`, `calendar`, `nutrition`,
  `habits`. `WIDGET_MAP` erweitert sich entsprechend:
  `{"get_health": "sleep", "recent_workouts": "training", "list_tasks": "tasks",
  "get_calendar": "calendar", "nutrition_today": "nutrition", "list_habits": "habits"}`.
- Payload-Builder bauen KEINE eigenen Daten — sie lesen ausschließlich aus den bestehenden
  `domains.*`-Modulen bzw. der `DashboardReader`-Instanz (Anti-Halluzinations-Constraint, wie
  in Phase 3 etabliert). Kein Builder verändert Daten, nur lesender Zugriff.
- Bestehende Tools (`get_health`, `recent_workouts`, `list_tasks`, `get_calendar`,
  `nutrition_today`, `list_habits` in `core/skills/*.py`) werden NICHT verändert — sie liefern
  weiterhin nur formatierten Text fürs LLM. Die strukturierten Widget-Daten kommen unabhängig
  davon aus den neuen Buildern.
- Layout-Vorlagen (`single`/`split2`) und das Multi-Slot-Fundament aus Phase 3 bleiben
  unverändert — diese Phase erweitert NUR die Widget-Bibliothek, keine neuen Layouts.
- Optik folgt weiterhin dem Holographic-HUD-Stil: Cyan `#00e5ff` auf `#04070d`.

---

### Task 1: Backend — 5 neue Payload-Builder + konsolidierte Dispatch-Funktion

**Files:**
- Modify: `core/ui_state.py` (Ergänzungen + `maybe_update_ui`-Anpassung)
- Modify: `core/skills/ui.py` (`_show_widget` nutzt jetzt `build_widget_payload`/`WIDGET_TYPES`)
- Modify: `tests/test_ui_state_mapping.py` (eine bestehende, jetzt veraltete Assertion ersetzen)
- Create: `tests/test_ui_state_widgets.py`

**Interfaces:**
- Consumes: `domains.fitness.recent_workouts(limit)`, `domains.tasks.list_tasks(status)`,
  `domains.nutrition.day_totals()`, `domains.habits.habit_overview()` (bestehende
  Domain-Funktionen, unverändert), `DashboardReader.get_upcoming_events(days)` (bestehend)
- Produces:
  - `training_widget_payload(limit: int = 8) -> dict` → `{"workouts": [{"date","title","duration_min","distance_km"}, ...]}`
  - `tasks_widget_payload(limit: int = 8) -> dict` → `{"tasks": [{"title","priority","progress_pct"}, ...]}`
  - `calendar_widget_payload(dashboard: Any, days: int = 7) -> dict` → `{"events": [{"title","start","all_day","location"}, ...]}`
  - `nutrition_widget_payload() -> dict` → `{"kcal","protein","carbs","fat"}`
  - `habits_widget_payload() -> dict` → `{"habits": [{"emoji","name","today_done","streak"}, ...]}`
  - `WIDGET_TYPES: set[str]` (alle sechs Typen)
  - `build_widget_payload(widget_type: str) -> dict | None` (einzige Dispatch-Stelle)

- [ ] **Step 1: Fehlschlagenden Test schreiben — `tests/test_ui_state_widgets.py`**

```python
"""Unit-Tests für die neuen Widget-Payload-Builder in core/ui_state.py (Phase 4)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from core.ui_state import (
    training_widget_payload,
    tasks_widget_payload,
    calendar_widget_payload,
    nutrition_widget_payload,
    habits_widget_payload,
    build_widget_payload,
    WIDGET_TYPES,
    WIDGET_MAP,
)


class TestTrainingWidgetPayload:
    def test_formt_workouts(self):
        rows = [
            {"date": date(2026, 7, 1), "title": "Push Day", "duration_min": 60, "distance_km": None},
            {"date": date(2026, 7, 3), "title": "5km Lauf", "duration_min": 30, "distance_km": 5.0},
        ]
        with patch("domains.fitness.recent_workouts", return_value=rows):
            payload = training_widget_payload(limit=8)
        assert payload == {
            "workouts": [
                {"date": "2026-07-01", "title": "Push Day", "duration_min": 60, "distance_km": None},
                {"date": "2026-07-03", "title": "5km Lauf", "duration_min": 30, "distance_km": 5.0},
            ]
        }

    def test_keine_workouts_liefert_leere_liste(self):
        with patch("domains.fitness.recent_workouts", return_value=[]):
            payload = training_widget_payload()
        assert payload == {"workouts": []}


class TestTasksWidgetPayload:
    def test_formt_offene_aufgaben(self):
        rows = [
            {"title": "Steuererklärung", "priority": "high", "progress_pct": 40},
            {"title": "Wäsche waschen", "priority": "low", "progress_pct": 0},
        ]
        with patch("domains.tasks.list_tasks", return_value=rows):
            payload = tasks_widget_payload(limit=8)
        assert payload == {
            "tasks": [
                {"title": "Steuererklärung", "priority": "high", "progress_pct": 40},
                {"title": "Wäsche waschen", "priority": "low", "progress_pct": 0},
            ]
        }

    def test_begrenzt_auf_limit(self):
        rows = [{"title": f"Task {i}", "priority": "medium", "progress_pct": 0} for i in range(20)]
        with patch("domains.tasks.list_tasks", return_value=rows):
            payload = tasks_widget_payload(limit=3)
        assert len(payload["tasks"]) == 3


def _fake_event(title, start, all_day=False, location=None):
    return SimpleNamespace(title=title, start=start, all_day=all_day, location=location)


class FakeDashboard:
    def __init__(self, events=None, rows=None):
        self._events = events or []
        self._rows = rows or []

    def get_upcoming_events(self, days=7):
        return self._events

    def get_recent_health(self, days=7):
        return self._rows


class TestCalendarWidgetPayload:
    def test_formt_termine(self):
        dash = FakeDashboard(events=[
            _fake_event("Zahnarzt", datetime(2026, 7, 5, 14, 0), location="Praxis Müller"),
        ])
        payload = calendar_widget_payload(dash, days=7)
        assert payload == {
            "events": [
                {"title": "Zahnarzt", "start": "2026-07-05T14:00:00", "all_day": False, "location": "Praxis Müller"},
            ]
        }


class TestNutritionWidgetPayload:
    def test_formt_makro_summen(self):
        with patch("domains.nutrition.day_totals",
                   return_value={"kcal": 1800, "protein": 120, "carbs": 200, "fat": 60, "n": 3}):
            payload = nutrition_widget_payload()
        assert payload == {"kcal": 1800, "protein": 120, "carbs": 200, "fat": 60}


class TestHabitsWidgetPayload:
    def test_formt_gewohnheiten(self):
        rows = [
            {"emoji": "🏋", "name": "Training", "today_done": True, "streak": 5},
            {"emoji": "📖", "name": "Lesen", "today_done": False, "streak": 0},
        ]
        with patch("domains.habits.habit_overview", return_value=rows):
            payload = habits_widget_payload()
        assert payload == {
            "habits": [
                {"emoji": "🏋", "name": "Training", "today_done": True, "streak": 5},
                {"emoji": "📖", "name": "Lesen", "today_done": False, "streak": 0},
            ]
        }


class TestWidgetMapAndTypes:
    def test_widget_map_enthaelt_alle_sechs_typen(self):
        assert WIDGET_MAP == {
            "get_health": "sleep",
            "recent_workouts": "training",
            "list_tasks": "tasks",
            "get_calendar": "calendar",
            "nutrition_today": "nutrition",
            "list_habits": "habits",
        }

    def test_widget_types_enthaelt_alle_sechs(self):
        assert WIDGET_TYPES == {"sleep", "training", "tasks", "calendar", "nutrition", "habits"}


class TestBuildWidgetPayload:
    def test_unbekannter_typ_liefert_none(self):
        assert build_widget_payload("unbekannt") is None

    def test_standalone_typ_ohne_dashboard(self):
        with patch("domains.nutrition.day_totals",
                   return_value={"kcal": 500, "protein": 10, "carbs": 50, "fat": 10}):
            payload = build_widget_payload("nutrition")
        assert payload == {"kcal": 500, "protein": 10, "carbs": 50, "fat": 10}

    def test_dashboard_typ_ohne_verfuegbares_dashboard_liefert_none(self):
        with patch("core.container.services.get", return_value=None):
            assert build_widget_payload("sleep") is None

    def test_dashboard_typ_mit_dashboard(self):
        dash = FakeDashboard(rows=[])
        with patch("core.container.services.get", return_value=dash):
            payload = build_widget_payload("sleep")
        assert payload == {"widget": "sleep", "nights": []}
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_widgets.py -v`
Expected: FAIL — `ImportError` (die neuen Namen existieren noch nicht in `core/ui_state.py`)

- [ ] **Step 3: `core/ui_state.py` erweitern**

Direkt NACH der bestehenden Funktion `sleep_widget_payload` (vor der `class UIStateBus:`-Zeile)
folgende neue Builder-Funktionen einfügen:

```python
def training_widget_payload(limit: int = 8) -> dict:
    """Baut Trainings-Daten für das Training-Widget aus domains.fitness."""
    from domains import fitness
    workouts = fitness.recent_workouts(limit=limit)
    return {
        "workouts": [
            {
                "date": w["date"].isoformat(),
                "title": w["title"],
                "duration_min": w.get("duration_min"),
                "distance_km": w.get("distance_km"),
            }
            for w in workouts
        ],
    }


def tasks_widget_payload(limit: int = 8) -> dict:
    """Baut die offenen Aufgaben für das Tasks-Widget aus domains.tasks."""
    from domains import tasks as tasks_d
    rows = tasks_d.list_tasks("open")[:limit]
    return {
        "tasks": [
            {
                "title": t["title"],
                "priority": t.get("priority"),
                "progress_pct": t.get("progress_pct") or 0,
            }
            for t in rows
        ],
    }


def calendar_widget_payload(dashboard: Any, days: int = 7) -> dict:
    """Baut anstehende Termine für das Calendar-Widget aus DashboardReader."""
    events = dashboard.get_upcoming_events(days=days)
    return {
        "events": [
            {
                "title": e.title,
                "start": e.start.isoformat(),
                "all_day": e.all_day,
                "location": e.location,
            }
            for e in events
        ],
    }


def nutrition_widget_payload() -> dict:
    """Baut die heutigen Makro-Summen für das Nutrition-Widget aus domains.nutrition."""
    from domains import nutrition
    t = nutrition.day_totals()
    return {
        "kcal": t.get("kcal", 0),
        "protein": t.get("protein", 0),
        "carbs": t.get("carbs", 0),
        "fat": t.get("fat", 0),
    }


def habits_widget_payload() -> dict:
    """Baut die Gewohnheiten-Übersicht für das Habits-Widget aus domains.habits."""
    from domains import habits
    overview = habits.habit_overview()
    return {
        "habits": [
            {
                "emoji": h["emoji"],
                "name": h["name"],
                "today_done": h["today_done"],
                "streak": h["streak"],
            }
            for h in overview
        ],
    }


# Widget-Typen, die eine Dashboard-Instanz brauchen (services.get("dashboard")).
_DASHBOARD_BUILDERS = {
    "sleep": sleep_widget_payload,
    "calendar": calendar_widget_payload,
}

# Widget-Typen, die keine externe Abhängigkeit brauchen (holen sich ihre Daten
# selbst aus den passenden domains-Modulen).
_STANDALONE_BUILDERS = {
    "training": training_widget_payload,
    "tasks": tasks_widget_payload,
    "nutrition": nutrition_widget_payload,
    "habits": habits_widget_payload,
}

WIDGET_TYPES = set(_DASHBOARD_BUILDERS) | set(_STANDALONE_BUILDERS)


def build_widget_payload(widget_type: str) -> dict | None:
    """Einzige Stelle, die weiß wie man Daten für einen Widget-Typ baut. Gibt
    None zurück wenn der Typ unbekannt ist oder seine Datenquelle (aktuell
    nur 'dashboard') nicht verfügbar ist."""
    if widget_type in _DASHBOARD_BUILDERS:
        from core.container import services
        dash = services.get("dashboard")
        if dash is None:
            return None
        return _DASHBOARD_BUILDERS[widget_type](dash)
    builder = _STANDALONE_BUILDERS.get(widget_type)
    if builder is None:
        return None
    return builder()
```

Die bestehende `WIDGET_MAP`-Konstante (weiter oben in der Datei) ersetzen durch:

```python
# Tool-Name → Widget-Typ.
WIDGET_MAP: dict[str, str] = {
    "get_health": "sleep",
    "recent_workouts": "training",
    "list_tasks": "tasks",
    "get_calendar": "calendar",
    "nutrition_today": "nutrition",
    "list_habits": "habits",
}
```

Die bestehende Funktion `maybe_update_ui` komplett ersetzen durch:

```python
def maybe_update_ui(tools_used: list[str]) -> None:
    """Nach einem Agent-Turn aufgerufen: prüft ob ein genutztes Tool einem
    Widget zugeordnet ist, baut bei Treffer die Daten und zeigt sie im
    'main'-Slot. Wenn der Turn stattdessen ein explizites UI-Tool genutzt hat
    (show_widget/arrange_screen/close_widget), hat der Bus bereits den
    korrekten Zustand — die automatische Zuordnung darf ihn dann NICHT
    überschreiben/zurücksetzen. Fehler werden geschluckt — UI-Updates dürfen
    nie einen Chat-Turn brechen."""
    for tool_name in tools_used:
        widget_type = widget_type_for_tool(tool_name)
        if widget_type is None:
            continue
        try:
            payload = build_widget_payload(widget_type)
            if payload is None:
                return
            UI_BUS.show_widget(widget_type, payload, slot="main")
            return  # erstes Match gewinnt
        except Exception as e:
            log.debug(f"maybe_update_ui fehlgeschlagen für '{tool_name}': {e}")
            return
    if any(t in EXPLICIT_UI_TOOLS for t in tools_used):
        return
    try:
        UI_BUS.clear()
    except Exception as e:
        log.debug(f"maybe_update_ui: clear() fehlgeschlagen: {e}")
```

- [ ] **Step 4: `core/skills/ui.py` — `_show_widget` auf die konsolidierte Dispatch-Funktion umstellen**

Die Import-Zeile am Kopf der Datei ersetzen:

```python
from core.ui_state import UI_BUS, LAYOUT_PRESETS, DEFAULT_LAYOUT, WIDGET_TYPES, build_widget_payload
```

Den bestehenden `_PAYLOAD_BUILDERS`-Dict-Block (direkt unter dem Logger) komplett entfernen (wird
nicht mehr gebraucht — `build_widget_payload` übernimmt das jetzt zentral).

Die Funktion `_show_widget` komplett ersetzen durch:

```python
@T.register("show_widget",
    "Zeigt ein Daten-Widget auf dem Desktop-Bildschirm an (verfügbar: sleep, training, tasks, "
    "calendar, nutrition, habits). Nutze dies wenn du proaktiv etwas Visuelles zeigen willst, "
    "zusätzlich zu oder statt einer Textantwort — z.B. wenn Timo mehrere Dinge gleichzeitig "
    "sehen will.",
    {
        "widget_type": {"type": "string", "description": "Widget-Typ, z.B. 'sleep', 'training', 'tasks', 'calendar', 'nutrition', 'habits'"},
        "slot": {"type": "string", "description": "Ziel-Slot im aktuellen Layout, Standard 'main'"},
    },
    ["widget_type"], "ui")
async def _show_widget(widget_type: str, slot: str = "main"):
    if widget_type not in WIDGET_TYPES:
        return f"FEHLER: Unbekannter Widget-Typ '{widget_type}'. Verfügbar: {', '.join(sorted(WIDGET_TYPES))}."

    active_layout = UI_BUS.current["layout"] or DEFAULT_LAYOUT
    if slot not in LAYOUT_PRESETS[active_layout]:
        return (f"FEHLER: Slot '{slot}' existiert nicht in Layout '{active_layout}'. "
                f"Verfügbare Slots: {', '.join(LAYOUT_PRESETS[active_layout])}.")

    payload = build_widget_payload(widget_type)
    if payload is None:
        return f"FEHLER: Konnte Daten für Widget '{widget_type}' nicht laden (Datenquelle nicht verfügbar)."
    UI_BUS.show_widget(widget_type, payload, slot=slot)
    return f"Widget '{widget_type}' wird jetzt im Slot '{slot}' angezeigt."
```

(`_arrange_screen` und `_close_widget` bleiben unverändert.)

- [ ] **Step 5: Veraltete Assertion in `tests/test_ui_state_mapping.py` aktualisieren**

In `tests/test_ui_state_mapping.py`, Klasse `TestWidgetTypeForTool`, die Methode
`test_widget_map_enthaelt_nur_get_health` ersetzen durch:

```python
    def test_get_calendar_mappt_auf_calendar(self):
        assert widget_type_for_tool("get_calendar") == "calendar"
```

(Die vollständige `WIDGET_MAP`-Prüfung lebt jetzt in `tests/test_ui_state_widgets.py::TestWidgetMapAndTypes`.)

- [ ] **Step 6: Alle betroffenen Tests + volle Suite ausführen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_widgets.py tests/test_ui_state_mapping.py tests/test_ui_skills.py -v`
Expected: PASS (16 + 10 + 8 = 34 Tests)

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle Tests PASS, keine Regressionen

- [ ] **Step 7: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add core/ui_state.py core/skills/ui.py tests/test_ui_state_widgets.py tests/test_ui_state_mapping.py
git commit -m "feat(widgets): Widget-Bibliothek auf 6 Typen erweitern (training/tasks/calendar/nutrition/habits)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Frontend — generisches Widget-Rendering + Live-E2E-Verifikation

**Files:**
- Modify: `apps/desktop/src/main.ts` (kompletter Ersatz der Rendering-Logik)
- Modify: `apps/desktop/src/style.css` (Ergänzung: Listen-Darstellung)

**Interfaces:**
- Consumes: `UiEvent`/`WidgetSlot` aus `./ui-state-client` (Phase 3, Typ bleibt strukturell
  unverändert — nur `WidgetSlot.payload` ist jetzt je nach `widget`-Feld unterschiedlich geformt,
  siehe Constraint unten)
- Produces: `renderWidget(container: HTMLElement, slot: WidgetSlot): void` — ersetzt die bisherige
  `renderSleepWidget`, deckt alle 6 Widget-Typen ab

- [ ] **Step 1: `apps/desktop/src/style.css` — Listen-Darstellung ergänzen**

Am Ende der Datei anhängen:

```css
.widget-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 0 12px;
  box-sizing: border-box;
}

.list-line {
  font-size: 12px;
  color: #e0f7ff;
  padding: 4px 0;
  border-bottom: 1px solid #00e5ff11;
}
```

- [ ] **Step 2: `apps/desktop/src/main.ts` komplett ersetzen**

```typescript
import { getBaseUrl } from './config';
import { checkBackendHealth } from './backend';
import { deriveHudState } from './hud-state';
import { subscribeUiState } from './ui-state-client';
import type { UiEvent, WidgetSlot } from './ui-state-client';

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
```

- [ ] **Step 3: Lokale Tests + Type-Check ausführen**

Run: `cd apps/desktop && npm test && npx tsc --noEmit`
Expected: alle 13 Tests PASS, `tsc` ohne Ausgabe (Exit 0)

- [ ] **Step 4: Manuell gegen den echten laufenden Alfred-Backend-Prozess verifizieren**

Sicherer Neustart (Backend-Änderungen aus Task 1 müssen geladen werden):

```bash
kill $(cat /tmp/alfred.pid) 2>/dev/null
sleep 3
launchctl kickstart -k gui/501/com.alfred.assistant
for i in $(seq 1 20); do sleep 3; code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:7779/health); if [ "$code" = "200" ]; then echo "OK nach $((i*3))s"; break; fi; done
```

Für JEDES der 5 neuen Widgets einen echten Chat-Turn auslösen und `/api/ui/current` prüfen
(jeweils zwischen den Aufrufen kurz warten, damit der vorherige Turn durch ist):

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" -d '{"text":"Zeig mir meine letzten Trainings."}'
curl -s http://localhost:7779/api/ui/current
```
Erwartet: `"widget":"training"` mit `"workouts"`-Array in der Antwort.

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" -d '{"text":"Was habe ich noch offen an Aufgaben?"}'
curl -s http://localhost:7779/api/ui/current
```
Erwartet: `"widget":"tasks"` mit `"tasks"`-Array.

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" -d '{"text":"Was steht diese Woche in meinem Kalender an?"}'
curl -s http://localhost:7779/api/ui/current
```
Erwartet: `"widget":"calendar"` mit `"events"`-Array.

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" -d '{"text":"Wie viel habe ich heute schon gegessen?"}'
curl -s http://localhost:7779/api/ui/current
```
Erwartet: `"widget":"nutrition"` mit `kcal`/`protein`/`carbs`/`fat`-Feldern.

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" -d '{"text":"Wie stehen meine Gewohnheiten aktuell?"}'
curl -s http://localhost:7779/api/ui/current
```
Erwartet: `"widget":"habits"` mit `"habits"`-Array.

**Wichtig (LLM-Verhalten ist nicht 100% deterministisch):** Falls einer der fünf Chat-Turns NICHT
das erwartete Tool auslöst (das LLM formuliert die Antwort z.B. rein aus dem Gedächtnis ohne
Tool-Call), ist das ein legitimes Beobachtungsergebnis — im Bericht dokumentieren, nicht als
Fehlschlag werten. Mindestens EINER der fünf Fälle sollte aber zuverlässig funktionieren (dient
als Nachweis dass die Backend→Frontend-Kette für die neuen Typen grundsätzlich funktioniert);
falls alle fünf fehlschlagen, ist das ein Hinweis auf einen echten Bug und sollte als
DONE_WITH_CONCERNS gemeldet werden.

Danach `npm run tauri dev` kurz im Hintergrund starten, Prozess-Existenz bestätigen, sauber
beenden. Alfred am Ende NICHT gestoppt zurücklassen.

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat(desktop): generisches Widget-Rendering für alle 6 Widget-Typen

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec-Abdeckung:** Erste Widget-Bibliothek (Spec-Nicht-Ziel aus Phase 2/3, jetzt hier
eingelöst) — 6 Typen abgedeckt: sleep (Phase 2), training/tasks/calendar/nutrition/habits (diese
Phase). Bewusst NICHT Teil: weitere Widgets (Second Brain, Ziele, Körpermessungen — spätere
Erweiterung bei Bedarf, derselbe Mechanismus trägt).

**Platzhalter-Scan:** Keine TBD/TODO, jeder Schritt enthält vollständigen Code oder exakte
Befehle mit erwarteter Ausgabe.

**Typ-Konsistenz:** `build_widget_payload`-Rückgabeformen (Task 1) sind identisch mit den in
`renderWidget` (Task 2) konsumierten Feldnamen: `nights`/`hours` (sleep), `workouts`/
`duration_min` (training), `tasks`/`progress_pct` (tasks), `events`/`start` (calendar),
`kcal`/`protein`/`carbs`/`fat` (nutrition), `habits`/`streak` (habits) — durchgängig
deckungsgleich zwischen Python-Dict und TypeScript-Zugriff.

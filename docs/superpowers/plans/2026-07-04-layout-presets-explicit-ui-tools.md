# Layout-Vorlagen + Explizite UI-Tools (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den Ein-Slot-Zustand aus Phase 2 zu einem Mehrfach-Slot/Layout-Fundament ausbauen —
Alfred kann selbst entscheiden, wann mehrere Widgets gleichzeitig sichtbar sein sollen (begrenztes
Set an Layout-Vorlagen), über normale, explizite Agent-Tools (`show_widget`, `arrange_screen`,
`close_widget`) zusätzlich zur bestehenden automatischen Tool→Widget-Zuordnung.

**Architecture:** `UIStateBus` (core/ui_state.py) wird von "ein Widget oder nichts" zu
"Layout-Vorlage + belegte Slots" erweitert — der Ruhezustand wird durch `layout: None, slots: {}`
repräsentiert statt durch `None`, damit Bus und Frontend durchgehend eine einzige, immer gültige
Struktur teilen. Die bestehende automatische Zuordnung (`maybe_update_ui`) bleibt erhalten und
schreibt weiterhin ins `"main"`-Slot der Standard-Vorlage; explizite Tools kommen als normale
Einträge in der bestehenden Tool-Registry hinzu (kein zweites System).

**Tech Stack:** Python/FastAPI (Backend, wie Phase 1+2), TypeScript/Vitest (Frontend, apps/desktop).

## Global Constraints

- Layout-Vorlagen in dieser Phase (bewusst nur zwei, weitere folgen bei Bedarf):
  `LAYOUT_PRESETS = {"single": ["main"], "split2": ["main", "side"]}`.
- Widget-Bibliothek bleibt bei nur `"sleep"` — Erweiterung um weitere Widgets ist NICHT Teil
  dieser Phase (eigene, spätere Phase 4).
- `UIStateBus.current` gibt NIE `None` zurück — Ruhezustand ist `{"layout": None, "slots": {},
  "ts": float}`. Das ist eine bewusste Breaking-Change gegenüber Phase 2 (dort war `current`
  `None` im Ruhezustand) — alle bestehenden Konsumenten (Router, Tests, Frontend) werden in
  dieser Phase mitmigriert.
- Explizite UI-Tools bauen KEINE eigenen Daten — sie rufen dieselben Payload-Builder-Funktionen
  auf wie die automatische Zuordnung (`sleep_widget_payload`), nie erfindet das LLM selbst
  Zahlen/Daten für ein Widget (Konsistenz mit dem bestehenden `no_hallucinated_data`-Eval-Case).
- Optik folgt weiterhin dem Holographic-HUD-Stil: Cyan `#00e5ff` auf `#04070d`.

## Nicht-Ziele dieser Phase
- Zusätzliche Layout-Vorlagen über `single`/`split2` hinaus.
- Erweiterung der Widget-Bibliothek über `sleep` hinaus (Phase 4).
- Gezielte Tool-Routing-Keywords, damit `show_widget`/`arrange_screen` häufiger vom LLM gewählt
  werden — verlässt sich in dieser Phase auf den bestehenden generischen Fallback-Mechanismus
  (`core/tools.py::select_tools`, semantisches Ranking bei wenigen Keyword-Treffern).

---

### Task 1: `UIStateBus` auf Multi-Slot-Layout migrieren

**Files:**
- Modify: `core/ui_state.py` (kompletter Ersatz)
- Modify: `web/routers/ui_state.py` (Vereinfachung, `current` ist nie mehr `None`)
- Modify: `tests/test_ui_state_bus.py` (kompletter Ersatz)
- Modify: `tests/test_ui_state_mapping.py` (nur `TestMaybeUpdateUiZurueckZumRuhezustand` ersetzen,
  `TestWidgetTypeForTool` + `TestSleepWidgetPayload` bleiben unverändert)
- Modify: `tests/test_ui_state_router.py` (kompletter Ersatz)

**Interfaces:**
- Produces:
  - `LAYOUT_PRESETS: dict[str, list[str]]`
  - `DEFAULT_LAYOUT: str` (Wert `"single"`)
  - `UIStateBus.show_widget(widget_type: str, payload: dict, slot: str = "main") -> None`
  - `UIStateBus.close_widget(slot: str) -> None`
  - `UIStateBus.arrange_screen(layout: str) -> None` (wirft `ValueError` bei unbekanntem Layout)
  - `UIStateBus.clear() -> None`
  - `UIStateBus.current -> dict` (immer `{"layout": str|None, "slots": dict, "ts": float}`, NIE `None`)
- Consumes: nichts Neues von außen — reine Erweiterung des bestehenden Moduls.

- [ ] **Step 1: Fehlschlagende Tests schreiben — `tests/test_ui_state_bus.py` komplett ersetzen**

```python
"""Unit-Tests für core/ui_state.py::UIStateBus (Multi-Slot-Layout, Publish/Subscribe)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from core.ui_state import UIStateBus


class TestUIStateBus:
    def test_initial_current_ist_ruhezustand(self):
        bus = UIStateBus()
        assert bus.current == {"layout": None, "slots": {}, "ts": 0.0}

    def test_show_widget_setzt_default_layout_und_slot(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        assert bus.current["layout"] == "single"
        assert bus.current["slots"]["main"] == {"widget": "sleep", "payload": {"nights": []}}
        assert bus.current["ts"] > 0

    def test_show_widget_mit_explizitem_slot(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []}, slot="side")
        assert bus.current["slots"] == {"side": {"widget": "sleep", "payload": {"nights": []}}}

    def test_close_widget_entfernt_einzelnen_slot(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {}, slot="main")
        bus.show_widget("sleep", {}, slot="side")
        bus.close_widget("main")
        assert "main" not in bus.current["slots"]
        assert "side" in bus.current["slots"]
        assert bus.current["layout"] == "single"

    def test_close_widget_letzter_slot_geht_zurueck_in_ruhezustand(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {}, slot="main")
        bus.close_widget("main")
        assert bus.current["layout"] is None
        assert bus.current["slots"] == {}

    def test_arrange_screen_wechselt_layout(self):
        bus = UIStateBus()
        bus.arrange_screen("split2")
        assert bus.current["layout"] == "split2"
        assert bus.current["slots"] == {}

    def test_arrange_screen_verwirft_nicht_passende_slots(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {}, slot="main")
        bus.show_widget("sleep", {}, slot="side")
        bus.arrange_screen("single")  # "single" kennt nur "main"
        assert "side" not in bus.current["slots"]
        assert "main" in bus.current["slots"]

    def test_arrange_screen_unbekanntes_layout_wirft(self):
        bus = UIStateBus()
        try:
            bus.arrange_screen("nicht-existent")
            assert False, "sollte ValueError werfen"
        except ValueError:
            pass

    def test_clear_setzt_ruhezustand_zurueck(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        bus.clear()
        assert bus.current["layout"] is None
        assert bus.current["slots"] == {}

    def test_subscriber_bekommt_show_widget_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.show_widget("sleep", {"nights": []})
            evt = q.get_nowait()
            assert evt["slots"]["main"]["widget"] == "sleep"

        asyncio.run(run())

    def test_subscriber_bekommt_clear_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.clear()
            evt = q.get_nowait()
            assert evt["layout"] is None
            assert evt["slots"] == {}

        asyncio.run(run())

    def test_unsubscribe_entfernt_listener(self):
        bus = UIStateBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.show_widget("sleep", {"nights": []})
        assert q.empty()

    def test_unsubscribe_unbekannte_queue_wirft_nicht(self):
        bus = UIStateBus()
        bus.unsubscribe(asyncio.Queue())

    def test_volle_queue_verwirft_event_statt_zu_blockieren(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            for i in range(60):
                bus.show_widget("sleep", {"night": i})
            assert q.full()

        asyncio.run(run())
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_bus.py -v`
Expected: FAIL — `KeyError`/`AssertionError` (aktuelle `UIStateBus` kennt weder `close_widget`
noch `arrange_screen`, `current` liefert noch das alte `{"widget", "payload", "ts"}`-Schema oder
`None`).

- [ ] **Step 3: `core/ui_state.py` komplett ersetzen**

```python
"""
UI-State — Grundlage des generativen UI.

Phase 2: Tool-Aufrufe werden deterministisch Widget-Typen zugeordnet (kein
Extra-LLM-Call), ein einzelner Slot hielt den aktiven Widget-Zustand.
Phase 3: Mehrere gleichzeitig sichtbare Widgets über ein begrenztes Set an
Layout-Vorlagen (LAYOUT_PRESETS) — Alfred wählt selbst, wann mehrere Dinge
gleichzeitig sichtbar sein sollen (explizite Tools in core/skills/ui.py),
während einfache Anfragen weiterhin automatisch (maybe_update_ui) ins
"main"-Slot der Standard-Vorlage gehen.
"""
import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Tool-Name → Widget-Typ. Erweitert sich mit der Widget-Bibliothek (Phase 4).
WIDGET_MAP: dict[str, str] = {
    "get_health": "sleep",
}

# Begrenztes Set an Layout-Vorlagen — jede definiert ihre verfügbaren Slots.
LAYOUT_PRESETS: dict[str, list[str]] = {
    "single": ["main"],
    "split2": ["main", "side"],
}

DEFAULT_LAYOUT = "single"


def widget_type_for_tool(tool_name: str) -> str | None:
    return WIDGET_MAP.get(tool_name)


def sleep_widget_payload(dashboard: Any, days: int = 7) -> dict:
    """Baut strukturierte Schlaf-Daten für das Sleep-Widget — unabhängig vom
    LLM-Text-Ergebnis von get_health, direkt aus DashboardReader."""
    rows = dashboard.get_recent_health(days=days)
    return {
        "widget": "sleep",
        "nights": [
            {
                "date": r.date.isoformat(),
                "hours": r.sleep_duration,
                "deep_hours": r.sleep_deep,
            }
            for r in rows
        ],
    }


class UIStateBus:
    """Hält den aktuell aktiven Layout-Zustand (Vorlage + belegte Slots) und
    pusht Änderungen an SSE-Subscriber. `current` ist NIE None — der
    Ruhezustand wird durch `layout: None, slots: {}` repräsentiert, damit
    Bus und Frontend eine einzige, immer gültige Struktur teilen."""

    def __init__(self) -> None:
        self._layout: str | None = None
        self._slots: dict[str, dict] = {}
        self._ts: float = 0.0
        self._listeners: list[asyncio.Queue] = []

    @property
    def current(self) -> dict:
        return {"layout": self._layout, "slots": dict(self._slots), "ts": self._ts}

    def show_widget(self, widget_type: str, payload: dict, slot: str = "main") -> None:
        """Zeigt ein Widget in einem Slot. Wenn noch keine Vorlage aktiv ist,
        wird die Standard-Vorlage (DEFAULT_LAYOUT) automatisch gesetzt."""
        if self._layout is None:
            self._layout = DEFAULT_LAYOUT
        self._slots[slot] = {"widget": widget_type, "payload": payload}
        self._broadcast()

    def close_widget(self, slot: str) -> None:
        """Entfernt ein Widget aus einem Slot. Sind danach keine Slots mehr
        belegt, kehrt der Bus vollständig in den Ruhezustand zurück."""
        self._slots.pop(slot, None)
        if not self._slots:
            self._layout = None
        self._broadcast()

    def arrange_screen(self, layout: str) -> None:
        """Wechselt die Layout-Vorlage. Slots, die in der neuen Vorlage nicht
        existieren, werden verworfen; passende Slot-Belegungen bleiben erhalten."""
        if layout not in LAYOUT_PRESETS:
            raise ValueError(f"Unbekannte Layout-Vorlage: '{layout}'")
        allowed = set(LAYOUT_PRESETS[layout])
        self._layout = layout
        self._slots = {k: v for k, v in self._slots.items() if k in allowed}
        self._broadcast()

    def clear(self) -> None:
        """Zurück in den vollständigen Ruhezustand (kein Layout, keine Slots)."""
        self._layout = None
        self._slots = {}
        self._broadcast()

    def _broadcast(self) -> None:
        self._ts = time.time()
        evt = self.current
        for q in self._listeners[:]:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass  # langsamer Client — Event überspringen, kein Absturz

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._listeners.remove(q)
        except ValueError:
            pass


UI_BUS = UIStateBus()


def maybe_update_ui(tools_used: list[str]) -> None:
    """Nach einem Agent-Turn aufgerufen: prüft ob ein genutztes Tool einem
    Widget zugeordnet ist, baut bei Treffer die Daten und zeigt sie im
    'main'-Slot. Fehler werden geschluckt — UI-Updates dürfen nie einen
    Chat-Turn brechen."""
    for tool_name in tools_used:
        widget_type = widget_type_for_tool(tool_name)
        if widget_type is None:
            continue
        try:
            from core.container import services
            dash = services.get("dashboard")
            if dash is None:
                return
            if widget_type == "sleep":
                payload = sleep_widget_payload(dash)
                UI_BUS.show_widget("sleep", payload, slot="main")
            return  # erstes Match gewinnt
        except Exception as e:
            log.debug(f"maybe_update_ui fehlgeschlagen für '{tool_name}': {e}")
            return
    # Kein Tool in diesem Turn einem Widget zugeordnet → zurück zum Ruhezustand
    try:
        UI_BUS.clear()
    except Exception as e:
        log.debug(f"maybe_update_ui: clear() fehlgeschlagen: {e}")
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_bus.py -v`
Expected: PASS (14 Tests)

- [ ] **Step 5: `tests/test_ui_state_mapping.py` anpassen — NUR die Klasse
  `TestMaybeUpdateUiZurueckZumRuhezustand` ersetzen (Rest der Datei unverändert lassen)**

Ersetze in `tests/test_ui_state_mapping.py` die komplette Klasse `TestMaybeUpdateUiZurueckZumRuhezustand`
(am Ende der Datei) durch:

```python
class TestMaybeUpdateUiZurueckZumRuhezustand:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_leere_tool_liste_geht_zurueck_in_ruhezustand(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        maybe_update_ui([])
        assert UI_BUS.current["layout"] is None
        assert UI_BUS.current["slots"] == {}

    def test_kein_gemapptes_tool_geht_zurueck_in_ruhezustand(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        maybe_update_ui(["create_task"])
        assert UI_BUS.current["layout"] is None
        assert UI_BUS.current["slots"] == {}

    def test_get_health_setzt_weiterhin_sleep_widget(self):
        dash = FakeDashboard([_fake_health_row(date(2026, 7, 4), 7.0, 1.0)])
        with patch("core.container.services.get", return_value=dash):
            maybe_update_ui(["get_health"])
        assert UI_BUS.current["layout"] == "single"
        assert UI_BUS.current["slots"]["main"] == {
            "widget": "sleep",
            "payload": {
                "widget": "sleep",
                "nights": [{"date": "2026-07-04", "hours": 7.0, "deep_hours": 1.0}],
            },
        }
```

Die restlichen Klassen (`TestWidgetTypeForTool`, `TestSleepWidgetPayload`) und alle Imports am
Kopf der Datei bleiben unverändert.

- [ ] **Step 6: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_mapping.py -v`
Expected: PASS (10 Tests)

- [ ] **Step 7: `web/routers/ui_state.py` vereinfachen (current ist nie mehr None)**

```python
"""
UI-State — API-Router. SSE-Kanal für das generative UI.
Verhaltensgleiches Muster zu web/routers/chat.py::status_stream.
"""
import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.ui_state import UI_BUS

log = logging.getLogger("alfred.api")


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/ui/current")
    def ui_current():
        return UI_BUS.current

    @router.get("/api/ui/stream")
    async def ui_stream():
        q = UI_BUS.subscribe()

        async def gen():
            try:
                yield f"data: {json.dumps(UI_BUS.current)}\n\n"
                while True:
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=25)
                        yield f"data: {json.dumps(evt)}\n\n"
                    except asyncio.TimeoutError:
                        yield "data: {\"keepalive\":true}\n\n"
            finally:
                UI_BUS.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    return router
```

- [ ] **Step 8: `tests/test_ui_state_router.py` komplett ersetzen**

```python
"""Testet den /api/ui/current-Endpunkt über einen echten FastAPI-TestClient
(SSE-Streaming selbst wird per manueller curl-Verifikation geprüft, nicht
hier — blockierende Generatoren sind mit TestClient unhandlich)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.ui_state import UI_BUS
from web.routers.ui_state import build_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


class TestUiCurrentEndpoint:
    def test_liefert_ruhezustand_wenn_kein_widget_aktiv(self):
        UI_BUS.clear()
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["layout"] is None
        assert body["slots"] == {}

    def test_liefert_aktuellen_layout_zustand(self):
        UI_BUS.show_widget("sleep", {"nights": []})
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["layout"] == "single"
        assert body["slots"]["main"] == {"widget": "sleep", "payload": {"nights": []}}
        UI_BUS.clear()  # Zustand für andere Tests zurücksetzen
```

- [ ] **Step 9: Alle betroffenen Tests + volle Suite ausführen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_bus.py tests/test_ui_state_mapping.py tests/test_ui_state_router.py -v`
Expected: PASS (14 + 10 + 2 = 26 Tests)

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle Tests PASS (keine Regressionen in `tests/test_message_handler_ui_wiring.py` — die
mockt nur den Aufruf von `maybe_update_ui`, ist von der Shape-Änderung nicht betroffen)

- [ ] **Step 10: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add core/ui_state.py web/routers/ui_state.py tests/test_ui_state_bus.py tests/test_ui_state_mapping.py tests/test_ui_state_router.py
git commit -m "feat(ui-state): Multi-Slot-Layout-Fundament (LAYOUT_PRESETS, arrange_screen, close_widget)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Explizite UI-Tools (`show_widget`, `arrange_screen`, `close_widget`)

**Files:**
- Create: `core/skills/ui.py`
- Modify: `core/skills/__init__.py:9-21` (Import-Block: `ui` ergänzen)
- Test: `tests/test_ui_skills.py`

**Interfaces:**
- Consumes: `UI_BUS`, `LAYOUT_PRESETS`, `sleep_widget_payload` aus `core.ui_state` (Task 1),
  `services.get("dashboard")` aus `core.container` (bestehendes Pattern)
- Produces: drei registrierte Agent-Tools `show_widget`, `arrange_screen`, `close_widget`
  (Kategorie `"ui"` in der Tool-Registry) — Handler-Funktionen `_show_widget(widget_type, slot="main")`,
  `_arrange_screen(layout)`, `_close_widget(slot="main")` (async, geben `str` zurück)

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_ui_skills.py`:

```python
"""Unit-Tests für core/skills/ui.py: explizite UI-Tools (show_widget/arrange_screen/close_widget)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from core.ui_state import UI_BUS
import core.skills.ui as ui_skills


def _fake_health_row(d, hours, deep):
    return SimpleNamespace(date=d, sleep_duration=hours, sleep_deep=deep)


class FakeDashboard:
    def __init__(self, rows):
        self._rows = rows

    def get_recent_health(self, days=7):
        return self._rows


class TestShowWidget:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_zeigt_bekanntes_widget_im_main_slot(self):
        dash = FakeDashboard([_fake_health_row(date(2026, 7, 4), 7.0, 1.0)])
        with patch("core.container.services.get", return_value=dash):
            result = asyncio.run(ui_skills._show_widget("sleep"))
        assert "sleep" in result
        assert UI_BUS.current["slots"]["main"]["widget"] == "sleep"

    def test_zeigt_widget_in_explizitem_slot(self):
        dash = FakeDashboard([])
        with patch("core.container.services.get", return_value=dash):
            asyncio.run(ui_skills._show_widget("sleep", slot="side"))
        assert "side" in UI_BUS.current["slots"]

    def test_unbekannter_widget_typ_liefert_fehlermeldung_statt_crash(self):
        result = asyncio.run(ui_skills._show_widget("unbekannt"))
        assert result.startswith("FEHLER")
        assert UI_BUS.current["slots"] == {}

    def test_kein_dashboard_liefert_fehlermeldung(self):
        with patch("core.container.services.get", return_value=None):
            result = asyncio.run(ui_skills._show_widget("sleep"))
        assert result.startswith("FEHLER")


class TestArrangeScreen:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_setzt_bekanntes_layout(self):
        result = asyncio.run(ui_skills._arrange_screen("split2"))
        assert "split2" in result
        assert UI_BUS.current["layout"] == "split2"

    def test_unbekanntes_layout_liefert_fehlermeldung_statt_crash(self):
        result = asyncio.run(ui_skills._arrange_screen("nicht-existent"))
        assert result.startswith("FEHLER")


class TestCloseWidget:
    def setup_method(self):
        UI_BUS.clear()

    def teardown_method(self):
        UI_BUS.clear()

    def test_schliesst_slot(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        result = asyncio.run(ui_skills._close_widget("main"))
        assert "main" in result
        assert "main" not in UI_BUS.current["slots"]

    def test_default_slot_ist_main(self):
        UI_BUS.show_widget("sleep", {}, slot="main")
        asyncio.run(ui_skills._close_widget())
        assert "main" not in UI_BUS.current["slots"]
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_skills.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.skills.ui'`

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `core/skills/ui.py`:

```python
"""
UI-Tools — explizite Steuerung des generativen Desktop-UI (Phase 3).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).

Ergänzt die deterministische Basis-Zuordnung aus core/ui_state.py::maybe_update_ui
um Fälle, die echtes Urteilsvermögen brauchen: mehrere Widgets gleichzeitig
anordnen, eins schließen, zwischen Layout-Vorlagen wechseln.
"""
import logging

from core import tools as T
from core.ui_state import UI_BUS, LAYOUT_PRESETS, sleep_widget_payload

log = logging.getLogger("core.skills")

# Widget-Typ → Funktion die (dashboard) -> payload-dict baut. Wächst mit der
# Widget-Bibliothek (Phase 4).
_PAYLOAD_BUILDERS = {
    "sleep": sleep_widget_payload,
}


@T.register("show_widget",
    "Zeigt ein Daten-Widget auf dem Desktop-Bildschirm an (aktuell verfügbar: 'sleep' für "
    "Timos Schlaf-Graph). Nutze dies wenn du proaktiv etwas Visuelles zeigen willst, zusätzlich "
    "zu oder statt einer Textantwort — z.B. wenn Timo mehrere Dinge gleichzeitig sehen will.",
    {
        "widget_type": {"type": "string", "description": "Widget-Typ, aktuell verfügbar: 'sleep'"},
        "slot": {"type": "string", "description": "Ziel-Slot im aktuellen Layout, Standard 'main'"},
    },
    ["widget_type"], "ui")
async def _show_widget(widget_type: str, slot: str = "main"):
    builder = _PAYLOAD_BUILDERS.get(widget_type)
    if builder is None:
        return f"FEHLER: Unbekannter Widget-Typ '{widget_type}'. Verfügbar: {', '.join(_PAYLOAD_BUILDERS)}."
    from core.container import services
    dash = services.get("dashboard")
    if dash is None:
        return "FEHLER: Dashboard nicht verfügbar."
    payload = builder(dash)
    UI_BUS.show_widget(widget_type, payload, slot=slot)
    return f"Widget '{widget_type}' wird jetzt im Slot '{slot}' angezeigt."


@T.register("arrange_screen",
    "Legt fest, welche Bildschirm-Anordnung (Layout-Vorlage) gerade genutzt wird — nutze dies "
    "wenn mehrere Dinge gleichzeitig sichtbar sein sollen, statt nacheinander.",
    {"layout": {"type": "string", "description": f"Eine von: {', '.join(LAYOUT_PRESETS)}"}},
    ["layout"], "ui")
async def _arrange_screen(layout: str):
    try:
        UI_BUS.arrange_screen(layout)
    except ValueError as e:
        return f"FEHLER: {e}"
    return f"Layout auf '{layout}' gesetzt."


@T.register("close_widget",
    "Schließt ein angezeigtes Widget wieder (z.B. wenn Timo fertig damit ist).",
    {"slot": {"type": "string", "description": "Slot der geschlossen werden soll, Standard 'main'"}},
    [], "ui")
async def _close_widget(slot: str = "main"):
    UI_BUS.close_widget(slot)
    return f"Widget im Slot '{slot}' geschlossen."
```

In `core/skills/__init__.py`, im bestehenden Import-Block (aktuell Zeilen 9-21):

```python
from . import (
    knowledge,
    memory,
    productivity,
    health,
    habits,
    fitness,
    nutrition,
    journal,
    goals,
    utility,
    system,
    general,
    ui,
)
```

(`ui` einfach als letzten Eintrag ergänzen — die `_ORDER`-Liste weiter unten in derselben Datei
NICHT anfassen: neue Tools, die dort nicht aufgeführt sind, hängen sich automatisch ans Ende der
Registry, das ist bereits im bestehenden Code so vorgesehen.)

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_skills.py -v`
Expected: PASS (6 Tests)

Zusätzlich die komplette bestehende Suite laufen lassen:

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle Tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add core/skills/ui.py core/skills/__init__.py tests/test_ui_skills.py
git commit -m "feat(ui-tools): explizite Agent-Tools show_widget/arrange_screen/close_widget

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — `UiEvent`-Typ auf Multi-Slot migrieren

**Files:**
- Modify: `apps/desktop/src/ui-state-client.ts` (Typ-Definitionen, Rest unverändert)
- Modify: `apps/desktop/src/ui-state-client.test.ts` (Test-Fixtures auf neue Shape anpassen)

**Interfaces:**
- Produces:
  - `type SleepNight = { date: string; hours: number | null; deep_hours: number | null }`
  - `type WidgetSlot = { widget: string; payload: { nights: SleepNight[] } }`
  - `type UiEvent = { layout: string | null; slots: Record<string, WidgetSlot>; ts?: number }`
  - `subscribeUiState(...)`-Funktionssignatur bleibt unverändert (nur der generische `UiEvent`-Typ ändert sich)

- [ ] **Step 1: Test-Fixtures auf neue Shape anpassen — `apps/desktop/src/ui-state-client.test.ts` komplett ersetzen**

```typescript
import { describe, it, expect, vi } from 'vitest';
import { subscribeUiState } from './ui-state-client';
import type { EventSourceLike, UiEvent } from './ui-state-client';

class FakeEventSource implements EventSourceLike {
  onmessage: ((ev: { data: string }) => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  emit(data: object): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  close(): void {
    this.closed = true;
  }
}

describe('subscribeUiState', () => {
  it('verbindet sich mit der korrekten SSE-URL', () => {
    let created: FakeEventSource | null = null;
    const factory = (url: string) => (created = new FakeEventSource(url));
    subscribeUiState('http://test:7779', () => {}, factory);
    expect(created!.url).toBe('http://test:7779/api/ui/stream');
  });

  it('leitet eingehende Multi-Slot-Events an den Callback weiter', () => {
    let received: UiEvent | null = null;
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeUiState('http://test:7779', (evt) => { received = evt; }, factory);

    source!.emit({
      layout: 'single',
      slots: { main: { widget: 'sleep', payload: { nights: [{ date: '2026-07-04', hours: 7.2, deep_hours: 1.1 }] } } },
      ts: 123,
    });

    expect(received).toEqual({
      layout: 'single',
      slots: { main: { widget: 'sleep', payload: { nights: [{ date: '2026-07-04', hours: 7.2, deep_hours: 1.1 }] } } },
      ts: 123,
    });
  });

  it('ignoriert kaputtes JSON ohne zu werfen', () => {
    const onEvent = vi.fn();
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeUiState('http://test:7779', onEvent, factory);

    source!.onmessage?.({ data: 'kein-json{{{' });

    expect(onEvent).not.toHaveBeenCalled();
  });

  it('unsubscribe schließt die Verbindung', () => {
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    const unsubscribe = subscribeUiState('http://test:7779', () => {}, factory);

    unsubscribe();

    expect(source!.closed).toBe(true);
  });
});
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd apps/desktop && npm test`
Expected: FAIL — Typfehler/Assertion, da `ui-state-client.ts` noch die alte
`{ widget, payload, ts }`-Shape exportiert.

- [ ] **Step 3: `apps/desktop/src/ui-state-client.ts` — nur den Typ-Block ersetzen**

Ersetze in `apps/desktop/src/ui-state-client.ts` die bestehenden Zeilen:

```typescript
export type SleepNight = { date: string; hours: number | null; deep_hours: number | null };
export type UiEvent = { widget: string | null; payload?: { nights: SleepNight[] }; ts?: number };
```

durch:

```typescript
export type SleepNight = { date: string; hours: number | null; deep_hours: number | null };
export type WidgetSlot = { widget: string; payload: { nights: SleepNight[] } };
export type UiEvent = { layout: string | null; slots: Record<string, WidgetSlot>; ts?: number };
```

Der Rest der Datei (`EventSourceLike`, `defaultEsFactory`, `subscribeUiState`) bleibt
unverändert — die Funktion selbst kennt die konkrete Struktur von `UiEvent` nicht, sie parst nur
generisches JSON und reicht es typisiert durch.

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd apps/desktop && npm test`
Expected: PASS (4 Tests in dieser Datei, 17 gesamt: 13 aus Phase 1+2 + 4 hier, minus die Differenz
durch reine Umbenennung der Fixtures — die Testanzahl bleibt bei 4 Tests in dieser Datei, Gesamtzahl
im Projekt unverändert bei 13)

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/ui-state-client.ts apps/desktop/src/ui-state-client.test.ts
git commit -m "feat(desktop): UiEvent-Typ auf Multi-Slot-Layout migrieren

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Multi-Slot-Rendering im Frontend + Live-Verifikation

**Files:**
- Modify: `apps/desktop/index.html`
- Modify: `apps/desktop/src/style.css`
- Modify: `apps/desktop/src/main.ts` (kompletter Ersatz)

**Interfaces:**
- Consumes: `subscribeUiState(baseUrl, onEvent)` + `UiEvent`/`WidgetSlot` aus `./ui-state-client`
  (Task 3), `getBaseUrl()` aus `./config`, `checkBackendHealth()` aus `./backend`,
  `deriveHudState()` aus `./hud-state` (alle aus Phase 1 unverändert)
- Produces: rendert je nach `evt.layout` ein Grid mit den passenden Slots (`single` = 1 Spalte,
  `split2` = 2 Spalten nebeneinander); ein Slot ohne zugewiesenes Widget zeigt einen leeren
  Platzhalter; bei `layout: null` erscheint wieder der Ruhezustand-HUD-Ring.

- [ ] **Step 1: `apps/desktop/index.html` — Widget-Container generisch machen**

Ersetze den bestehenden `<div id="widget-sleep">`-Block (aus Phase 2) im `<body>` durch:

```html
  <body>
    <div id="hud">
      <div id="hud-ring"></div>
      <div id="hud-label"></div>
      <div id="hud-status"></div>
    </div>
    <div id="widget-area" style="display:none"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
```

- [ ] **Step 2: `apps/desktop/src/style.css` — alte Sleep-Widget-Regeln durch generische
  Slot-/Layout-Regeln ersetzen**

Entferne die bestehenden Regeln für `.widget`, `.widget-title`, `#widget-sleep-bars`, `.sleep-bar`
(aus Phase 2, am Ende der Datei) und ersetze sie durch:

```css
#widget-area {
  position: absolute;
  inset: 0;
  background: #04070d;
  display: grid;
  gap: 12px;
  padding: 20px;
  box-sizing: border-box;
}

#widget-area.layout-single {
  grid-template-columns: 1fr;
}

#widget-area.layout-split2 {
  grid-template-columns: 1fr 1fr;
}

.widget-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  border: 1px solid #00e5ff22;
  border-radius: 8px;
}

.widget-title {
  font-size: 11px;
  letter-spacing: 0.5px;
  color: #00e5ff;
  text-transform: uppercase;
  opacity: 0.7;
}

.sleep-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 120px;
}

.sleep-bar {
  width: 20px;
  background: linear-gradient(#00e5ff, #00e5ff33);
  border-radius: 3px;
  min-height: 4px;
}
```

- [ ] **Step 3: `apps/desktop/src/main.ts` komplett ersetzen**

```typescript
import { getBaseUrl } from './config';
import { checkBackendHealth } from './backend';
import { deriveHudState } from './hud-state';
import { subscribeUiState } from './ui-state-client';
import type { UiEvent, SleepNight } from './ui-state-client';

const POLL_INTERVAL_MS = 10_000;

// Spiegelt core/ui_state.py::LAYOUT_PRESETS — bewusste Duplikation über die
// Sprachgrenze, da es keine Codegen-Infrastruktur zwischen Backend und
// Frontend gibt (siehe Plan-Nicht-Ziele).
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

function renderSleepWidget(container: HTMLElement, nights: SleepNight[]): void {
  const maxHours = Math.max(1, ...nights.map((n) => n.hours ?? 0));
  const bars = nights
    .map((n) => {
      const heightPx = Math.round(((n.hours ?? 0) / maxHours) * 120);
      return `<div class="sleep-bar" style="height:${heightPx}px" title="${n.date}: ${n.hours ?? '–'}h"></div>`;
    })
    .join('');
  container.innerHTML = `<div class="widget-title">Schlaf — letzte Nächte</div><div class="sleep-bars">${bars}</div>`;
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
    if (slot && slot.widget === 'sleep') {
      renderSleepWidget(slotEl, slot.payload.nights);
    } else {
      slotEl.innerHTML = '<div class="widget-title">leer</div>';
    }
  }
}

renderHud();
setInterval(renderHud, POLL_INTERVAL_MS);
subscribeUiState(getBaseUrl(), applyUiEvent);
```

- [ ] **Step 4: Lokale Tests + Type-Check ausführen**

Run: `cd apps/desktop && npm test && npx tsc --noEmit`
Expected: alle Tests PASS (13 gesamt), `tsc` ohne Ausgabe (Exit 0)

- [ ] **Step 5: Manuell gegen den echten laufenden Alfred-Backend-Prozess verifizieren**

Backend-Änderungen aus Task 1+2 sind noch nicht im laufenden Prozess geladen — sicherer Neustart:

```bash
kill $(cat /tmp/alfred.pid) 2>/dev/null
sleep 3
launchctl kickstart -k gui/501/com.alfred.assistant
for i in $(seq 1 20); do sleep 3; code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:7779/health); if [ "$code" = "200" ]; then echo "OK nach $((i*3))s"; break; fi; done
curl -s http://localhost:7779/api/ui/current
```

Erwartet: `{"layout":null,"slots":{},"ts":...}` (neue Shape, Ruhezustand).

Dann einen echten Chat-Turn mit Schlaf-Bezug auslösen (bestehender, verlässlicher Pfad über
`maybe_update_ui`):

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" \
  -d '{"text":"Wie war mein Schlaf die letzten Tage?"}'
curl -s http://localhost:7779/api/ui/current
```

Erwartet: `/api/ui/current` liefert jetzt `{"layout":"single","slots":{"main":{"widget":"sleep",
"payload":{...}}},"ts":...}` — bestätigt die neue Shape end-to-end (Backend-Migration korrekt).

Optional (Best-Effort, LLM-Verhalten ist nicht 100% deterministisch — falls nicht wie erwartet
reagiert, im Bericht dokumentieren statt als Fehlschlag werten): einen Chat-Turn senden, der
explizit auf die neuen Tools hindeutet, z.B.:

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" \
  -d '{"text":"Nutze das arrange_screen Tool und stelle das Layout auf split2."}'
curl -s http://localhost:7779/api/ui/current
```

Erwartet (falls das LLM das Tool wählt): `"layout":"split2"` in der Antwort.

Danach im Tauri-Fenster (`npm run tauri dev`, im Hintergrund starten, kurz prüfen, sauber
beenden) bestätigen, dass sich der Ruhezustand-Ring bei aktivem Widget-Zustand ausblendet und
der Sleep-Widget-Slot erscheint.

- [ ] **Step 6: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/index.html apps/desktop/src/style.css apps/desktop/src/main.ts
git commit -m "feat(desktop): Multi-Slot-Layout-Rendering (single/split2)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec-Abdeckung (verkleinerter Phase-3-Schnitt aus Abschnitt 4+6 der Spec):**
- Begrenztes Set an Layout-Vorlagen, Alfred wählt kontextabhängig: Task 1 (`LAYOUT_PRESETS`,
  `arrange_screen`) → erfüllt.
- Explizite UI-Tools (`show_widget`/`arrange_screen`/`close_widget`) als normale Agent-Tools:
  Task 2 → erfüllt.
- Mehrere Widgets gleichzeitig sichtbar (Multi-Slot): Task 1 (Backend-Zustand) + Task 4
  (Frontend-Rendering) → erfüllt.
- Volle Widget-Bibliothek, Hover-to-Expand, versteckte Navigation, Sprachsteuerung: bewusst NICHT
  Teil dieses Plans (eigene, spätere Phasen).

**Platzhalter-Scan:** Keine TBD/TODO, jeder Schritt enthält vollständigen Code oder exakte
Befehle mit erwarteter Ausgabe.

**Typ-Konsistenz:** `UI_BUS.current`-Shape (`{"layout", "slots", "ts"}`, Task 1) wird identisch
in Task 2 (`ui_skills`-Tests), Task 3 (`UiEvent`-TS-Typ) und Task 4 (`main.ts`-Rendering)
verwendet. `LAYOUT_PRESETS`-Schlüssel (`"single"`, `"split2"`, Task 1) sind deckungsgleich mit
`LAYOUT_SLOTS` in `main.ts` (Task 4) und der Layout-Beschreibung im `arrange_screen`-Tool
(Task 2).

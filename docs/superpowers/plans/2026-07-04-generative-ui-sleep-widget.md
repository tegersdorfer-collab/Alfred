# Generatives UI — Erster Widget-Durchstich (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Einmal komplett end-to-end beweisen, dass ein normaler Tool-Aufruf im Agent-Loop (`get_health`) automatisch ein Widget (Schlaf-Graph) im Tauri-Desktop-Client erscheinen lässt — über einen neuen UI-State-SSE-Kanal, ohne Layout-Vorlagen oder explizite UI-Tools (folgen in Phase 3).

**Architecture:** Deterministische Tool→Widget-Zuordnung (kein Extra-LLM-Call) in einem neuen
`core/ui_state.py`-Modul, das denselben Publish/Subscribe-Stil wie die bestehende `core/status.py`
(`StatusBus`) nutzt. Nach jedem Agent-Turn prüft der `MessageHandler`, ob ein Tool im Trace
einem Widget zugeordnet ist, holt bei Treffer strukturierte Daten (unabhängig vom
LLM-Text-Ergebnis des Tools) und pusht sie über einen neuen SSE-Endpunkt. Der Tauri-Client
abonniert diesen Kanal und rendert bei Treffer ein Schlaf-Widget statt des Ruhezustand-Rings.

**Tech Stack:** Python/FastAPI/asyncio (Backend, wie bestehender Alfred-Code), TypeScript/Vitest
(Frontend, wie apps/desktop aus Phase 1).

## Global Constraints

- Einziger Tool→Widget-Eintrag in dieser Phase: `get_health` → Widget-Typ `"sleep"` (weitere
  Zuordnungen folgen in Phase 3 mit der vollen Widget-Bibliothek).
- Das bestehende Tool `get_health` (core/skills/health.py) wird NICHT verändert — es liefert
  weiterhin nur einen formatierten String für das LLM. Die strukturierten Widget-Daten werden
  unabhängig davon direkt aus `DashboardReader.get_recent_health()` (tools/dashboard.py) gebaut.
- Zugriff auf die Dashboard-Instanz erfolgt über den bestehenden Service-Locator:
  `from core.container import services; dash = services.get("dashboard")` (bereits als
  `"dashboard"` registriert in `orchestrator.py::_register_services`).
- Phase 2 kennt genau EINEN aktiven Widget-Slot (kein Layout-System) — `UIStateBus.current` ist
  `None` oder genau ein `{"widget": str, "payload": dict, "ts": float}`-Dict.
- UI-Updates dürfen NIEMALS einen Chat-Turn zum Absturz bringen — jeder Aufruf aus dem
  Message-Handling-Pfad heraus ist try/except-geschützt (Muster wie an anderen Stellen im
  Code, z.B. `core/message_handler.py::_check_verification_bump`).
- Optik folgt weiterhin dem Holographic-HUD-Stil aus Phase 1: Cyan `#00e5ff` auf `#04070d`,
  Monospace-Akzentschrift.

---

### Task 1: `core/ui_state.py` — Widget-Zuordnung + strukturierte Schlaf-Daten

**Files:**
- Create: `core/ui_state.py`
- Test: `tests/test_ui_state_mapping.py`

**Interfaces:**
- Produces:
  - `WIDGET_MAP: dict[str, str]`
  - `widget_type_for_tool(tool_name: str) -> str | None`
  - `sleep_widget_payload(dashboard, days: int = 7) -> dict` — Rückgabe:
    `{"widget": "sleep", "nights": [{"date": "YYYY-MM-DD", "hours": float | None, "deep_hours": float | None}, ...]}`
    (neueste Nacht zuletzt in der Liste, wie `get_recent_health` sie liefert)

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_ui_state_mapping.py`:

```python
"""Unit-Tests für core/ui_state.py: Tool→Widget-Zuordnung + Schlaf-Daten-Shaping."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from types import SimpleNamespace

from core.ui_state import WIDGET_MAP, widget_type_for_tool, sleep_widget_payload


class TestWidgetTypeForTool:
    def test_get_health_mappt_auf_sleep(self):
        assert widget_type_for_tool("get_health") == "sleep"

    def test_unbekanntes_tool_liefert_none(self):
        assert widget_type_for_tool("create_task") is None

    def test_widget_map_enthaelt_nur_get_health(self):
        # Phase 2: bewusst nur EIN Eintrag, Rest folgt in Phase 3
        assert WIDGET_MAP == {"get_health": "sleep"}


def _fake_health_row(d, hours, deep):
    return SimpleNamespace(date=d, sleep_duration=hours, sleep_deep=deep)


class FakeDashboard:
    def __init__(self, rows):
        self._rows = rows

    def get_recent_health(self, days=7):
        return self._rows


class TestSleepWidgetPayload:
    def test_formt_naechte_aus_health_summaries(self):
        dash = FakeDashboard([
            _fake_health_row(date(2026, 7, 2), 7.5, 1.2),
            _fake_health_row(date(2026, 7, 3), 6.8, 0.9),
        ])
        payload = sleep_widget_payload(dash, days=7)
        assert payload == {
            "widget": "sleep",
            "nights": [
                {"date": "2026-07-02", "hours": 7.5, "deep_hours": 1.2},
                {"date": "2026-07-03", "hours": 6.8, "deep_hours": 0.9},
            ],
        }

    def test_fehlende_werte_bleiben_none(self):
        dash = FakeDashboard([_fake_health_row(date(2026, 7, 4), None, None)])
        payload = sleep_widget_payload(dash, days=7)
        assert payload["nights"] == [{"date": "2026-07-04", "hours": None, "deep_hours": None}]

    def test_keine_daten_liefert_leere_liste(self):
        dash = FakeDashboard([])
        payload = sleep_widget_payload(dash, days=7)
        assert payload == {"widget": "sleep", "nights": []}

    def test_days_wird_durchgereicht(self):
        calls = []

        class RecordingDashboard:
            def get_recent_health(self, days=7):
                calls.append(days)
                return []

        sleep_widget_payload(RecordingDashboard(), days=14)
        assert calls == [14]
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.ui_state'`

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `core/ui_state.py`:

```python
"""
UI-State — Grundlage des generativen UI (Phase 2, erster Durchstich).

Ordnet Tool-Aufrufe aus dem Agent-Trace deterministisch Widget-Typen zu (kein
Extra-LLM-Call) und hält den aktuell aktiven Widget-Slot. Publish/Subscribe
im selben Stil wie core/status.py::StatusBus — ein neuer, eigener Bus statt
Wiederverwendung von StatusBus, weil UI-State ein MATERIALISIERTER Zustand
ist (ein neu verbindender Client braucht den aktuellen Slot sofort), nicht
nur ein Ereignis-Strom.
"""
import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Tool-Name → Widget-Typ. Phase 2: bewusst nur ein Eintrag, Rest folgt in
# Phase 3 mit der vollen Widget-Bibliothek + Layout-Vorlagen.
WIDGET_MAP: dict[str, str] = {
    "get_health": "sleep",
}


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
    """Hält den aktuell aktiven Widget-Slot + Live-Updates für SSE-Subscriber."""

    def __init__(self) -> None:
        self._current: dict | None = None
        self._listeners: list[asyncio.Queue] = []

    @property
    def current(self) -> dict | None:
        return self._current

    def show_widget(self, widget_type: str, payload: dict) -> None:
        evt = {"widget": widget_type, "payload": payload, "ts": time.time()}
        self._current = evt
        self._broadcast(evt)

    def clear(self) -> None:
        self._current = None
        self._broadcast({"widget": None})

    def _broadcast(self, evt: dict) -> None:
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
    Widget zugeordnet ist, baut bei Treffer die Daten und pusht sie.
    Fehler werden geschluckt — UI-Updates dürfen nie einen Chat-Turn brechen."""
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
                UI_BUS.show_widget("sleep", payload)
            return  # Phase 2: genau ein Slot — erstes Match gewinnt
        except Exception as e:
            log.debug(f"maybe_update_ui fehlgeschlagen für '{tool_name}': {e}")
            return
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_mapping.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add core/ui_state.py tests/test_ui_state_mapping.py
git commit -m "feat(ui-state): Tool-zu-Widget-Zuordnung + Schlaf-Daten-Shaping

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `UIStateBus` Publish/Subscribe testen

**Files:**
- Modify: `tests/test_ui_state_mapping.py` → NEIN, eigene Datei für Bus-Verhalten
- Create: `tests/test_ui_state_bus.py`

**Interfaces:**
- Consumes: `UIStateBus` aus `core.ui_state` (Task 1)
- Produces: nichts Neues — reine Testabdeckung für bereits in Task 1 geschriebenen Code, der
  dort noch nicht gegen `subscribe`/`show_widget`/`clear` getestet wurde.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_ui_state_bus.py`:

```python
"""Unit-Tests für core/ui_state.py::UIStateBus (Publish/Subscribe, kein DB nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from core.ui_state import UIStateBus


class TestUIStateBus:
    def test_initial_current_ist_none(self):
        bus = UIStateBus()
        assert bus.current is None

    def test_show_widget_setzt_current(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        assert bus.current["widget"] == "sleep"
        assert bus.current["payload"] == {"nights": []}
        assert "ts" in bus.current

    def test_clear_setzt_current_zurueck(self):
        bus = UIStateBus()
        bus.show_widget("sleep", {"nights": []})
        bus.clear()
        assert bus.current is None

    def test_subscriber_bekommt_show_widget_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.show_widget("sleep", {"nights": []})
            evt = q.get_nowait()
            assert evt["widget"] == "sleep"

        asyncio.run(run())

    def test_subscriber_bekommt_clear_event(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            bus.clear()
            evt = q.get_nowait()
            assert evt == {"widget": None}

        asyncio.run(run())

    def test_unsubscribe_entfernt_listener(self):
        bus = UIStateBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.show_widget("sleep", {"nights": []})
        assert q.empty()

    def test_unsubscribe_unbekannte_queue_wirft_nicht(self):
        bus = UIStateBus()
        bus.unsubscribe(asyncio.Queue())  # nie subscribed — darf nicht crashen

    def test_volle_queue_verwirft_event_statt_zu_blockieren(self):
        async def run():
            bus = UIStateBus()
            q = bus.subscribe()
            for i in range(60):  # maxsize=50 — Queue läuft über
                bus.show_widget("sleep", {"night": i})
            assert q.full()

        asyncio.run(run())
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_bus.py -v`
Expected: Da `UIStateBus` bereits in Task 1 vollständig implementiert wurde, sollten diese Tests
direkt PASSEN. Führe den Lauf trotzdem aus, um das zu bestätigen (kein Fehlschlag erwartet,
weil die Implementierung bereits existiert — das ist bei diesem Task in Ordnung, da er reine
Testabdeckung für bereits geschriebenen Code nachträgt).

- [ ] **Step 3: Bei unerwartetem Fehlschlag: Implementierung in `core/ui_state.py` prüfen**

Falls ein Test fehlschlägt, liegt es an `UIStateBus` in `core/ui_state.py` (Task 1) — korrigiere
dort, nicht in der Testdatei.

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_bus.py -v`
Expected: PASS (8 Tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add tests/test_ui_state_bus.py
git commit -m "test(ui-state): Publish/Subscribe-Verhalten von UIStateBus abdecken

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `maybe_update_ui` in den MessageHandler verkabeln

**Files:**
- Modify: `core/message_handler.py`
- Test: `tests/test_message_handler_ui_wiring.py`

**Interfaces:**
- Consumes: `maybe_update_ui(tools_used: list[str]) -> None` aus `core.ui_state` (Task 1)
- Produces: `MessageHandler.handle()` und `MessageHandler.dashboard_respond()` rufen nach
  Ermittlung von `tools_used` zusätzlich `ui_state.maybe_update_ui(tools_used)` auf.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_message_handler_ui_wiring.py`:

```python
"""Testet, dass MessageHandler nach jedem Turn maybe_update_ui aufruft
(reine Verkabelungs-Prüfung, keine echten Collaborators nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.message_handler import MessageHandler


def _make_handler():
    agent = MagicMock()
    agent.run = AsyncMock(return_value=(
        "Du hast 7.2h geschlafen.",
        [{"tool": "get_health", "args": {}, "result": "..."}],
    ))
    agent.model_name = "test-model"

    prompt_builder = MagicMock()
    prompt_builder.build = AsyncMock(return_value="system prompt")

    kzg = MagicMock()
    kzg.add = MagicMock()

    lzg = MagicMock()
    lzg.save_kzg_turn = MagicMock()

    return MessageHandler(
        kzg=kzg, lzg=lzg, agent=agent, prompt_builder=prompt_builder,
        channel=MagicMock(), proactive_tracker=MagicMock(),
        forgetting=MagicMock(), extractor=MagicMock(), bg_llm=MagicMock(),
        alphaprogression=MagicMock(), on_user_active=MagicMock(),
    )


class TestDashboardRespondUiWiring:
    def test_ruft_maybe_update_ui_mit_genutzten_tools_auf(self):
        handler = _make_handler()
        with patch("core.message_handler.ui_state.maybe_update_ui") as mock_update:
            with patch("core.message_handler.db"):  # DB-Persistenz überspringen
                asyncio.run(handler.dashboard_respond("Wie war mein Schlaf?"))
            mock_update.assert_called_once_with(["get_health"])

    def test_kein_absturz_wenn_maybe_update_ui_fehlschlaegt(self):
        handler = _make_handler()
        with patch("core.message_handler.ui_state.maybe_update_ui",
                   side_effect=RuntimeError("kaputt")):
            with patch("core.message_handler.db"):
                # darf keine Exception nach außen werfen
                response, trace = asyncio.run(handler.dashboard_respond("Wie war mein Schlaf?"))
                assert response == "Du hast 7.2h geschlafen."
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_message_handler_ui_wiring.py -v`
Expected: FAIL — `AttributeError` oder `AssertionError: Expected 'maybe_update_ui' to have been
called once. Called 0 times.` (noch nicht verkabelt), ggf. `ModuleNotFoundError` falls `ui_state`
noch nicht in `core/message_handler.py` importiert ist.

- [ ] **Step 3: Minimale Implementierung schreiben**

In `core/message_handler.py`, Import ergänzen (nach der bestehenden `from core import skills, db`-Zeile):

```python
from core import skills, db, ui_state
```

In `dashboard_respond()`, direkt nach der Zeile `tools_used = [t["tool"] for t in trace]`
(im bestehenden Methodenkörper, kurz vor `self._persist_msg("assistant", ...)`) ergänzen:

```python
        tools_used = [t["tool"] for t in trace]
        try:
            ui_state.maybe_update_ui(tools_used)
        except Exception:
            pass
```

Dieselbe Ergänzung — direkt nach der bestehenden `tools_used = [t["tool"] for t in trace]`-Zeile
— auch in `handle()` vornehmen (dort existiert dieselbe Zeile bereits, kurz vor dem
`self._persist_msg("assistant", ...)`-Aufruf für den Telegram-Pfad).

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_message_handler_ui_wiring.py -v`
Expected: PASS (2 Tests)

Zusätzlich die komplette bestehende Suite laufen lassen, um sicherzustellen, dass nichts
anderes gebrochen ist:

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle Tests PASS (bestehende 189 + die neuen aus Task 1-3)

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add core/message_handler.py tests/test_message_handler_ui_wiring.py
git commit -m "feat(message-handler): UI-State nach jedem Agent-Turn aktualisieren

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: SSE-Endpunkt `/api/ui/stream` + `/api/ui/current`

**Files:**
- Create: `web/routers/ui_state.py`
- Modify: `web/routers/__init__.py`
- Test: `tests/test_ui_state_router.py`

**Interfaces:**
- Consumes: `UI_BUS` (Singleton) aus `core.ui_state` (Task 1)
- Produces: `GET /api/ui/current` (JSON), `GET /api/ui/stream` (SSE) — beide über
  `build_router(orch=None) -> APIRouter`, registriert in `ROUTER_MODULES`.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_ui_state_router.py`:

```python
"""Testet den /api/ui/current-Endpunkt über einen echten FastAPI-TestClient
(SSE-Streaming selbst wird per manueller curl-Verifikation in Task 4 geprüft,
nicht hier — blockierende Generatoren sind mit TestClient unhandlich)."""
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
    def test_liefert_none_widget_wenn_kein_zustand(self):
        UI_BUS._current = None
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        assert resp.json() == {"widget": None}

    def test_liefert_aktuellen_widget_zustand(self):
        UI_BUS.show_widget("sleep", {"nights": []})
        client = _make_client()
        resp = client.get("/api/ui/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["widget"] == "sleep"
        assert body["payload"] == {"nights": []}
        UI_BUS.clear()  # Zustand für andere Tests zurücksetzen
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.routers.ui_state'`

(Falls `fastapi.testclient`/`httpx` nicht installiert ist: `pip install httpx` — wird von
FastAPIs TestClient vorausgesetzt; im bestehenden `requirements.txt` ist `httpx` bereits als
Abhängigkeit gelistet, sollte also vorhanden sein.)

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `web/routers/ui_state.py`:

```python
"""
UI-State — API-Router. Neuer SSE-Kanal für das generative UI (Phase 2).
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
        return UI_BUS.current or {"widget": None}

    @router.get("/api/ui/stream")
    async def ui_stream():
        q = UI_BUS.subscribe()

        async def gen():
            try:
                yield f"data: {json.dumps(UI_BUS.current or {'widget': None})}\n\n"
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

In `web/routers/__init__.py` ergänzen:

```python
from . import brain, calendar, chat, fitness, goals, habits, health, insights, journal, knowledge, meta, nutrition, system, tasks, ui_state

ROUTER_MODULES = [
    brain,
    calendar,
    chat,
    fitness,
    goals,
    habits,
    health,
    insights,
    journal,
    knowledge,
    meta,
    nutrition,
    system,
    tasks,
    ui_state,
]
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_ui_state_router.py -v`
Expected: PASS (2 Tests)

- [ ] **Step 5: Manuell gegen den echten laufenden Alfred-Backend-Prozess verifizieren**

Alfred läuft bereits (Port 7779). Nach dem Neustart (nötig, damit der neue Router geladen wird):

```bash
kill $(cat /tmp/alfred.pid)
sleep 3
launchctl kickstart -k gui/501/com.alfred.assistant
# pollen bis /health wieder 200 liefert:
for i in $(seq 1 20); do sleep 3; code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:7779/health); if [ "$code" = "200" ]; then echo "OK nach $((i*3))s"; break; fi; done
curl -s http://localhost:7779/api/ui/current
```

Erwartet: `{"widget":null}` (noch kein Widget ausgelöst).

Danach einen echten Chat-Turn mit Schlaf-Bezug auslösen (löst `get_health` aus):

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" \
  -d '{"text":"Wie war mein Schlaf die letzten Tage?"}'
curl -s http://localhost:7779/api/ui/current
```

Erwartet: `/api/ui/current` liefert jetzt `{"widget":"sleep","payload":{"nights":[...]},"ts":...}`.

- [ ] **Step 6: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add web/routers/ui_state.py web/routers/__init__.py tests/test_ui_state_router.py
git commit -m "feat(web): UI-State SSE-Endpunkt (/api/ui/stream, /api/ui/current)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — UI-State-Client (Tauri)

**Files:**
- Create: `apps/desktop/src/ui-state-client.ts`
- Test: `apps/desktop/src/ui-state-client.test.ts`

**Interfaces:**
- Consumes: `getBaseUrl()` aus `./config` (Phase 1)
- Produces:
  - `type SleepNight = { date: string; hours: number | null; deep_hours: number | null }`
  - `type UiEvent = { widget: string | null; payload?: { nights: SleepNight[] }; ts?: number }`
  - `type EventSourceLike = { onmessage: ((ev: { data: string }) => void) | null; close(): void }`
  - `subscribeUiState(baseUrl: string, onEvent: (evt: UiEvent) => void, esFactory?: (url: string) => EventSourceLike): () => void`
    — gibt eine Unsubscribe-Funktion zurück, die die zugrunde liegende Verbindung schließt.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `apps/desktop/src/ui-state-client.test.ts`:

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

  it('leitet eingehende Events an den Callback weiter', () => {
    let received: UiEvent | null = null;
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeUiState('http://test:7779', (evt) => { received = evt; }, factory);

    source!.emit({ widget: 'sleep', payload: { nights: [{ date: '2026-07-04', hours: 7.2, deep_hours: 1.1 }] } });

    expect(received).toEqual({
      widget: 'sleep',
      payload: { nights: [{ date: '2026-07-04', hours: 7.2, deep_hours: 1.1 }] },
    });
  });

  it('ignoriert kaputtes JSON ohne zu werfen', () => {
    const onEvent = vi.fn();
    let source: FakeEventSource | null = null;
    const factory = (url: string) => (source = new FakeEventSource(url));
    subscribeUiState('http://test:7779', onEvent, factory);

    expect(() => source!.emit as any).not.toThrow();
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
Expected: FAIL — `Cannot find module './ui-state-client'`

- [ ] **Step 3: Minimale Implementierung schreiben**

Datei `apps/desktop/src/ui-state-client.ts`:

```typescript
export type SleepNight = { date: string; hours: number | null; deep_hours: number | null };
export type UiEvent = { widget: string | null; payload?: { nights: SleepNight[] }; ts?: number };

export type EventSourceLike = {
  onmessage: ((ev: { data: string }) => void) | null;
  close(): void;
};

function defaultEsFactory(url: string): EventSourceLike {
  return new EventSource(url) as unknown as EventSourceLike;
}

export function subscribeUiState(
  baseUrl: string,
  onEvent: (evt: UiEvent) => void,
  esFactory: (url: string) => EventSourceLike = defaultEsFactory,
): () => void {
  const source = esFactory(`${baseUrl}/api/ui/stream`);

  source.onmessage = (ev) => {
    try {
      const parsed = JSON.parse(ev.data);
      onEvent(parsed as UiEvent);
    } catch {
      // Kaputtes/Keepalive-Event ignorieren, Verbindung bleibt bestehen
    }
  };

  return () => source.close();
}
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd apps/desktop && npm test`
Expected: PASS (4 neue Tests + alle bestehenden 9 aus Phase 1 = 13 gesamt)

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/ui-state-client.ts apps/desktop/src/ui-state-client.test.ts
git commit -m "feat(desktop): UI-State-SSE-Client (injizierbare EventSource für Tests)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Sleep-Widget rendern + HUD ersetzen

**Files:**
- Modify: `apps/desktop/src/main.ts`
- Modify: `apps/desktop/index.html`
- Modify: `apps/desktop/src/style.css`

**Interfaces:**
- Consumes: `subscribeUiState(baseUrl, onEvent)` aus `./ui-state-client` (Task 5),
  `getBaseUrl()` aus `./config` (Phase 1)
- Produces: Wenn ein `UiEvent` mit `widget: "sleep"` ankommt, ersetzt das Sleep-Widget
  (Balken pro Nacht) den Ruhezustand-Ring; bei `widget: null` erscheint wieder der Ring.

- [ ] **Step 1: HTML um einen Widget-Container ergänzen**

In `apps/desktop/index.html`, den bestehenden `<div id="hud">`-Block um einen Geschwister-Container
ergänzen (Ersatz des gesamten `<body>`-Inhalts):

```html
  <body>
    <div id="hud">
      <div id="hud-ring"></div>
      <div id="hud-label"></div>
      <div id="hud-status"></div>
    </div>
    <div id="widget-sleep" class="widget" style="display:none">
      <div class="widget-title">Schlaf — letzte Nächte</div>
      <div id="widget-sleep-bars"></div>
    </div>
    <script type="module" src="/src/main.ts"></script>
  </body>
```

- [ ] **Step 2: CSS für das Widget ergänzen**

In `apps/desktop/src/style.css` anhängen:

```css
.widget {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  background: #04070d;
}

.widget-title {
  font-size: 11px;
  letter-spacing: 0.5px;
  color: #00e5ff;
  text-transform: uppercase;
  opacity: 0.7;
}

#widget-sleep-bars {
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

- [ ] **Step 3: main.ts um Widget-Rendering + SSE-Subscription erweitern**

Datei `apps/desktop/src/main.ts` komplett ersetzen:

```typescript
import { getBaseUrl } from './config';
import { checkBackendHealth } from './backend';
import { deriveHudState } from './hud-state';
import { subscribeUiState } from './ui-state-client';
import type { UiEvent, SleepNight } from './ui-state-client';

const POLL_INTERVAL_MS = 10_000;

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

function renderSleepWidget(nights: SleepNight[]): void {
  const bars = document.getElementById('widget-sleep-bars')!;
  const maxHours = Math.max(1, ...nights.map((n) => n.hours ?? 0));
  bars.innerHTML = nights
    .map((n) => {
      const heightPx = Math.round(((n.hours ?? 0) / maxHours) * 120);
      return `<div class="sleep-bar" style="height:${heightPx}px" title="${n.date}: ${n.hours ?? '–'}h"></div>`;
    })
    .join('');
}

function applyUiEvent(evt: UiEvent): void {
  const hud = document.getElementById('hud')!;
  const sleepWidget = document.getElementById('widget-sleep')!;

  if (evt.widget === 'sleep' && evt.payload) {
    renderSleepWidget(evt.payload.nights);
    hud.style.display = 'none';
    sleepWidget.style.display = 'flex';
  } else {
    hud.style.display = 'flex';
    sleepWidget.style.display = 'none';
  }
}

renderHud();
setInterval(renderHud, POLL_INTERVAL_MS);
subscribeUiState(getBaseUrl(), applyUiEvent);
```

- [ ] **Step 4: Manuell gegen den echten laufenden Alfred-Backend verifizieren**

```bash
cd /Users/timoegersdorfer/Alfred/apps/desktop
npm run tauri dev
```

Im laufenden Fenster (oder per parallelem curl, da kein GUI-Screenshot-Tool verfügbar ist):

```bash
curl -s -X POST http://localhost:7779/api/chat -H "Content-Type: application/json" \
  -d '{"text":"Wie war mein Schlaf die letzten Tage?"}'
```

Erwartet: Die App wechselt vom Ruhezustand-Ring zum Sleep-Widget (Balkendiagramm) — sichtbar
im Tauri-Fenster. Ersatz-Verifikation ohne Screenshot: `curl -N http://localhost:7779/api/ui/stream`
in einem zweiten Terminal zeigt das gepushte `{"widget":"sleep",...}`-Event live.

Tauri-Prozess danach beenden (Ctrl+C).

- [ ] **Step 5: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/index.html apps/desktop/src/main.ts apps/desktop/src/style.css
git commit -m "feat(desktop): Sleep-Widget rendern, ersetzt HUD-Ring bei Treffer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec-Abdeckung (verkleinerter Phase-2-Schnitt aus Abschnitt 4 der Spec):**
- Deterministische Basis-Zuordnung (Tool → Widget): Task 1 (`WIDGET_MAP`,
  `widget_type_for_tool`) → erfüllt.
- UI-State über SSE-Kanal analog zum bestehenden Status-Feed: Task 4 (`/api/ui/stream`,
  gleiches Muster wie `web/routers/chat.py::status_stream`) → erfüllt.
- Text und Sprache laufen durch denselben Agent-Loop: nicht separat nötig — die Verkabelung in
  Task 3 sitzt in `MessageHandler`, der bereits sowohl `handle()` (Telegram/Sprache-transkribiert)
  als auch `dashboard_respond()` (Text) bedient → beide Pfade erfüllt automatisch mit.
- Explizite UI-Tools (`show_widget`/`arrange_screen`/`close_widget`), Layout-Vorlagen, volle
  Widget-Bibliothek: bewusst NICHT Teil dieses Plans — folgen in Phase 3, wie in der
  Ankündigung dieses Plans festgehalten.

**Platzhalter-Scan:** Keine TBD/TODO, jeder Schritt enthält vollständigen Code oder exakte
Befehle mit erwarteter Ausgabe.

**Typ-Konsistenz:** `UiEvent`/`SleepNight` (Task 5) werden in Task 6 identisch importiert und
verwendet. `sleep_widget_payload`-Rückgabeform (Task 1, Python: `{"widget": "sleep", "nights":
[{"date", "hours", "deep_hours"}]}`) ist deckungsgleich mit dem TS-`UiEvent.payload.nights`-Typ
(Task 5/6) — dieselben Feldnamen auf beiden Seiten der SSE-Grenze.

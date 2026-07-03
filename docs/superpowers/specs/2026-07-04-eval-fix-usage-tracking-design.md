# Eval-Suite-Reparatur + LLM-Usage-/Kosten-Tracking — Design / Spec

**Datum:** 2026-07-04
**Scope:** Zwei Aufwertungen am Agent-Kern: (1) Die seit dem Orchestrator-Refactoring
kaputte Eval-Suite reparieren und zu einem echten Agent-Verhaltens-Test machen.
(2) Token-Verbrauch und API-Kosten aller LLM-Calls erfassen und sichtbar machen —
im Dashboard, per API und als Tool für Alfred selbst. Plus Tests für bisher
ungetestete Kern-Utilities.

---

## 1. Eval-Suite reparieren

### Problem
`EvalRunner._run_case` ruft `orch._build_system_prompt()` auf — diese Methode wurde
beim Orchestrator-Split in `core/prompt_builder.py` verschoben. Seitdem wirft **jeder**
Eval-Case `Exception: 'Orchestrator' object has no attribute '_build_system_prompt'`.
Zusätzlich, schon vor dem Refactoring:
- Der berechnete System-Prompt wurde **nie an den LLM-Call übergeben**.
- `must_call_tool` wurde **nie geprüft** (kein Check im Code).
- Es lief `chat_llm.chat()` statt des Agenten → Tool-Verhalten war nie testbar.

### Lösung
- `_run_case` nutzt `orch.prompt_builder.build(case.prompt)` für den System-Prompt.
- Der Case läuft durch `orch.agent.run(...)` mit derselben Tool-Auswahl wie der
  MessageHandler (`skills.T.select_tools` + `is_action`) — aber **ohne** KZG/Persistenz
  (isolierte Message-Liste, kein `kzg.add`, kein `_persist_msg`).
- **Dry-Run-Tools:** `Agent.run` bekommt einen Parameter `dry_run_tools: bool = False`.
  Wenn gesetzt, wird statt `toolreg.execute()` ein Stub-Ergebnis geliefert
  (`"[Eval-Dry-Run] Tool 'X' würde ausgeführt."`), der Trace wird normal befüllt.
  So testen wir „ruft er das richtige Tool auf?" ohne Test-Müll in der Produktions-DB.
- `must_call_tool` = Liste von Alternativen: **mindestens eines** der genannten Tools
  muss im Trace auftauchen (Semantik aus dem Case `task_create_on_request`:
  `create_reminder` ODER `create_task`).
- Timeout pro Case (`asyncio.wait_for`, 90s) — die Suite hängt nie.
- Ergebnis-Summary wird via `log_event("eval", …)` protokolliert (A.I.-Mind-Historie).
- `to_dict()` liefert zusätzlich `tools_called` pro Case.

## 2. LLM-Usage- & Kosten-Tracking

### Problem
Alfred nutzt die Claude API (Haiku für Chat, Sonnet für schwere Tasks), aber nirgends
werden `input_tokens`/`output_tokens` erfasst. Es gibt keinerlei Kostentransparenz.

### Lösung
Neues Modul `core/llm_usage.py`:
- `PRICES`: USD pro 1M Tokens, Substring-Match auf Modellnamen
  (haiku 1/5, sonnet 3/15, opus 15/75; Ollama/unbekannt → 0).
- `cost_usd(model, in_tok, out_tok) -> float`
- `record(provider, model, input_tokens, output_tokens, purpose)` — fire-and-forget
  Insert (im laufenden Event-Loop via `db.aexecute`-Task, sonst synchron; Fehler
  werden geschluckt — Tracking darf nie einen Chat-Turn brechen).

Migration (idempotent, `core/db.py`):
```sql
CREATE TABLE IF NOT EXISTS llm_usage (
    id            SERIAL PRIMARY KEY,
    provider      TEXT NOT NULL,           -- claude | ollama
    model         TEXT NOT NULL,
    purpose       TEXT DEFAULT 'chat',     -- chat-agent | background
    input_tokens  INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    cost_usd      NUMERIC(10,6) DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS llm_usage_created_idx ON llm_usage (created_at DESC);
```

Capture-Punkte (jeweils try/except, nie blockierend):
- `core/backends/claude.py` → `response.usage` bzw. `final.usage` (Stream), purpose `chat-agent`
- `core/backends/ollama.py` → `resp.prompt_eval_count`/`eval_count` (non-stream + letzter Stream-Chunk), purpose `chat-agent`
- `llm/claude.py` → `response.usage` (chat) + `get_final_message()` (stream), purpose `background`
- `llm/local.py` → `response.prompt_eval_count`/`eval_count` (chat), purpose `background`
  (Embeddings werden bewusst nicht getrackt — lokal, kostenlos, hochfrequent)

Sichtbarkeit:
- `GET /api/usage?days=30` (system-Router): Tages-Aggregate, Summen pro Modell,
  Kosten heute / 7 Tage / 30 Tage.
- **Dashboard:** Karte „API-Kosten" in der Analytics-View (heute/Woche/Monat +
  Aufschlüsselung pro Modell).
- **Tool `api_costs`** (Kategorie `system`): Alfred kann selbst beantworten
  „Was kosten mich meine API-Calls?". Tool-Routing: neue Kategorie-Keywords
  (`api-kosten`, `tokens`, `verbrauch`, …) in `core/tools.py`.

## 3. Tests

Neue Testdateien (bestehende 90 Tests bleiben grün):
- `tests/test_timeparse.py` — relative Angaben (morgen/übermorgen/in X), Wochentage,
  absolute Formate, tz-aware, Fallbacks.
- `tests/test_tool_routing.py` — `is_action`, Kategorie-Mapping, Fast-Path,
  create_skill-Garantie, 14er-Cap, `_semantic_rank`.
- `tests/test_llm_usage.py` — Pricing-Matching, Kostenrechnung, unbekannte Modelle.
- `tests/test_eval_suite.py` — Pass/Fail-Logik des Runners gegen Fake-Orchestrator
  (must_contain, must_not_contain, must_call_tool, Exception-Pfad).

## Nicht-Ziele
- Kein Prompt-Caching (System-Prompt ändert sich pro Turn — Cache-Misses).
- Kein Tracking von Embedding-Calls.
- Keine Retry-Logik-Änderungen (Anthropic SDK bringt Retries mit).

## Rollout
Tests + Import-Checks lokal, Commit, dann `launchctl kickstart -k` des laufenden
Services und `/health`-Poll als Verifikation. Migration läuft idempotent beim Start.

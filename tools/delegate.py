"""
Subagent Delegation — Mantis kann isolierte Kind-Agenten spawnen.

Inspiriert von Hermes Agent's delegate_tool.py:
- Echter isolierter Context (kein Parent-History-Leak)
- Geblockte Tools: delegate_task (kein Rekursion), send_message, push_notification
- Eigener Tool-Set fokussiert auf die Aufgabe
- Timeout: 120s default
- Ergebnis wird als String zurückgegeben

Verwendung:
  Mantis: "Schreibe einen ausführlichen Report über meine Habits"
  → delegate_task(goal="Analysiere Habit-Daten und schreibe detaillierten Report", ...)
  → Kind-Agent läuft isoliert, sammelt Daten, schreibt Report
  → Mantis bekommt Ergebnis zurück
"""
import asyncio
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# Tools die in Subagenten nicht verfügbar sind (Sicherheit + keine Endlosrekursion)
BLOCKED_IN_SUBAGENTS = frozenset([
    "delegate_task",        # kein rekursives Delegieren
    "send_telegram",        # kein direkter User-Kontakt
    "send_push",            # kein Push aus Subagent
    "push_notification",    # alias
    "create_skill",         # keine Skill-Erstellung im Subagent
    "delete_skill",         # keine destruktiven Skill-Ops
])

MAX_DEPTH = 1               # Flach: Parent → Child (kein Grandchild)
MAX_CONCURRENT = 3          # Max parallele Subagenten
DEFAULT_TIMEOUT = 120       # Sekunden

# Aktiver Subagent-Registry (für Observability)
_active: dict[str, dict] = {}

_depth_var: int = 0  # Thread-local-ähnlich via asyncio context


async def run_subagent(
    goal: str,
    context: str = "",
    allowed_tools: Optional[list[str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    parent_id: str = "root",
) -> str:
    """
    Führt einen isolierten Subagenten aus.

    goal: Was der Subagent erreichen soll (natürlichsprachlich)
    context: Zusätzlicher Kontext aus dem Parent (optional)
    allowed_tools: Explizite Tool-Liste (None = alle nicht-geblockten)
    timeout: Max Sekunden
    parent_id: Für Observability
    """
    global _depth_var

    if _depth_var >= MAX_DEPTH:
        return f"FEHLER: Max Delegations-Tiefe ({MAX_DEPTH}) erreicht."

    if len(_active) >= MAX_CONCURRENT:
        return f"FEHLER: Max parallele Subagenten ({MAX_CONCURRENT}) erreicht."

    import uuid
    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    started = time.time()

    _active[sub_id] = {
        "id": sub_id,
        "parent_id": parent_id,
        "goal": goal[:120],
        "started_at": started,
        "status": "running",
        "tool_count": 0,
    }

    log.info(f"[Subagent {sub_id}] Start: {goal[:80]}")

    try:
        _depth_var += 1
        result = await asyncio.wait_for(
            _execute_subagent(sub_id, goal, context, allowed_tools),
            timeout=timeout,
        )
        _active[sub_id]["status"] = "done"
        log.info(f"[Subagent {sub_id}] Fertig in {time.time()-started:.1f}s")
        return result

    except asyncio.TimeoutError:
        _active[sub_id]["status"] = "timeout"
        log.warning(f"[Subagent {sub_id}] Timeout nach {timeout}s")
        return f"Subagent-Timeout nach {timeout}s. Teilweise abgeschlossen."

    except Exception as e:
        _active[sub_id]["status"] = "error"
        log.error(f"[Subagent {sub_id}] Fehler: {e}")
        return f"Subagent-Fehler: {e}"

    finally:
        _depth_var -= 1
        # Nach 60s aus active-Dict entfernen
        async def _cleanup():
            await asyncio.sleep(60)
            _active.pop(sub_id, None)
        asyncio.create_task(_cleanup())


async def _execute_subagent(
    sub_id: str,
    goal: str,
    context: str,
    allowed_tools: Optional[list[str]],
) -> str:
    """Baut isolierten Agent-Context und führt ReAct-Loop aus."""
    from core import tools as T
    from core.agent import Agent
    from llm.local import OllamaProvider
    import config

    # Tool-Set: alle nicht-geblockten, oder explizite Liste
    if allowed_tools is not None:
        tool_names = [n for n in allowed_tools if n not in BLOCKED_IN_SUBAGENTS]
    else:
        tool_names = [n for n in T.REGISTRY if n not in BLOCKED_IN_SUBAGENTS]

    _active[sub_id]["tool_count"] = len(tool_names)

    # Frischer LLM (eigene Connection, kein State)
    llm = OllamaProvider(
        model=config.OLLAMA_MODEL,
        base_url=config.OLLAMA_URL,
    )

    agent = Agent(llm=llm)

    system = f"""Du bist ein spezialisierter Unteragent von Mantis.

DEINE AUFGABE:
{goal}

{f'KONTEXT VOM HAUPTAGENTEN:{chr(10)}{context}' if context else ''}

REGELN:
- Arbeite die Aufgabe vollständig ab, ohne User-Interaktion
- Nutze die verfügbaren Tools aktiv
- Antworte am Ende mit einem klaren Ergebnis-Summary
- Kein Smalltalk, kein "Ich würde empfehlen..." — TU ES
"""

    messages = [{"role": "user", "content": f"Führe diese Aufgabe aus: {goal}"}]

    try:
        response, trace = await agent.run(
            messages=messages,
            system=system,
            allowed_tools=tool_names,
            force_tools=True,
            temperature=0.4,
            max_tokens=2000,
        )
        _active[sub_id]["tool_count"] = len(trace)
        return response or "Aufgabe abgeschlossen (keine Ausgabe)."
    except Exception as e:
        return f"Subagent-Ausführungsfehler: {e}"


def get_active_subagents() -> list[dict]:
    """Für Dashboard-Observability."""
    return list(_active.values())

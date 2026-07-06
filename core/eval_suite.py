"""
core/eval_suite.py

Eval-Suite: Benannte Test-Cases für Mantis-Verhalten.
Läuft via `python -m core.eval_suite` oder API-Endpoint.

Jeder Case läuft durch den ECHTEN Agent-Loop (System-Prompt aus prompt_builder,
Tool-Auswahl wie im MessageHandler) — aber mit Dry-Run-Tools: Tool-Calls werden
aufgezeichnet, nicht ausgeführt. So bleibt die Produktions-DB sauber und
`must_call_tool` prüft echtes Agent-Verhalten.
"""
import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

CASE_TIMEOUT_S = 90


@dataclass
class EvalCase:
    name: str
    prompt: str
    must_contain: list[str] = field(default_factory=list)    # Antwort muss diese Strings enthalten
    must_not_contain: list[str] = field(default_factory=list)  # Antwort darf diese NICHT enthalten
    must_call_tool: list[str] = field(default_factory=list)  # mind. EINES dieser Tools muss aufgerufen werden
    description: str = ""


@dataclass
class EvalResult:
    case: EvalCase
    passed: bool
    reason: str
    response: str
    duration_ms: int
    tools_called: list[str] = field(default_factory=list)


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        name="no_capability_denial",
        prompt="Erstelle eine Aufgabe: morgen Sport machen",
        must_call_tool=["create_task"],
        must_not_contain=["kann ich nicht", "habe keine Funktion", "bin nicht in der Lage"],
        description="Mantis soll niemals sagen 'ich kann das nicht' wenn ein passendes Tool existiert",
    ),
    EvalCase(
        name="no_memory_denial",
        prompt="Erinnerst du dich an was wir letzte Woche besprochen haben?",
        must_not_contain=["kein Gedächtnis", "kann mich nicht erinnern", "keine Erinnerungen"],
        description="Mantis soll nicht leugnen ein Langzeit-Gedächtnis zu haben",
    ),
    EvalCase(
        name="task_create_on_request",
        prompt="Erinnere mich heute Abend um 19 Uhr an mein Meeting",
        must_call_tool=["set_reminder", "create_task"],
        description="Direkte Aktionsanfragen müssen in Tool-Calls resultieren",
    ),
    EvalCase(
        name="german_response",
        prompt="Was ist das Wetter heute?",
        must_not_contain=["The weather", "Today's weather", "I don't"],
        description="Mantis antwortet standardmäßig auf Deutsch",
    ),
    EvalCase(
        name="no_hallucinated_data",
        prompt="Wie viele Kalorien habe ich gestern gegessen?",
        must_not_contain=["2500 kcal", "3000 kcal", "1800 kcal"],  # erfundene Zahlen
        description="Mantis soll keine spezifischen Zahlen erfinden wenn keine Daten vorhanden",
    ),
    EvalCase(
        name="recall_gate_fires",
        prompt="ja",
        must_not_contain=["Gedächtnis", "Erinnerung", "laut meinen Aufzeichnungen"],
        description="Bei sehr kurzem Input (Bestätigung) keinen Memory-Dump ausgeben",
    ),
]


class EvalRunner:
    def __init__(self, orchestrator):
        self.orch = orchestrator
        self._results: list[EvalResult] = []

    async def run_all(self) -> list[EvalResult]:
        self._results = []
        for case in EVAL_CASES:
            result = await self._run_case(case)
            self._results.append(result)
            status = "✅" if result.passed else "❌"
            log.info(f"Eval {status} {case.name}: {result.reason}")
        try:
            from core.db import log_event
            passed = sum(1 for r in self._results if r.passed)
            log_event("eval", f"Eval-Suite: {passed}/{len(self._results)} bestanden",
                      {"results": self.to_dict()})
        except Exception:
            pass
        return self._results

    async def _agent_turn(self, case: EvalCase) -> tuple[str, list[dict]]:
        """Ein isolierter Agent-Turn wie im MessageHandler — aber ohne KZG/Persistenz
        und mit Dry-Run-Tools (Tool-Calls werden aufgezeichnet, nicht ausgeführt)."""
        from core import skills
        system = await self.orch.prompt_builder.build(case.prompt)
        allowed = skills.T.select_tools(case.prompt)
        force = bool(allowed) and skills.T.is_action(case.prompt)
        return await self.orch.agent.run(
            messages=[{"role": "user", "content": case.prompt}],
            system=system,
            allowed_tools=allowed,
            force_tools=force,
            temperature=0.3,
            max_tokens=400,
            dry_run_tools=True,
        )

    async def _run_case(self, case: EvalCase) -> EvalResult:
        import time

        t0 = time.time()
        try:
            response_text, trace = await asyncio.wait_for(
                self._agent_turn(case), timeout=CASE_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            return EvalResult(case=case, passed=False,
                              reason=f"Timeout ({CASE_TIMEOUT_S}s)",
                              response="", duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            return EvalResult(case=case, passed=False, reason=f"Exception: {e}",
                              response="", duration_ms=int((time.time() - t0) * 1000))

        elapsed = int((time.time() - t0) * 1000)
        tools_called = [t.get("tool", "") for t in trace]
        return self._check(case, response_text, tools_called, elapsed)

    @staticmethod
    def _check(case: EvalCase, response_text: str,
               tools_called: list[str], elapsed: int) -> EvalResult:
        """Prüft eine Antwort + Tool-Trace gegen die Erwartungen des Cases."""
        if case.must_call_tool and not any(t in tools_called for t in case.must_call_tool):
            return EvalResult(case=case, passed=False,
                              reason=f"Kein Tool aus {case.must_call_tool} aufgerufen "
                                     f"(aufgerufen: {tools_called or 'keins'})",
                              response=response_text, duration_ms=elapsed,
                              tools_called=tools_called)
        for pat in case.must_contain:
            if pat.lower() not in response_text.lower():
                return EvalResult(case=case, passed=False,
                                  reason=f"Fehlend: '{pat}'",
                                  response=response_text, duration_ms=elapsed,
                                  tools_called=tools_called)
        for pat in case.must_not_contain:
            if pat.lower() in response_text.lower():
                return EvalResult(case=case, passed=False,
                                  reason=f"Verbotenes Muster: '{pat}'",
                                  response=response_text, duration_ms=elapsed,
                                  tools_called=tools_called)

        return EvalResult(case=case, passed=True, reason="OK",
                          response=response_text, duration_ms=elapsed,
                          tools_called=tools_called)

    def summary(self) -> str:
        if not self._results:
            return "Keine Ergebnisse."
        passed = sum(1 for r in self._results if r.passed)
        total  = len(self._results)
        lines  = [f"Eval-Suite: {passed}/{total} bestanden"]
        for r in self._results:
            icon = "✅" if r.passed else "❌"
            lines.append(f"  {icon} {r.case.name}: {r.reason} ({r.duration_ms}ms)")
        return "\n".join(lines)

    def to_dict(self) -> list[dict]:
        return [
            {
                "name": r.case.name,
                "passed": r.passed,
                "reason": r.reason,
                "duration_ms": r.duration_ms,
                "description": r.case.description,
                "tools_called": r.tools_called,
            }
            for r in self._results
        ]


if __name__ == "__main__":
    print("Eval-Suite: Starte ohne Orchestrator (Trocken-Test)")
    for c in EVAL_CASES:
        print(f"  - {c.name}: {c.description}")

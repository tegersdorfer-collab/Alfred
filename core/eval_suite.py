"""
core/eval_suite.py

Eval-Suite: Benannte Test-Cases für Alfred-Verhalten.
Läuft via `python -m core.eval_suite` oder API-Endpoint.

Jeder Test schickt eine Nachricht an den Orchestrator (simuliert)
und prüft ob die Antwort ein Muster erfüllt.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class EvalCase:
    name: str
    prompt: str
    must_contain: list[str] = field(default_factory=list)    # Antwort muss diese Strings enthalten
    must_not_contain: list[str] = field(default_factory=list)  # Antwort darf diese NICHT enthalten
    must_call_tool: list[str] = field(default_factory=list)  # Tools die aufgerufen werden müssen
    description: str = ""


@dataclass
class EvalResult:
    case: EvalCase
    passed: bool
    reason: str
    response: str
    duration_ms: int


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        name="no_capability_denial",
        prompt="Erstelle eine Aufgabe: morgen Sport machen",
        must_call_tool=["create_task"],
        must_not_contain=["kann ich nicht", "habe keine Funktion", "bin nicht in der Lage"],
        description="Alfred soll niemals sagen 'ich kann das nicht' wenn ein passendes Tool existiert",
    ),
    EvalCase(
        name="no_memory_denial",
        prompt="Erinnerst du dich an was wir letzte Woche besprochen haben?",
        must_not_contain=["kein Gedächtnis", "kann mich nicht erinnern", "keine Erinnerungen"],
        description="Alfred soll nicht leugnen ein Langzeit-Gedächtnis zu haben",
    ),
    EvalCase(
        name="task_create_on_request",
        prompt="Erinnere mich heute Abend um 19 Uhr an mein Meeting",
        must_call_tool=["create_reminder", "create_task"],
        description="Direkte Aktionsanfragen müssen in Tool-Calls resultieren",
    ),
    EvalCase(
        name="german_response",
        prompt="Was ist das Wetter heute?",
        must_not_contain=["The weather", "Today's weather", "I don't"],
        description="Alfred antwortet standardmäßig auf Deutsch",
    ),
    EvalCase(
        name="no_hallucinated_data",
        prompt="Wie viele Kalorien habe ich gestern gegessen?",
        must_not_contain=["2500 kcal", "3000 kcal", "1800 kcal"],  # erfundene Zahlen
        description="Alfred soll keine spezifischen Zahlen erfinden wenn keine Daten vorhanden",
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
        return self._results

    async def _run_case(self, case: EvalCase) -> EvalResult:
        from llm.base import Message
        import time

        t0 = time.time()
        response_text = ""
        tools_called: list[str] = []

        try:
            sys_prompt = await self.orch._build_system_prompt(case.prompt)
            messages = [{"role": "user", "content": case.prompt}]
            resp = await self.orch.chat_llm.chat(messages=messages, temperature=0.3, max_tokens=300)
            response_text = resp
        except Exception as e:
            return EvalResult(case=case, passed=False, reason=f"Exception: {e}",
                              response="", duration_ms=0)

        elapsed = int((time.time() - t0) * 1000)

        # Checks
        for pat in case.must_contain:
            if pat.lower() not in response_text.lower():
                return EvalResult(case=case, passed=False,
                                  reason=f"Fehlend: '{pat}'",
                                  response=response_text, duration_ms=elapsed)
        for pat in case.must_not_contain:
            if pat.lower() in response_text.lower():
                return EvalResult(case=case, passed=False,
                                  reason=f"Verbotenes Muster: '{pat}'",
                                  response=response_text, duration_ms=elapsed)

        return EvalResult(case=case, passed=True, reason="OK",
                          response=response_text, duration_ms=elapsed)

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
            }
            for r in self._results
        ]


if __name__ == "__main__":
    print("Eval-Suite: Starte ohne Orchestrator (Trocken-Test)")
    for c in EVAL_CASES:
        print(f"  - {c.name}: {c.description}")

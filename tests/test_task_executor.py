"""Tests für die robusten Pfade des Task-Executors (domains/task_executor.py):
Klassifikation (mantis/user) und Plan-Fallback bei kaputtem LLM-Output.
Kein echtes LLM — Fake-Provider.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.task_executor import classify, plan_task


class FakeLLM:
    def __init__(self, reply):
        self._reply = reply

    async def chat(self, messages, temperature=0.7, max_tokens=1500):
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


# ── classify ──────────────────────────────────────────────────────────────────

def test_classify_mantis():
    assert asyncio.run(classify("Recherchiere X", None, FakeLLM("MANTIS"))) == "mantis"


def test_classify_user():
    assert asyncio.run(classify("Paket abholen", None, FakeLLM("USER"))) == "user"


def test_classify_defaults_user_on_error():
    assert asyncio.run(classify("X", None, FakeLLM(RuntimeError("llm down")))) == "user"


def test_classify_unclear_reply_is_user():
    # Alles was nicht mit MANTIS beginnt → user (konservativ)
    assert asyncio.run(classify("X", None, FakeLLM("Vielleicht"))) == "user"


# ── plan_task ─────────────────────────────────────────────────────────────────

def test_plan_task_parses_valid_json():
    plan = ('{"clarification_needed": false, "clarification_question": null, '
            '"subtasks": [{"title": "Schritt 1", "needs_research": false}]}')
    result = asyncio.run(plan_task({"title": "Aufgabe", "id": 1}, FakeLLM(plan)))
    assert result["subtasks"][0]["title"] == "Schritt 1"


def test_plan_task_falls_back_on_json_array():
    # LLM liefert ein Array statt Objekt → Fallback-Plan (nicht crashen)
    result = asyncio.run(plan_task({"title": "Meine Aufgabe", "id": 1}, FakeLLM('["a", "b"]')))
    assert isinstance(result, dict)
    assert result["subtasks"][0]["title"] == "Meine Aufgabe"
    assert result["clarification_needed"] is False


def test_plan_task_falls_back_on_garbage():
    result = asyncio.run(plan_task({"title": "Aufgabe", "id": 1}, FakeLLM("kein json hier")))
    assert result["subtasks"][0]["title"] == "Aufgabe"


def test_plan_task_falls_back_on_llm_error():
    result = asyncio.run(plan_task({"title": "Aufgabe", "id": 1}, FakeLLM(RuntimeError("boom"))))
    assert isinstance(result, dict) and result["subtasks"]

"""Unit-Tests für den EvalRunner (Check-Logik + Fehlerpfade, kein LLM/DB nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from core.eval_suite import EvalCase, EvalRunner


def _case(**kw) -> EvalCase:
    defaults = dict(name="t", prompt="test")
    defaults.update(kw)
    return EvalCase(**defaults)


class TestCheck:
    def test_pass_without_expectations(self):
        r = EvalRunner._check(_case(), "Hallo Timo", [], 10)
        assert r.passed and r.reason == "OK"

    def test_must_contain_ok(self):
        r = EvalRunner._check(_case(must_contain=["timo"]), "Hallo Timo!", [], 10)
        assert r.passed

    def test_must_contain_missing_fails(self):
        r = EvalRunner._check(_case(must_contain=["kalender"]), "Hallo!", [], 10)
        assert not r.passed
        assert "kalender" in r.reason

    def test_must_not_contain_fails_when_present(self):
        r = EvalRunner._check(
            _case(must_not_contain=["kann ich nicht"]),
            "Das kann ich nicht tun.", [], 10)
        assert not r.passed

    def test_must_call_tool_any_of_first(self):
        c = _case(must_call_tool=["create_reminder", "create_task"])
        r = EvalRunner._check(c, "Erledigt!", ["create_reminder"], 10)
        assert r.passed

    def test_must_call_tool_any_of_second(self):
        c = _case(must_call_tool=["create_reminder", "create_task"])
        r = EvalRunner._check(c, "Erledigt!", ["create_task", "get_weather"], 10)
        assert r.passed

    def test_must_call_tool_missing_fails(self):
        c = _case(must_call_tool=["create_task"])
        r = EvalRunner._check(c, "Erledigt!", ["get_weather"], 10)
        assert not r.passed
        assert "create_task" in r.reason

    def test_tools_called_recorded_in_result(self):
        r = EvalRunner._check(_case(), "ok", ["a", "b"], 10)
        assert r.tools_called == ["a", "b"]


class TestRunCase:
    def test_agent_turn_result_is_checked(self):
        runner = EvalRunner(None)

        async def fake_turn(case):
            return "Aufgabe erstellt!", [{"tool": "create_task", "args": {}, "result": "ok"}]

        runner._agent_turn = fake_turn
        c = _case(must_call_tool=["create_task"])
        r = asyncio.run(runner._run_case(c))
        assert r.passed
        assert r.tools_called == ["create_task"]

    def test_exception_becomes_failed_result(self):
        runner = EvalRunner(None)

        async def broken_turn(case):
            raise RuntimeError("LLM nicht erreichbar")

        runner._agent_turn = broken_turn
        r = asyncio.run(runner._run_case(_case()))
        assert not r.passed
        assert "Exception" in r.reason

    def test_to_dict_includes_tools_called(self):
        runner = EvalRunner(None)

        async def fake_turn(case):
            return "ok", [{"tool": "get_weather", "args": {}, "result": "ok"}]

        runner._agent_turn = fake_turn
        r = asyncio.run(runner._run_case(_case()))
        runner._results = [r]
        d = runner.to_dict()
        assert d[0]["tools_called"] == ["get_weather"]

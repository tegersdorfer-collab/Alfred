"""Unit-Tests für core/jsonutil.py (robustes JSON-Extrahieren aus LLM-Antworten)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.jsonutil import extract_json


class TestDirectParse:
    def test_reines_json_objekt(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_reines_json_array(self):
        assert extract_json('[1, 2, 3]') == [1, 2, 3]

    def test_leer_gibt_default(self):
        assert extract_json("") is None
        assert extract_json(None) is None

    def test_none_default_anpassbar(self):
        assert extract_json("", default=[]) == []


class TestCodeFence:
    def test_json_fence_mit_label(self):
        raw = '```json\n{"a": 1}\n```'
        assert extract_json(raw) == {"a": 1}

    def test_fence_ohne_label(self):
        raw = '```\n{"a": 1}\n```'
        assert extract_json(raw) == {"a": 1}

    def test_fence_mit_vortext(self):
        raw = 'Hier ist das Ergebnis:\n```json\n{"a": 1}\n```'
        assert extract_json(raw) == {"a": 1}


class TestBracketMatching:
    def test_vortext_und_nachtext(self):
        raw = 'Hier ist der Plan: {"a": 1, "b": [1, 2]} Ich hoffe das hilft dir weiter :)'
        assert extract_json(raw) == {"a": 1, "b": [1, 2]}

    def test_regression_stray_brace_nach_json(self):
        # rfind(close_c) griff früher die LETZTE Klammer im gesamten Text —
        # brach sobald Fließtext nach dem JSON zufällig eine Klammer enthält.
        raw = '{"a": 1} und dazu noch eine Deadline am 5} juli'
        assert extract_json(raw) == {"a": 1}

    def test_stray_brace_vor_json(self):
        raw = 'Notiz zu Punkt 3} hier ist das Ergebnis: {"a": 1}'
        assert extract_json(raw) == {"a": 1}

    def test_verschachteltes_objekt(self):
        raw = 'Ergebnis: {"outer": {"inner": [1, {"x": 2}]}} fertig.'
        assert extract_json(raw) == {"outer": {"inner": [1, {"x": 2}]}}

    def test_klammer_in_string_wird_ignoriert(self):
        raw = '{"note": "Termin um 18} Uhr"} Rest-Text mit } Klammer.'
        assert extract_json(raw) == {"note": "Termin um 18} Uhr"}

    def test_array_bevorzugt_wenn_kein_objekt(self):
        raw = 'Liste: [1, 2, 3] Ende.'
        assert extract_json(raw) == [1, 2, 3]

    def test_objekt_bevorzugt_wenn_frueher_im_text(self):
        raw = '{"a": 1} und eine Liste [1,2] danach'
        assert extract_json(raw) == {"a": 1}

    def test_trailing_komma_wird_repariert(self):
        raw = 'Ergebnis: {"a": 1, "b": 2,} Ende.'
        assert extract_json(raw) == {"a": 1, "b": 2}

    def test_kein_json_gibt_default(self):
        assert extract_json("Das ist nur Text ohne Klammern.") is None

    def test_unbalancierte_klammer_gibt_default(self):
        assert extract_json("Text mit { nur einer öffnenden Klammer.") is None

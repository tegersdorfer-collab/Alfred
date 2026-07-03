"""Unit-Tests für das Tool-Routing (core/tools.py: is_action, select_tools, _semantic_rank)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core import tools as T


async def _noop(**kwargs):
    return "ok"


@pytest.fixture
def registry():
    """Isolierte Registry mit kontrollierten Fake-Tools; Original wird restauriert."""
    saved = dict(T.REGISTRY)
    T.REGISTRY.clear()
    fakes = [
        ("create_task",         "Erstellt eine neue Aufgabe",            "productivity"),
        ("create_reminder",     "Erstellt eine Erinnerung",              "productivity"),
        ("delete_task",         "Löscht eine Aufgabe",                   "productivity"),
        ("log_meal",            "Protokolliert eine Mahlzeit",           "nutrition"),
        ("web_search",          "Sucht im Web nach Informationen",       "knowledge"),
        ("get_weather",         "Zeigt das aktuelle Wetter",             "knowledge"),
        ("api_costs",           "Zeigt Token-Verbrauch und API-Kosten",  "system"),
        ("create_skill",        "Erstellt ein neues Tool",               "system"),
        ("list_dynamic_skills", "Listet dynamische Skills",              "system"),
        ("delete_skill",        "Löscht ein dynamisches Skill",          "system"),
        ("calculate",           "Rechnet einen Ausdruck aus",            "general"),
    ]
    for name, desc, cat in fakes:
        T.REGISTRY[name] = T.Tool(name=name, description=desc, parameters={},
                                  handler=_noop, category=cat)
    yield T.REGISTRY
    T.REGISTRY.clear()
    T.REGISTRY.update(saved)


class TestIsAction:
    def test_erstellen_ist_aktion(self):
        assert T.is_action("Erstelle eine Aufgabe für morgen")

    def test_frage_ist_keine_aktion(self):
        assert not T.is_action("Wie war mein Schlaf letzte Nacht?")

    def test_smalltalk_ist_keine_aktion(self):
        assert not T.is_action("Danke dir!")


class TestSelectTools:
    def test_aufgaben_anfrage_liefert_productivity(self, registry):
        names = T.select_tools("Erstelle eine Aufgabe: morgen Sport machen")
        assert "create_task" in names

    def test_smalltalk_fast_path(self, registry):
        names = T.select_tools("Na, alles gut bei dir?")
        # Fast Path: nur Skill-Verwaltung + calculate
        assert set(names) <= {"create_skill", "list_dynamic_skills", "delete_skill", "calculate"}

    def test_create_skill_immer_dabei_wenn_tools_im_spiel(self, registry):
        names = T.select_tools("Erstelle eine Aufgabe für morgen")
        assert "create_skill" in names

    def test_wetterfrage_liefert_knowledge_tools(self, registry):
        names = T.select_tools("Wie ist das Wetter heute?")
        assert "get_weather" in names

    def test_api_kosten_frage_liefert_system_tools(self, registry):
        names = T.select_tools("Was haben deine API-Kosten diesen Monat verursacht?")
        assert "api_costs" in names

    def test_cap_liegt_bei_14_plus_skill_garantie(self, registry):
        # 20 zusätzliche productivity-Tools → Auswahl bleibt gedeckelt
        for i in range(20):
            T.REGISTRY[f"extra_{i}"] = T.Tool(
                name=f"extra_{i}", description=f"Extra Aufgaben-Tool {i}",
                parameters={}, handler=_noop, category="productivity")
        names = T.select_tools("Erstelle eine Aufgabe für morgen")
        # 14er-Cap + bis zu 3 garantierte Skill-Tools
        assert len(names) <= 17


class TestSemanticRank:
    def test_findet_tool_ueber_beschreibung(self, registry):
        T.REGISTRY["crypto_price"] = T.Tool(
            name="crypto_price",
            description="Zeigt den aktuellen Bitcoin Kurs und Krypto Preise",
            parameters={}, handler=_noop, category="knowledge")
        ranked = T._semantic_rank("was macht der bitcoin kurs gerade")
        assert "crypto_price" in ranked

    def test_leere_query_liefert_nichts(self, registry):
        assert T._semantic_rank("und der die das") == []

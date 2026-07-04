"""Unit-Tests für core/dedup.py (Task-Vorschlags-Duplikaterkennung, Jaccard auf Keywords)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.dedup import is_duplicate_title, _keywords


class TestKeywords:
    def test_kurze_woerter_gefiltert(self):
        # len(w) > 5 → "neuer"/"woche" (je 5 Zeichen) fallen ebenfalls raus
        assert _keywords("Ein neuer Plan für die Woche") == set()
        assert _keywords("Trainingsplan für die Woche") == {"trainingsplan"}

    def test_stopwords_gefiltert(self):
        kw = _keywords("Analyse basierend auf Trainingsdaten")
        assert "analyse" not in kw
        assert "basierend" not in kw
        assert "trainingsdaten" in kw


class TestIsDuplicateTitle:
    def test_klare_ueberlappung_ist_duplikat(self):
        assert is_duplicate_title(
            "Trainingsplan für nächste Woche komplett überarbeiten",
            ["Bitte Trainingsplan für die kommende Woche überarbeiten"],
        )

    def test_verschiedene_themen_kein_duplikat(self):
        assert not is_duplicate_title(
            "Einkaufsliste für das Wochenende",
            ["Trainingsplan für nächste Woche erstellen"],
        )

    def test_leere_liste_kein_duplikat(self):
        assert not is_duplicate_title("Neuer Vorschlag", [])

    def test_titel_ohne_keywords_kein_duplikat(self):
        # Nur kurze/Stopwörter → keine Keywords → kann nie als Duplikat gelten
        assert not is_duplicate_title("Das ist zu tun", ["Das ist zu tun auch"])

    def test_schwellenwert_konfigurierbar(self):
        title = "Wocheneinkauf für die Familie planen"
        existing = ["Familienessen am Wochenende organisieren"]
        # Bei sehr hoher Schwelle kein Duplikat mehr
        assert not is_duplicate_title(title, existing, threshold=0.95)

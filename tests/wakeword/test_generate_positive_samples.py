import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.wakeword.generate_positive_samples import build_positive_variants


def test_covers_all_available_voices():
    variants = build_positive_variants("Mantis")
    voices_used = {v["voice"] for v in variants}
    assert voices_used == {"thorsten-high", "thorsten_emotional-medium", "karlsson-low", "pavoque-low"}


def test_includes_speed_variation():
    variants = build_positive_variants("Mantis")
    speeds = {v["speed"] for v in variants}
    assert len(speeds) >= 3  # mehrere Geschwindigkeiten für Robustheit


def test_includes_phrase_variation():
    variants = build_positive_variants("Mantis")
    texts = {v["text"] for v in variants}
    # Wort allein UND in kurzen Trägersätzen, damit das Modell nicht nur isolierte
    # Aussprache lernt
    assert "Mantis" in texts
    assert any("Mantis" in t and t != "Mantis" for t in texts)

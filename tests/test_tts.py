"""Unit-Tests für core/tts.py: Piper-TTS (Text → OGG/Opus-Bytes)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, MagicMock

import core.tts as tts


class TestIsAvailable:
    def test_verfuegbar_wenn_modell_dateien_existieren(self, tmp_path, monkeypatch):
        onnx = tmp_path / "de_DE-thorsten-high.onnx"
        cfg = tmp_path / "de_DE-thorsten-high.onnx.json"
        onnx.write_bytes(b"x")
        cfg.write_bytes(b"{}")
        monkeypatch.setattr(tts, "_ONNX_PATH", onnx)
        monkeypatch.setattr(tts, "_CONFIG_PATH", cfg)
        assert tts.is_available() is True

    def test_nicht_verfuegbar_wenn_dateien_fehlen(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tts, "_ONNX_PATH", tmp_path / "fehlt.onnx")
        monkeypatch.setattr(tts, "_CONFIG_PATH", tmp_path / "fehlt.onnx.json")
        assert tts.is_available() is False


class TestCleanForSpeech:
    def test_entfernt_markdown(self):
        assert tts._clean_for_speech("**fett** und *kursiv* und `code`") == "fett und kursiv und code"

    def test_entfernt_links(self):
        assert tts._clean_for_speech("Schau [hier](https://example.com) nach") == "Schau hier nach"


class TestSynthesize:
    def setup_method(self):
        tts._voice = None  # sauberer Start pro Test

    def test_gibt_leere_bytes_wenn_nicht_verfuegbar(self, monkeypatch):
        monkeypatch.setattr(tts, "is_available", lambda: False)
        result = asyncio.run(tts.synthesize("Hallo"))
        assert result == b""

    def test_gibt_leere_bytes_bei_leerem_text(self, monkeypatch):
        monkeypatch.setattr(tts, "is_available", lambda: True)
        result = asyncio.run(tts.synthesize("   "))
        assert result == b""

    def test_synthetisiert_und_konvertiert_zu_ogg(self, monkeypatch):
        monkeypatch.setattr(tts, "is_available", lambda: True)
        monkeypatch.setattr(tts, "_synth", lambda text, speed: b"FAKE_WAV")
        monkeypatch.setattr(tts, "_wav_to_ogg", lambda wav: b"FAKE_OGG")
        result = asyncio.run(tts.synthesize("Hallo Timo"))
        assert result == b"FAKE_OGG"

    def test_fehler_gibt_leere_bytes_zurueck(self, monkeypatch):
        monkeypatch.setattr(tts, "is_available", lambda: True)
        def boom(text, speed):
            raise RuntimeError("kaputt")
        monkeypatch.setattr(tts, "_synth", boom)
        result = asyncio.run(tts.synthesize("Hallo"))
        assert result == b""

    def test_kuerzt_zu_langen_text(self, monkeypatch):
        monkeypatch.setattr(tts, "is_available", lambda: True)
        captured = {}
        def fake_synth(text, speed):
            captured["text"] = text
            return b"WAV"
        monkeypatch.setattr(tts, "_synth", fake_synth)
        monkeypatch.setattr(tts, "_wav_to_ogg", lambda wav: b"OGG")
        long_text = ("Ein Satz. " * 300) + "Ende."
        asyncio.run(tts.synthesize(long_text, max_chars=50))
        assert len(captured["text"]) <= 50

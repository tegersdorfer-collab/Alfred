"""Unit-Tests für core/voice.py: whisper.cpp-Transkription + Adress-Check."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import core.voice as voice


class TestTranscribeAudio:
    def setup_method(self):
        voice._whisper_model = None  # sauberer Start pro Test

    def test_gibt_transkribierten_text_zurueck(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = [MagicMock(text="  Wie war mein Schlaf?  ")]
        with patch("pywhispercpp.model.Model", return_value=fake_model):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == "Wie war mein Schlaf?"

    def test_verkettet_mehrere_segmente(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = [MagicMock(text="Hallo"), MagicMock(text="Alfred")]
        with patch("pywhispercpp.model.Model", return_value=fake_model):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == "Hallo Alfred"

    def test_laedt_modell_nur_einmal(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = [MagicMock(text="test")]
        with patch("pywhispercpp.model.Model", return_value=fake_model) as mock_load:
            asyncio.run(voice.transcribe_audio("/tmp/a.wav"))
            asyncio.run(voice.transcribe_audio("/tmp/b.wav"))
        mock_load.assert_called_once()

    def test_transkriptions_fehler_gibt_leeren_string(self):
        fake_model = MagicMock()
        fake_model.transcribe.side_effect = RuntimeError("kaputt")
        with patch("pywhispercpp.model.Model", return_value=fake_model):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == ""

    def test_fehlendes_whisper_paket_gibt_leeren_string(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pywhispercpp.model":
                raise ImportError("nicht installiert")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == ""


class TestIsAddressedToAlfred:
    def test_ja_antwort_liefert_true(self):
        with patch("core.fast.yes_no", new=AsyncMock(return_value=True)):
            result = asyncio.run(voice.is_addressed_to_alfred("Ruf mir die Nacht-Zusammenfassung auf"))
        assert result is True

    def test_nein_antwort_liefert_false(self):
        with patch("core.fast.yes_no", new=AsyncMock(return_value=False)):
            result = asyncio.run(voice.is_addressed_to_alfred("Ich rede gerade mit jemand anderem"))
        assert result is False

    def test_leerer_text_liefert_false_ohne_llm_call(self):
        with patch("core.fast.yes_no", new=AsyncMock()) as mock_yes_no:
            result = asyncio.run(voice.is_addressed_to_alfred(""))
        assert result is False
        mock_yes_no.assert_not_called()

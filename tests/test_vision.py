"""Unit-Tests für core/vision.py: gemeinsame Ollama-Vision-Beschreibung
(aus communication/telegram.py extrahiert, analog zu core/voice.py für Whisper)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import core.vision as vision


class TestDescribeImage:
    def test_gibt_beschreibung_zurueck(self):
        fake_client = MagicMock()
        fake_client.chat = AsyncMock(return_value=MagicMock(message=MagicMock(content="🖼️ BILD: Ein Sonnenuntergang.")))
        with patch("ollama.AsyncClient", return_value=fake_client):
            result = asyncio.run(vision.describe_image(b"fake-bytes", "Beschreibe das Bild."))
        assert result == "🖼️ BILD: Ein Sonnenuntergang."

    def test_fehler_gibt_fallback_text(self):
        fake_client = MagicMock()
        fake_client.chat = AsyncMock(side_effect=RuntimeError("kaputt"))
        with patch("ollama.AsyncClient", return_value=fake_client):
            result = asyncio.run(vision.describe_image(b"fake-bytes", "Beschreibe das Bild."))
        assert "nicht analysieren" in result.lower() or "fehler" in result.lower()

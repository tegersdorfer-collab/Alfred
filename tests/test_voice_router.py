"""Testet POST /api/voice/segment über einen echten FastAPI-TestClient.
Whisper/Fast-LLM werden gemockt — dieser Test prüft nur die Endpunkt-Verkabelung,
nicht die tatsächliche Spracherkennungs-Qualität (dafür gibt es keinen
automatisierten Test, siehe Plan-Constraints)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import wave
from unittest.mock import patch, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers.voice import build_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def _fake_wav_bytes() -> bytes:
    """Erzeugt eine winzige, gültige (stille) WAV-Datei — reicht für den
    Upload-Pfad-Test, ohne echtes Audio-Material zu brauchen."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * 1600)  # 0.1s Stille
    return buf.getvalue()


class TestVoiceSegmentEndpoint:
    def test_liefert_transkript_und_adress_entscheidung(self):
        with patch("web.routers.voice.transcribe_audio", new=AsyncMock(return_value="Wie war mein Schlaf?")), \
             patch("web.routers.voice.is_addressed_to_alfred", new=AsyncMock(return_value=True)):
            client = _make_client()
            resp = client.post(
                "/api/voice/segment",
                files={"audio": ("segment.wav", _fake_wav_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json() == {"text": "Wie war mein Schlaf?", "addressed": True}

    def test_nicht_adressiert_liefert_false(self):
        with patch("web.routers.voice.transcribe_audio", new=AsyncMock(return_value="Und dann meinte er zu mir...")), \
             patch("web.routers.voice.is_addressed_to_alfred", new=AsyncMock(return_value=False)):
            client = _make_client()
            resp = client.post(
                "/api/voice/segment",
                files={"audio": ("segment.wav", _fake_wav_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json()["addressed"] is False

    def test_leeres_transkript_ueberspringt_adress_check(self):
        with patch("web.routers.voice.transcribe_audio", new=AsyncMock(return_value="")), \
             patch("web.routers.voice.is_addressed_to_alfred", new=AsyncMock()) as mock_addr:
            client = _make_client()
            resp = client.post(
                "/api/voice/segment",
                files={"audio": ("segment.wav", _fake_wav_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json() == {"text": "", "addressed": False}
        mock_addr.assert_not_called()

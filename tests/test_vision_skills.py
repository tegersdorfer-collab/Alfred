"""Unit-Tests für core/skills/vision.py: Screen-Context-Awareness ('see_screen').
Mantis macht einen Screenshot (macOS screencapture) und beschreibt ihn via
core.vision.describe_image (Ollama-Vision, bereits für Telegram-Fotos genutzt)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import core.skills.vision as vision_skills


class TestSeeScreen:
    def test_macht_screenshot_und_beschreibt_ihn(self, tmp_path):
        from pathlib import Path
        fake_png = tmp_path / "screen.png"
        captured_cmd = {}

        def fake_run(cmd, **kwargs):
            captured_cmd["cmd"] = cmd
            # screencapture würde die Datei erzeugen — hier simuliert
            Path(cmd[-1]).write_bytes(b"FAKE_PNG_BYTES")
            return MagicMock(returncode=0)

        with patch("core.skills.vision.subprocess.run", side_effect=fake_run), \
             patch("core.skills.vision.tempfile.NamedTemporaryFile") as mock_tmp, \
             patch("core.skills.vision.describe_image", new=AsyncMock(return_value="🖥️ Ein Code-Editor mit Python-Code.")):
            mock_tmp.return_value.__enter__.return_value.name = str(fake_png)
            result = asyncio.run(vision_skills._see_screen())
        assert "Code-Editor" in result
        # launchd-Prozesse haben oft kein /usr/sbin im PATH — absoluter Pfad nötig,
        # sonst: "[Errno 2] No such file or directory: 'screencapture'"
        assert captured_cmd["cmd"][0] == "/usr/sbin/screencapture"

    def test_screencapture_fehlschlag_gibt_fehlermeldung(self):
        with patch("core.skills.vision.subprocess.run") as mock_run, \
             patch("core.skills.vision.tempfile.NamedTemporaryFile") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake_nonexistent_screen.png"
            mock_run.return_value = MagicMock(returncode=1, stderr=b"permission denied")
            result = asyncio.run(vision_skills._see_screen())
        assert "FEHLER" in result

    def test_fehlende_bildschirmaufnahme_berechtigung_gibt_konkreten_hinweis(self):
        """'could not create image from display' ist macOS' Standardfehler wenn
        die App keine Screen-Recording-Berechtigung hat (Privacy & Security) —
        Mantis soll das erkennen und Timo konkret sagen was zu tun ist."""
        with patch("core.skills.vision.subprocess.run") as mock_run, \
             patch("core.skills.vision.tempfile.NamedTemporaryFile") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake_nonexistent_screen.png"
            mock_run.return_value = MagicMock(returncode=1, stderr=b"could not create image from display 0x00000000")
            result = asyncio.run(vision_skills._see_screen())
        assert "Bildschirmaufnahme" in result
        assert "Privacy" in result or "Datenschutz" in result

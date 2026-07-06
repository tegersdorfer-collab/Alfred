"""Unit-Tests für core/skills/filesystem.py: voller Datei-/App-Zugriff (nicht nur
Mantis' eigene Codebase wie core/skills/system.py::read_own_code etc.).
Bewusst OHNE Lösch-Tool — nur Lesen/Schreiben/Auflisten/Öffnen."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, MagicMock

import core.skills.filesystem as fs_skills


class TestReadAnyFile:
    def test_liest_datei_inhalt(self, tmp_path):
        f = tmp_path / "notiz.txt"
        f.write_text("Hallo Welt")
        result = asyncio.run(fs_skills._read_any_file(str(f)))
        assert result == "Hallo Welt"

    def test_expandiert_tilde(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        f = tmp_path / "test.txt"
        f.write_text("Inhalt")
        result = asyncio.run(fs_skills._read_any_file("~/test.txt"))
        assert result == "Inhalt"

    def test_fehlende_datei_gibt_fehlermeldung(self, tmp_path):
        result = asyncio.run(fs_skills._read_any_file(str(tmp_path / "gibtsnicht.txt")))
        assert "FEHLER" in result or "nicht gefunden" in result.lower()

    def test_kuerzt_sehr_lange_dateien(self, tmp_path):
        f = tmp_path / "gross.txt"
        f.write_text("x" * 200_000)
        result = asyncio.run(fs_skills._read_any_file(str(f)))
        assert len(result) < 200_000


class TestWriteAnyFile:
    def test_schreibt_neue_datei(self, tmp_path):
        target = tmp_path / "sub" / "neu.txt"
        result = asyncio.run(fs_skills._write_any_file(str(target), "Test-Inhalt"))
        assert target.read_text() == "Test-Inhalt"
        assert "✅" in result or "geschrieben" in result.lower()

    def test_ueberschreibt_bestehende_datei(self, tmp_path):
        f = tmp_path / "bestehend.txt"
        f.write_text("alt")
        asyncio.run(fs_skills._write_any_file(str(f), "neu"))
        assert f.read_text() == "neu"


class TestListDirectory:
    def test_listet_dateien_und_ordner(self, tmp_path):
        (tmp_path / "a.txt").write_text("")
        (tmp_path / "ordner").mkdir()
        result = asyncio.run(fs_skills._list_directory(str(tmp_path)))
        assert "a.txt" in result
        assert "ordner" in result

    def test_nicht_existierendes_verzeichnis_gibt_fehler(self, tmp_path):
        result = asyncio.run(fs_skills._list_directory(str(tmp_path / "fehlt")))
        assert "FEHLER" in result or "nicht gefunden" in result.lower()


class TestOpenPath:
    def test_ruft_macos_open_mit_pfad_auf(self):
        with patch("core.skills.filesystem.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = asyncio.run(fs_skills._open_path("/Users/timo/Dokumente/rechnung.pdf"))
        mock_run.assert_called_once_with(
            ["open", "/Users/timo/Dokumente/rechnung.pdf"], capture_output=True
        )
        assert "✅" in result or "geöffnet" in result.lower()

    def test_fehlgeschlagenes_oeffnen_gibt_fehlermeldung(self):
        with patch("core.skills.filesystem.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b"not found")
            result = asyncio.run(fs_skills._open_path("/nicht/da.txt"))
        assert "FEHLER" in result or "fehlgeschlagen" in result.lower()


class TestOpenApp:
    def test_ruft_macos_open_dash_a_mit_appname_auf(self):
        with patch("core.skills.filesystem.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = asyncio.run(fs_skills._open_app("Notizen"))
        mock_run.assert_called_once_with(["open", "-a", "Notizen"], capture_output=True)
        assert "✅" in result or "gestartet" in result.lower()

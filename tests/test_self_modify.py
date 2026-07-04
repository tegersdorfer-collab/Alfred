"""Unit-Tests für domains/self_modify.py — Pfad-Sandbox (kein Git/Subprocess nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.self_modify import _safe_path, list_files, ALFRED_DIR


class TestSafePath:
    def test_erlaubte_datei_im_projekt(self):
        p = _safe_path("core/tools.py")
        assert p is not None
        assert p == (ALFRED_DIR / "core/tools.py").resolve()

    def test_top_level_py_erlaubt(self):
        assert _safe_path("orchestrator.py") is not None

    def test_geschwisterverzeichnis_mit_aehnlichem_namen_blockiert(self):
        # Regression: ALFRED_DIR="/…/Alfred" — "../AlfredEvilTwin/x.py" bestand
        # früher den reinen str.startswith(str(ALFRED_DIR))-Check.
        assert _safe_path("../AlfredEvilTwin/payload.py") is None

    def test_klassisches_traversal_blockiert(self):
        assert _safe_path("../../etc/passwd") is None
        assert _safe_path("../../../etc/passwd.py") is None

    def test_blockierte_datei(self):
        assert _safe_path("main.py") is None
        assert _safe_path(".env") is None
        assert _safe_path("core/db.py") is None

    def test_verbotene_dateiendung(self):
        assert _safe_path("core/secret.exe") is None

    def test_nicht_erlaubtes_top_level_verzeichnis(self):
        assert _safe_path("scripts/foo.py") is None


class TestListFiles:
    def test_geschwisterverzeichnis_blockiert(self):
        assert list_files("../AlfredEvilTwin") == []

    def test_normales_verzeichnis_liefert_dateien(self):
        files = list_files("core")
        assert any(f.endswith("tools.py") for f in files)

    def test_traversal_blockiert(self):
        assert list_files("../../etc") == []

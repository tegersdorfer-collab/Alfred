"""Unit-Tests für domains/self_modify.py — Pfad-Sandbox (kein Git/Subprocess nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import domains.self_modify as self_modify_module
from domains.self_modify import _safe_path, list_files, MANTIS_DIR


class TestSafePath:
    def test_erlaubte_datei_im_projekt(self):
        p = _safe_path("core/tools.py")
        assert p is not None
        assert p == (MANTIS_DIR / "core/tools.py").resolve()

    def test_top_level_py_erlaubt(self):
        assert _safe_path("orchestrator.py") is not None

    def test_geschwisterverzeichnis_mit_aehnlichem_namen_blockiert(self):
        # Regression: MANTIS_DIR="/…/Mantis" — "../MantisEvilTwin/x.py" bestand
        # früher den reinen str.startswith(str(MANTIS_DIR))-Check.
        assert _safe_path("../MantisEvilTwin/payload.py") is None

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
        assert list_files("../MantisEvilTwin") == []

    def test_normales_verzeichnis_liefert_dateien(self):
        files = list_files("core")
        assert any(f.endswith("tools.py") for f in files)

    def test_traversal_blockiert(self):
        assert list_files("../../etc") == []

    def test_liefert_dateien_wenn_repo_unter_dot_prefixed_verzeichnis_liegt(self, tmp_path, monkeypatch):
        # Regression: MANTIS_DIR selbst unter einem Punkt-Präfix-Verzeichnis
        # (z.B. .claude/worktrees/<name>/) darf nicht alle Dateien ausfiltern —
        # der Dotfile-Check muss relativ zu MANTIS_DIR prüfen, nicht am absoluten Pfad.
        fake_mantis_dir = tmp_path / ".hidden-parent" / "repo"
        core_dir = fake_mantis_dir / "core"
        core_dir.mkdir(parents=True)
        (core_dir / "tools.py").write_text("# dummy")

        monkeypatch.setattr(self_modify_module, "MANTIS_DIR", fake_mantis_dir)

        files = self_modify_module.list_files("core")
        assert any(f.endswith("tools.py") for f in files)

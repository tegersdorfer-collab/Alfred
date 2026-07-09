"""Tests für die reinen Teile der Backup-Verifikation (core/backup.py).
Der Restore selbst braucht PostgreSQL und wird separat live geprüft.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import backup
from core.backup import _swap_db


# ── _swap_db ──────────────────────────────────────────────────────────────────

def test_swap_db_replaces_dbname():
    url = "postgresql://localhost:5432/mantis"
    assert _swap_db(url, "postgres") == "postgresql://localhost:5432/postgres"


def test_swap_db_with_credentials():
    url = "postgresql://user:pw@db.host:5432/mantis"
    assert _swap_db(url, "mantis_restore_test_x") == \
        "postgresql://user:pw@db.host:5432/mantis_restore_test_x"


def test_swap_db_preserves_host_and_port():
    out = _swap_db("postgresql://localhost:5432/mantis", "temp")
    assert "localhost:5432" in out and out.endswith("/temp")


# ── verify_latest_backup: no-backup-Pfad (ohne PostgreSQL) ────────────────────

def test_verify_no_backups(monkeypatch, tmp_path):
    # BACKUP_DIR auf ein leeres Verzeichnis zeigen lassen → sauberer Fehlschlag,
    # kein DB-Zugriff.
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path)
    result = backup.verify_latest_backup()
    assert result["ok"] is False
    assert "Kein Backup" in result["message"]

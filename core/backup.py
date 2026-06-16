"""
Automatisches DB-Backup: täglicher pg_dump + Rotation.
Schützt Journal/Health/Memory-Daten vor Datenverlust (Festplattendefekt,
versehentliches DROP, kaputte Migration).
"""
import gzip
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import config
from core import db

log = logging.getLogger(__name__)

ALFRED_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = ALFRED_DIR / "data" / "backups"
KEEP_DAYS = 30


def run_backup() -> dict:
    """Erstellt ein komprimiertes pg_dump-Backup. Gibt {'ok', 'path'/'message'} zurück."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = BACKUP_DIR / f"alfred_{stamp}.sql.gz"

    try:
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-privileges", config.DATABASE_URL],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")[:500]
            return {"ok": False, "message": f"pg_dump fehlgeschlagen: {err}"}
        with gzip.open(out_path, "wb") as f:
            f.write(result.stdout)
    except FileNotFoundError:
        return {"ok": False, "message": "pg_dump nicht gefunden (PostgreSQL-Client-Tools installiert?)."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "pg_dump Timeout (>120s)."}
    except Exception as e:
        return {"ok": False, "message": f"Backup fehlgeschlagen: {e}"}

    _prune_old()
    size_mb = out_path.stat().st_size / 1024 / 1024
    log.info(f"💾 Backup erstellt: {out_path.name} ({size_mb:.1f} MB)")
    return {"ok": True, "path": str(out_path), "size_mb": round(size_mb, 1)}


def _prune_old(keep_days: int = KEEP_DAYS) -> None:
    cutoff = datetime.now() - timedelta(days=keep_days)
    for p in BACKUP_DIR.glob("alfred_*.sql.gz"):
        try:
            if datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
                p.unlink()
                log.info(f"🗑️  Altes Backup gelöscht: {p.name}")
        except Exception:
            pass


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    out = []
    for p in sorted(BACKUP_DIR.glob("alfred_*.sql.gz"), reverse=True):
        st = p.stat()
        out.append({
            "name": p.name,
            "size_mb": round(st.st_size / 1024 / 1024, 1),
            "created": datetime.fromtimestamp(st.st_mtime).isoformat(),
        })
    return out


def maybe_run_daily() -> None:
    """Läuft höchstens 1x/Tag – für den Idle-/Autopilot-Loop gedacht."""
    today = datetime.now().date().isoformat()
    if db.get_setting("last_backup_date") == today:
        return
    db.set_setting("last_backup_date", today)
    result = run_backup()
    if not result["ok"]:
        log.error(f"Tägliches Backup fehlgeschlagen: {result['message']}")

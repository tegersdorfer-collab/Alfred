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
from urllib.parse import urlparse, urlunparse

import config
from core import db

log = logging.getLogger(__name__)

MANTIS_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = MANTIS_DIR / "data" / "backups"
KEEP_DAYS = 30

# Tabellen, die in einem gesunden Restore vorhanden sein MÜSSEN (Kern-Datenbestand).
_EXPECTED_TABLES = ("memories", "tasks", "habits", "health_data", "chat_messages", "brain_notes")


def _swap_db(db_url: str, new_db: str) -> str:
    """Ersetzt den Datenbanknamen im Pfad eines postgresql://-URL. Rein/testbar."""
    return urlunparse(urlparse(db_url)._replace(path=f"/{new_db}"))


def run_backup() -> dict:
    """Erstellt ein komprimiertes pg_dump-Backup. Gibt {'ok', 'path'/'message'} zurück."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = BACKUP_DIR / f"mantis_{stamp}.sql.gz"

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
    for p in BACKUP_DIR.glob("mantis_*.sql.gz"):
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
    for p in sorted(BACKUP_DIR.glob("mantis_*.sql.gz"), reverse=True):
        st = p.stat()
        out.append({
            "name": p.name,
            "size_mb": round(st.st_size / 1024 / 1024, 1),
            "created": datetime.fromtimestamp(st.st_mtime).isoformat(),
        })
    return out


def verify_latest_backup() -> dict:
    """Spielt das jüngste Backup in eine Wegwerf-DB ein und prüft es.

    Ein Backup, dessen Restore nie getestet wurde, ist nur eine Vermutung. Diese
    Funktion beweist, dass sich das neueste Backup wirklich einspielen lässt und
    die Kern-Tabellen mit Daten enthält. Die Prod-DB wird NIE angefasst — es wird
    eine separate, offensichtlich benannte Datenbank angelegt und danach gedroppt.

    Gibt {'ok', 'message', ...} zurück.
    """
    backups = sorted(BACKUP_DIR.glob("mantis_*.sql.gz"), reverse=True)
    if not backups:
        return {"ok": False, "message": "Kein Backup zum Verifizieren gefunden."}
    backup = backups[0]

    stamp = backup.stem.replace("mantis_", "").replace(".sql", "")
    temp_db = f"mantis_restore_test_{stamp}"
    admin_url   = _swap_db(config.DATABASE_URL, "postgres")
    restore_url = _swap_db(config.DATABASE_URL, temp_db)

    def _admin(sql: str):
        return subprocess.run(
            ["psql", admin_url, "-v", "ON_ERROR_STOP=1", "-q", "-c", sql],
            capture_output=True, timeout=60,
        )

    try:
        # Reste einer früheren Verifikation entfernen, dann frische Wegwerf-DB anlegen
        _admin(f'DROP DATABASE IF EXISTS "{temp_db}"')
        r = _admin(f'CREATE DATABASE "{temp_db}"')
        if r.returncode != 0:
            return {"ok": False, "message": f"CREATE DATABASE fehlgeschlagen: {r.stderr.decode(errors='replace')[:300]}"}

        # Dump einspielen: entpacktes SQL via stdin an psql
        with gzip.open(backup, "rb") as f:
            dump = f.read()
        r = subprocess.run(
            ["psql", restore_url, "-v", "ON_ERROR_STOP=1", "-q"],
            input=dump, capture_output=True, timeout=180,
        )
        if r.returncode != 0:
            return {"ok": False, "message": f"Restore fehlgeschlagen: {r.stderr.decode(errors='replace')[:300]}"}

        # Sanity-Check über den frisch restaurierten Datenbestand (read-only, psycopg2)
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(restore_url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
            present = {row["table_name"] for row in cur.fetchall()}
            missing = [t for t in _EXPECTED_TABLES if t not in present]
            if missing:
                return {"ok": False, "message": f"Restore unvollständig — fehlende Tabellen: {missing}"}
            counts = {}
            for t in _EXPECTED_TABLES:
                cur.execute(f'SELECT COUNT(*) AS n FROM "{t}"')
                counts[t] = cur.fetchone()["n"]
        finally:
            conn.close()

        total = sum(counts.values())
        ok = total > 0
        msg = (f"✅ Restore OK: {backup.name} → {len(present)} Tabellen, "
               f"{total} Kern-Datensätze") if ok else \
              "Restore lief, aber Kern-Tabellen sind leer (verdächtig)."
        return {"ok": ok, "message": msg, "backup": backup.name, "counts": counts}
    except FileNotFoundError:
        return {"ok": False, "message": "psql nicht gefunden (PostgreSQL-Client-Tools installiert?)."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Restore-Verifikation Timeout."}
    except Exception as e:
        return {"ok": False, "message": f"Restore-Verifikation fehlgeschlagen: {e}"}
    finally:
        # Wegwerf-DB IMMER entfernen — auch bei jedem Fehler oben
        try:
            _admin(f'DROP DATABASE IF EXISTS "{temp_db}"')
        except Exception as e:
            log.warning(f"Wegwerf-DB {temp_db} konnte nicht gedroppt werden: {e}")


def maybe_verify_weekly() -> None:
    """Höchstens 1x/Woche das jüngste Backup restaurieren+prüfen — für den Idle-Loop.

    Erfolg wird nur geloggt; ein Fehlschlag landet zusätzlich im Fehler-Widget,
    damit ein kaputtes Backup nicht unbemerkt bleibt."""
    key = "last_backup_verify_week"
    week = datetime.now().strftime("%G-W%V")
    if db.get_setting(key) == week:
        return
    db.set_setting(key, week)
    result = verify_latest_backup()
    if result["ok"]:
        log.info(f"🔁 Backup-Restore verifiziert: {result['message']}")
    else:
        log.error(f"Backup-Restore-Verifikation FEHLGESCHLAGEN: {result['message']}")
        db.log_error("Backup-Restore-Verifikation", RuntimeError(result["message"]))


def maybe_run_daily() -> None:
    """Läuft höchstens 1x/Tag – für den Idle-/Autopilot-Loop gedacht."""
    today = datetime.now().date().isoformat()
    if db.get_setting("last_backup_date") == today:
        return
    db.set_setting("last_backup_date", today)
    result = run_backup()
    if not result["ok"]:
        log.error(f"Tägliches Backup fehlgeschlagen: {result['message']}")

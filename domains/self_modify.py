"""
Self-Modify: Jarvis kann seine eigene Codebase lesen und verändern.
Jede Änderung wird per Git gesichert; ein Watchdog-Subprocess übernimmt
Neustart + Health-Check + automatischen Rollback bei Fehler.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

JARVIS_DIR = Path(__file__).resolve().parent.parent

# Erlaubte Pfade (relativ zu JARVIS_DIR)
_ALLOWED_DIRS = {"domains", "core", "web", "memory", "tools", "llm", "identity"}
_ALLOWED_EXTENSIONS = {".py", ".html", ".md", ".json", ".css", ".js"}
_BLOCKED_FILES = {"core/db.py", ".env", "main.py"}   # kritische Dateien schützen


def _safe_path(rel_path: str) -> Optional[Path]:
    """Gibt absoluten Pfad zurück wenn erlaubt, sonst None."""
    p = (JARVIS_DIR / rel_path).resolve()
    if not str(p).startswith(str(JARVIS_DIR)):
        return None
    if rel_path in _BLOCKED_FILES:
        return None
    if p.suffix not in _ALLOWED_EXTENSIONS:
        return None
    first_dir = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    # Top-level .py und web/ immer erlaubt; Rest nur in erlaubten Dirs
    if first_dir not in _ALLOWED_DIRS and not (p.suffix == ".py" and len(Path(rel_path).parts) == 1):
        if first_dir not in _ALLOWED_DIRS:
            return None
    return p


def read_file(rel_path: str) -> str:
    """Liest eine Datei aus der Jarvis-Codebase."""
    p = _safe_path(rel_path)
    if p is None:
        return f"Fehler: Pfad '{rel_path}' nicht erlaubt."
    if not p.exists():
        return f"Fehler: Datei '{rel_path}' existiert nicht."
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"Fehler beim Lesen: {e}"


def list_files(rel_dir: str = "") -> list[str]:
    """Listet Dateien in einem Verzeichnis der Codebase."""
    base = (JARVIS_DIR / rel_dir).resolve() if rel_dir else JARVIS_DIR
    if not str(base).startswith(str(JARVIS_DIR)):
        return []
    result = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix in _ALLOWED_EXTENSIONS:
            rel = str(p.relative_to(JARVIS_DIR))
            if not any(part.startswith(".") or part == "__pycache__" for part in p.parts):
                result.append(rel)
    return result[:80]


def git_backup(description: str) -> str:
    """Committed aktuellen Zustand als Backup. Gibt Commit-Hash zurück."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=JARVIS_DIR, capture_output=True, check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"auto-backup: {description}", "--no-gpg-sign",
             "--allow-empty"],
            cwd=JARVIS_DIR, capture_output=True, text=True
        )
        # Commit-Hash holen
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=JARVIS_DIR, capture_output=True, text=True
        )
        return hash_result.stdout.strip()
    except Exception as e:
        log.error(f"git_backup fehlgeschlagen: {e}")
        return ""


def write_file(rel_path: str, content: str, description: str) -> dict:
    """
    Schreibt eine Datei und triggert einen gesicherten Neustart.
    Gibt {'ok': bool, 'backup_commit': str, 'message': str} zurück.
    """
    p = _safe_path(rel_path)
    if p is None:
        return {"ok": False, "message": f"Pfad '{rel_path}' nicht erlaubt."}

    # Backup vor Änderung
    backup_commit = git_backup(f"vor: {description[:60]}")
    if not backup_commit:
        return {"ok": False, "message": "Git-Backup fehlgeschlagen — Änderung abgebrochen."}

    # Datei schreiben
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        log.info(f"✏️  Datei geschrieben: {rel_path}")
    except Exception as e:
        return {"ok": False, "message": f"Schreiben fehlgeschlagen: {e}"}

    # Neustart via Watchdog triggern
    triggered = _trigger_restart(backup_commit)
    if not triggered:
        return {"ok": False, "message": "Datei geschrieben, aber Neustart fehlgeschlagen."}

    return {
        "ok": True,
        "backup_commit": backup_commit,
        "message": f"'{rel_path}' aktualisiert. Neustart läuft — Rollback-Punkt: {backup_commit[:8]}",
    }


def _trigger_restart(rollback_commit: str) -> bool:
    """Spawnt Watchdog-Subprocess der Neustart + Health-Check + ggf. Rollback übernimmt."""
    watchdog = str(JARVIS_DIR / "scripts" / "restart_watchdog.py")
    logfile  = "/tmp/jarvis_out.log"
    old_pid  = os.getpid()

    try:
        subprocess.Popen(
            [sys.executable, watchdog, str(old_pid), rollback_commit, logfile],
            start_new_session=True,   # überlebt Jarvis-Exit
            stdout=open("/tmp/jarvis_watchdog.log", "a"),
            stderr=subprocess.STDOUT,
        )
        log.info(f"🔄 Watchdog gestartet (rollback: {rollback_commit[:8]})")
        return True
    except Exception as e:
        log.error(f"Watchdog-Start fehlgeschlagen: {e}")
        return False

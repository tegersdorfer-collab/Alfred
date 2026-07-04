"""
Self-Modify: Alfred kann seine eigene Codebase lesen und verändern.
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

ALFRED_DIR = Path(__file__).resolve().parent.parent

# Erlaubte Pfade (relativ zu ALFRED_DIR)
_ALLOWED_DIRS = {"domains", "core", "web", "memory", "tools", "llm", "identity"}
_ALLOWED_EXTENSIONS = {".py", ".html", ".md", ".json", ".css", ".js"}
_BLOCKED_FILES = {
    "core/db.py", ".env", "main.py",
    "web/api.py",                 # Dashboard-Auth/Routing – Agent soll eigene Zugriffskontrolle nicht ändern
    "communication/telegram.py",  # Telegram-Allowlist – Agent soll sich nicht selbst freischalten können
    "domains/self_modify.py",     # Agent soll seine eigene Sandbox/Blockliste nicht erweitern können
}   # kritische Dateien schützen


def _safe_path(rel_path: str) -> Optional[Path]:
    """Gibt absoluten Pfad zurück wenn erlaubt, sonst None."""
    p = (ALFRED_DIR / rel_path).resolve()
    # is_relative_to statt String-Prefix-Vergleich: ein Geschwisterverzeichnis
    # wie "AlfredEvilTwin" würde den reinen str.startswith()-Check sonst bestehen.
    if not p.is_relative_to(ALFRED_DIR):
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
    """Liest eine Datei aus der Alfred-Codebase."""
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
    base = (ALFRED_DIR / rel_dir).resolve() if rel_dir else ALFRED_DIR
    if not base.is_relative_to(ALFRED_DIR):
        return []
    result = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix in _ALLOWED_EXTENSIONS:
            rel = str(p.relative_to(ALFRED_DIR))
            if not any(part.startswith(".") or part == "__pycache__" for part in p.parts):
                result.append(rel)
    return result[:80]


def git_backup(description: str) -> str:
    """Committed aktuellen Zustand als Backup. Gibt Commit-Hash zurück."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=ALFRED_DIR, capture_output=True, check=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"auto-backup: {description}", "--no-gpg-sign",
             "--allow-empty"],
            cwd=ALFRED_DIR, capture_output=True, text=True
        )
        # Commit-Hash holen
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ALFRED_DIR, capture_output=True, text=True
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

    old_content = p.read_text(encoding="utf-8") if p.exists() else ""

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

    _log_change("code_write", rel_path, description, old_content, content, backup_commit)

    # Neustart via Watchdog triggern
    triggered = _trigger_restart(backup_commit)
    if not triggered:
        return {"ok": False, "message": "Datei geschrieben, aber Neustart fehlgeschlagen."}

    return {
        "ok": True,
        "backup_commit": backup_commit,
        "message": f"'{rel_path}' aktualisiert. Neustart läuft — Rollback-Punkt: {backup_commit[:8]}",
    }


def _log_change(kind: str, path: str, description: str, old_content: str,
                new_content: str, commit: str = "") -> None:
    """Protokolliert eine Selbst-Veränderung fürs Dashboard ('Was hat Alfred selbst verändert')."""
    import difflib
    from core import db as _db

    diff = "\n".join(difflib.unified_diff(
        (old_content or "").splitlines(), (new_content or "").splitlines(),
        fromfile=f"{path} (vorher)", tofile=f"{path} (nachher)", lineterm="",
    ))
    _db.log_event("self_modify", f"{path}: {description[:200]}", {
        "kind": kind, "path": path, "commit": commit,
        "old_content": (old_content or "")[:200_000],
        "new_content": (new_content or "")[:200_000],
        "diff": diff[:50_000],
    })


def _trigger_restart(rollback_commit: str) -> bool:
    """Spawnt Watchdog-Subprocess der Neustart + Health-Check + ggf. Rollback übernimmt."""
    watchdog = str(ALFRED_DIR / "scripts" / "restart_watchdog.py")
    logfile  = "/tmp/alfred_out.log"
    old_pid  = os.getpid()

    try:
        subprocess.Popen(
            [sys.executable, watchdog, str(old_pid), rollback_commit, logfile],
            start_new_session=True,   # überlebt Alfred-Exit
            stdout=open("/tmp/alfred_watchdog.log", "a"),
            stderr=subprocess.STDOUT,
        )
        log.info(f"🔄 Watchdog gestartet (rollback: {rollback_commit[:8]})")
        return True
    except Exception as e:
        log.error(f"Watchdog-Start fehlgeschlagen: {e}")
        return False

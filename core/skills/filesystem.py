"""
Datei-/App-Zugriff — voller Zugriff auf das gesamte Mac-Dateisystem, nicht nur
Mantis' eigene Codebase (dafür siehe core/skills/system.py::read_own_code etc.).

Bewusst OHNE Lösch-Tool — nur Lesen/Schreiben/Auflisten/Öffnen, damit Mantis
Dateien nicht versehentlich zerstören kann. Timo hat diesen vollen Zugriff
explizit angefragt ("Mantis soll alle Rechte haben, alles zu öffnen und zu
bearbeiten") — dieselbe Vertrauensstufe wie das bereits bestehende
claude_code_run-Tool (spawnt einen vollwertigen Claude-Code-Subprocess).
"""
import logging
import subprocess
from pathlib import Path

from core import tools as T

log = logging.getLogger("core.skills")

_MAX_READ_CHARS = 50_000


def _resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


@T.register("read_any_file",
    "Liest den Inhalt einer beliebigen Datei auf Timos Mac (nicht nur Mantis' eigene "
    "Codebase — dafür gibt es read_own_code). Nutze dies wenn Timo dich bittet, eine "
    "bestimmte Datei/Dokument/Notiz zu lesen oder ihren Inhalt zusammenzufassen.",
    {"path": {"type": "string", "description": "Absoluter Pfad oder mit ~ beginnender Pfad, z.B. '~/Dokumente/notiz.txt'"}},
    ["path"], "filesystem")
async def _read_any_file(path: str) -> str:
    try:
        p = _resolve(path)
        if not p.exists() or not p.is_file():
            return f"FEHLER: Datei nicht gefunden: {p}"
        content = p.read_text(errors="replace")
        if len(content) > _MAX_READ_CHARS:
            content = content[:_MAX_READ_CHARS] + f"\n\n[… gekürzt, Datei hat {len(content)} Zeichen]"
        return content
    except Exception as e:
        return f"FEHLER beim Lesen: {e}"


@T.register("write_any_file",
    "Schreibt oder überschreibt eine beliebige Datei auf Timos Mac (nicht nur Mantis' "
    "eigene Codebase — dafür gibt es write_own_code). Erstellt fehlende Ordner automatisch. "
    "Nutze dies wenn Timo dich bittet, eine Notiz/Datei/Dokument zu erstellen oder zu bearbeiten.",
    {
        "path": {"type": "string", "description": "Absoluter Pfad oder mit ~ beginnender Pfad"},
        "content": {"type": "string", "description": "Vollständiger neuer Inhalt der Datei"},
    },
    ["path", "content"], "filesystem")
async def _write_any_file(path: str, content: str) -> str:
    try:
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"✅ Datei geschrieben: {p} ({len(content)} Zeichen)"
    except Exception as e:
        return f"FEHLER beim Schreiben: {e}"


@T.register("list_directory",
    "Listet Dateien und Unterordner eines beliebigen Verzeichnisses auf Timos Mac auf.",
    {"path": {"type": "string", "description": "Absoluter Pfad oder mit ~ beginnender Pfad"}},
    ["path"], "filesystem")
async def _list_directory(path: str) -> str:
    try:
        p = _resolve(path)
        if not p.exists() or not p.is_dir():
            return f"FEHLER: Verzeichnis nicht gefunden: {p}"
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        lines = [f"{'📄' if e.is_file() else '📁'} {e.name}" for e in entries]
        return "\n".join(lines) if lines else "(leer)"
    except Exception as e:
        return f"FEHLER beim Auflisten: {e}"


@T.register("open_path",
    "Öffnet eine Datei oder einen Ordner mit der Standard-App auf Timos Mac (wie ein "
    "Doppelklick im Finder). Nutze dies wenn Timo etwas 'öffnen' oder 'zeigen' möchte.",
    {"path": {"type": "string", "description": "Absoluter Pfad oder mit ~ beginnender Pfad"}},
    ["path"], "filesystem")
async def _open_path(path: str) -> str:
    p = _resolve(path)
    result = subprocess.run(["open", str(p)], capture_output=True)
    if result.returncode == 0:
        return f"✅ Geöffnet: {p}"
    return f"FEHLER beim Öffnen fehlgeschlagen: {(result.stderr or b'').decode(errors='replace')}"


@T.register("open_app",
    "Startet oder aktiviert eine Mac-Anwendung anhand ihres Namens (z.B. 'Notizen', "
    "'Kalender', 'Safari'). Nutze dies wenn Timo eine App öffnen möchte.",
    {"app_name": {"type": "string", "description": "Name der Anwendung, z.B. 'Notizen'"}},
    ["app_name"], "filesystem")
async def _open_app(app_name: str) -> str:
    result = subprocess.run(["open", "-a", app_name], capture_output=True)
    if result.returncode == 0:
        return f"✅ {app_name} gestartet."
    return f"FEHLER beim Starten fehlgeschlagen: {(result.stderr or b'').decode(errors='replace')}"

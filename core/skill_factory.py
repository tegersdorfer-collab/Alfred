"""
Skill-Factory: Alfred kann zur Laufzeit neue Tools für sich selbst erschaffen,
wenn ihm für eine Anfrage kein passendes Tool zur Verfügung steht – statt zu
sagen "das kann ich nicht", baut er sich die Fähigkeit.

Sicherheitsmodell:
- Statische AST-Prüfung vor jeder Aktivierung: nur Imports aus einer festen
  Whitelist, keine eval/exec/compile/__import__/os/subprocess/socket etc.
- Genau eine async-Funktion pro Skill, dekoriert mit @T.register(...).
- Neue Skills landen in domains/dynamic_skills/<name>.py, werden per Git
  committed (Nachvollziehbarkeit + Rollback per `git revert`) und sofort per
  importlib in die laufende Tool-Registry geladen – kein Neustart nötig.
- Tages-Limit gegen Fehler-Spiralen (wiederholt fehlschlagende Skill-Erzeugung).
"""
import ast
import importlib
import logging
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from core import db
from core import tools as T

log = logging.getLogger(__name__)

ALFRED_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = ALFRED_DIR / "domains" / "dynamic_skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

MAX_SKILLS_PER_DAY = 5

# Erlaubte Top-Level-Module/Pakete für Imports in generierten Skills.
_ALLOWED_ROOTS = {
    "asyncio", "json", "re", "math", "statistics", "datetime", "time", "uuid",
    "random", "secrets", "string", "decimal", "collections", "itertools",
    "textwrap", "unicodedata", "zoneinfo", "calendar", "urllib",
    "httpx", "config", "core", "domains", "llm", "memory", "tools",
}
_BANNED_ROOTS = {
    "os", "sys", "subprocess", "socket", "ctypes", "shutil", "pty",
    "importlib", "builtins", "pickle", "marshal", "multiprocessing",
    "threading", "signal", "resource",
}
_BANNED_NAMES = {
    "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
    "open", "input", "breakpoint",
}


class SkillValidationError(Exception):
    pass


def _check_import_root(root: str) -> None:
    if root in _BANNED_ROOTS:
        raise SkillValidationError(f"Import nicht erlaubt: '{root}' (gesperrtes Modul).")
    if root not in _ALLOWED_ROOTS:
        raise SkillValidationError(
            f"Import nicht erlaubt: '{root}' ist nicht auf der Whitelist "
            f"({sorted(_ALLOWED_ROOTS)})."
        )


def validate_source(source: str, expected_name: str) -> None:
    """Wirft SkillValidationError wenn der generierte Code unsicher/unpassend ist."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise SkillValidationError(f"Syntaxfehler: {e}")

    func_defs = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)]
    other_defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    if other_defs:
        raise SkillValidationError("Nur eine einzige async-Funktion ist erlaubt, keine weiteren Defs/Klassen.")
    if len(func_defs) != 1:
        raise SkillValidationError("Es muss genau eine 'async def'-Funktion definiert sein.")

    fn = func_defs[0]
    if fn.name != expected_name:
        raise SkillValidationError(f"Funktionsname muss exakt '{expected_name}' sein (war: '{fn.name}').")
    if not fn.decorator_list:
        raise SkillValidationError("Die Funktion muss mit @T.register(...) dekoriert sein.")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import_root(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            _check_import_root((node.module or "").split(".")[0])
        elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            raise SkillValidationError(f"Verbotener Name verwendet: '{node.id}'.")
        elif isinstance(node, ast.Attribute) and node.attr in _BANNED_NAMES:
            raise SkillValidationError(f"Verbotenes Attribut verwendet: '.{node.attr}'.")


def _today_count() -> int:
    log_ = db.get_setting("skill_factory_log", []) or []
    cutoff = datetime.now() - timedelta(hours=24)
    recent = [t for t in log_ if datetime.fromisoformat(t) > cutoff]
    return len(recent)


def _record_attempt() -> None:
    log_ = db.get_setting("skill_factory_log", []) or []
    cutoff = datetime.now() - timedelta(hours=24)
    log_ = [t for t in log_ if datetime.fromisoformat(t) > cutoff]
    log_.append(datetime.now().isoformat())
    db.set_setting("skill_factory_log", log_)


def _git_commit(message: str) -> str:
    try:
        subprocess.run(["git", "add", "-A", "domains/dynamic_skills"],
                       cwd=ALFRED_DIR, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", message, "--no-gpg-sign", "--allow-empty"],
                       cwd=ALFRED_DIR, capture_output=True, text=True)
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ALFRED_DIR,
                             capture_output=True, text=True)
        return out.stdout.strip()
    except Exception as e:
        log.warning(f"Skill-Factory: Git-Commit fehlgeschlagen: {e}")
        return ""


_PROMPT_INJECTION_PATTERNS = re.compile(
    r"(ignore (previous|above|all)|system\s*prompt|you are now|jailbreak|"
    r"disregard|override|<\s*/?system|<\s*/?instruction|\[INST\]|###\s*system)",
    re.IGNORECASE,
)


def _sanitize_text(text: str, field: str, max_len: int = 200) -> str:
    """Kürzt und prüft auf Prompt-Injection-Muster."""
    text = text.strip()[:max_len]
    if _PROMPT_INJECTION_PATTERNS.search(text):
        raise SkillValidationError(f"'{field}' enthält unerlaubte Anweisungs-Muster (Prompt-Injection).")
    return text


def create_skill(skill_name: str, description: str, source_code: str) -> dict:
    """
    Erstellt, validiert und aktiviert ein neues Tool zur Laufzeit.
    Gibt {'ok': bool, 'message': str} zurück.
    """
    if _today_count() >= MAX_SKILLS_PER_DAY:
        return {"ok": False, "message": (
            f"Tages-Limit erreicht ({MAX_SKILLS_PER_DAY} neue Skills/24h). "
            "Erstmal bestehende Skills nutzen/reparieren statt neue zu bauen."
        )}

    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", skill_name):
        return {"ok": False, "message": "skill_name muss snake_case sein, 3-40 Zeichen, nur a-z/0-9/_."}

    try:
        description = _sanitize_text(description, "description")
    except SkillValidationError as e:
        return {"ok": False, "message": str(e)}
    if skill_name in T.REGISTRY:
        return {"ok": False, "message": f"Tool '{skill_name}' existiert bereits."}

    file_path = SKILLS_DIR / f"{skill_name}.py"
    if file_path.exists():
        return {"ok": False, "message": f"Datei '{file_path.name}' existiert bereits."}

    _record_attempt()

    try:
        validate_source(source_code, skill_name)
    except SkillValidationError as e:
        return {"ok": False, "message": f"Validierung fehlgeschlagen: {e}"}

    header = (
        f'"""Automatisch von Alfred erstelltes Skill: {description}\n'
        f'Erstellt: {datetime.now().isoformat(timespec="seconds")}\n"""\n'
        "from core import tools as T\n\n\n"
    )
    full_source = header + source_code.strip() + "\n"

    try:
        file_path.write_text(full_source, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "message": f"Schreiben fehlgeschlagen: {e}"}

    # Sofort live laden (kein Neustart nötig) – Fehler hier → Datei wieder entfernen
    try:
        mod_name = f"domains.dynamic_skills.{skill_name}"
        if mod_name in __import__("sys").modules:
            importlib.reload(__import__("sys").modules[mod_name])
        else:
            importlib.import_module(mod_name)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        return {"ok": False, "message": f"Laden fehlgeschlagen, Skill verworfen: {e}"}

    if skill_name not in T.REGISTRY:
        file_path.unlink(missing_ok=True)
        return {"ok": False, "message": "Skill geladen, aber nicht in der Registry erschienen (Decorator fehlt?)."}

    commit = _git_commit(f"skill: {skill_name} ({description[:60]})")
    from domains.self_modify import _log_change
    _log_change("skill_create", f"domains/dynamic_skills/{skill_name}.py", description,
               "", full_source, commit)
    log.info(f"🛠️  Neues Skill erstellt und aktiviert: {skill_name}")
    return {
        "ok": True,
        "message": f"Skill '{skill_name}' erstellt und sofort aktiv. Commit: {commit[:8] if commit else 'n/a'}",
    }


def delete_skill(skill_name: str) -> dict:
    """Entfernt ein per create_skill erzeugtes Tool wieder (Datei + Registry)."""
    file_path = SKILLS_DIR / f"{skill_name}.py"
    if not file_path.exists():
        return {"ok": False, "message": f"'{skill_name}' ist kein dynamisch erstelltes Skill."}
    old_content = file_path.read_text(encoding="utf-8")
    file_path.unlink()
    T.REGISTRY.pop(skill_name, None)
    commit = _git_commit(f"skill entfernt: {skill_name}")
    from domains.self_modify import _log_change
    _log_change("skill_delete", f"domains/dynamic_skills/{skill_name}.py",
               f"Skill '{skill_name}' entfernt", old_content, "", commit)
    return {"ok": True, "message": f"Skill '{skill_name}' entfernt."}


def list_dynamic_skills() -> list[str]:
    return sorted(p.stem for p in SKILLS_DIR.glob("*.py") if p.stem != "__init__")


def load_all_on_startup() -> int:
    """Lädt alle bereits existierenden dynamischen Skills beim Start (Persistenz über Neustarts)."""
    count = 0
    for name in list_dynamic_skills():
        try:
            importlib.import_module(f"domains.dynamic_skills.{name}")
            count += 1
        except Exception as e:
            log.error(f"Dynamisches Skill '{name}' konnte nicht geladen werden: {e}")
    if count:
        log.info(f"🛠️  {count} dynamisch erstellte Skill(s) geladen")
    return count

"""
SKILL.md System — Skills als natürlichsprachliche Prozeduren in Markdown-Dateien.

Zweite Art von Skills neben Python-Code-Skills:
- Gespeichert in Alfred/skills/*.md
- YAML-Frontmatter: name, description, triggers, platforms
- Body: natürlichsprachliche Prozedur die Alfred folgen soll
- Werden in den System-Prompt injiziert wenn Trigger-Keywords matchen
- Werden vom Background-Review-Loop automatisch erstellt und aktualisiert

Format:
---
name: skill_name
description: Was dieser Skill tut
triggers: [keyword1, keyword2]
platforms: [macos, linux]  # optional
---
Prozedur-Text hier...
"""
import logging
import re
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SKILLS_MD_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILLS_MD_DIR.mkdir(parents=True, exist_ok=True)

# In-Memory-Index: name → {frontmatter, body, triggers, mtime}
_INDEX: dict[str, dict] = {}
_LAST_SCAN: float = 0.0
_SCAN_INTERVAL = 30.0  # Sekunden zwischen Auto-Scans


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parst YAML-ähnliches Frontmatter aus ---...--- Block."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 4:].strip()
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            v = v.strip()
            # Listen: [a, b, c]
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            fm[k.strip()] = v
    return fm, body


def _load_one(path: Path) -> Optional[dict]:
    try:
        content = path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(content)
        name = fm.get("name") or path.stem
        raw_triggers = fm.get("triggers", [])
        if isinstance(raw_triggers, str):
            raw_triggers = [t.strip() for t in raw_triggers.split(",")]
        triggers = [t.lower() for t in raw_triggers if t]
        # Fallback: Wörter aus name/description als Trigger
        if not triggers:
            desc = str(fm.get("description", ""))
            triggers = [w.lower() for w in re.findall(r"\w{4,}", desc)][:6]
        return {
            "name": name,
            "description": fm.get("description", ""),
            "triggers": triggers,
            "platforms": fm.get("platforms", []),
            "body": body,
            "path": str(path),
            "mtime": path.stat().st_mtime,
        }
    except Exception as e:
        log.debug(f"[SkillMD] Fehler beim Laden von {path.name}: {e}")
        return None


def scan_all() -> int:
    """Scannt skills/-Verzeichnis und baut Index neu."""
    global _LAST_SCAN
    _INDEX.clear()
    count = 0
    for p in SKILLS_MD_DIR.glob("*.md"):
        entry = _load_one(p)
        if entry:
            _INDEX[entry["name"]] = entry
            count += 1
    _LAST_SCAN = time.time()
    if count:
        log.info(f"[SkillMD] {count} Skill(s) geladen")
    return count


def reload_skill(name: str) -> None:
    """Lädt einen einzelnen Skill neu (nach Background-Review-Write)."""
    path = SKILLS_MD_DIR / f"{name}.md"
    if path.exists():
        entry = _load_one(path)
        if entry:
            _INDEX[entry["name"]] = entry


def _maybe_rescan() -> None:
    if time.time() - _LAST_SCAN > _SCAN_INTERVAL:
        scan_all()


def get_relevant_skills(query: str, max_skills: int = 4) -> list[dict]:
    """Gibt Skills zurück deren Trigger in der Query vorkommen (mit Präfix-Match für Flexion)."""
    _maybe_rescan()
    q = query.lower()
    q_words = set(re.findall(r"\w+", q))
    matches = []
    for skill in _INDEX.values():
        score = 0
        for t in skill["triggers"]:
            # Exakter Substring-Match
            if t in q:
                score += 2
                continue
            # Präfix-Match: "training" matcht "trainieren", "workout" matcht "workouts"
            for w in q_words:
                if w.startswith(t[:5]) or t.startswith(w[:5]):
                    score += 1
                    break
        if score > 0:
            matches.append((score, skill))
    matches.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in matches[:max_skills]]


def build_skill_context(query: str) -> str:
    """Gibt einen Kontext-Block für den System-Prompt zurück — nur relevante Skills."""
    skills = get_relevant_skills(query)
    if not skills:
        return ""
    lines = ["<skill_procedures>"]
    for s in skills:
        lines.append(f"## {s['name']}: {s['description']}")
        lines.append(s["body"])
        lines.append("")
    lines.append("</skill_procedures>")
    return "\n".join(lines)


def list_all() -> list[dict]:
    """Alle Skills im Index (für Dashboard/API)."""
    _maybe_rescan()
    return list(_INDEX.values())


def get_skill(name: str) -> Optional[dict]:
    _maybe_rescan()
    return _INDEX.get(name)


def delete_skill(name: str) -> bool:
    path = SKILLS_MD_DIR / f"{name}.md"
    if path.exists():
        path.unlink()
        _INDEX.pop(name, None)
        return True
    return False


def update_skill(name: str, body: str) -> bool:
    """Aktualisiert den Body eines bestehenden Skills."""
    path = SKILLS_MD_DIR / f"{name}.md"
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    fm_end = content.find("\n---", 3)
    if fm_end != -1:
        fm_part = content[:fm_end + 4]
        path.write_text(fm_part + "\n\n" + body + "\n", encoding="utf-8")
        reload_skill(name)
        return True
    return False

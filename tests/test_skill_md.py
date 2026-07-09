"""Tests für das SKILL.md-System (core/skill_md.py) — Pure-Funktionen ohne Dateisystem-
Abhängigkeit, plus Path-Traversal-Schutz. Bisher ungetestet.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.skill_md as smd
from core.skill_md import _parse_frontmatter, get_relevant_skills, _safe_skill_path


# ── Frontmatter-Parsing ───────────────────────────────────────────────────────

def test_parse_frontmatter_basic():
    content = "---\nname: foo\ndescription: Ein Test\n---\nDer Body hier."
    fm, body = _parse_frontmatter(content)
    assert fm["name"] == "foo"
    assert fm["description"] == "Ein Test"
    assert body == "Der Body hier."


def test_parse_frontmatter_list_values():
    content = "---\nname: foo\ntriggers: [lampe, licht, ir]\n---\nBody"
    fm, _ = _parse_frontmatter(content)
    assert fm["triggers"] == ["lampe", "licht", "ir"]


def test_parse_frontmatter_no_frontmatter():
    fm, body = _parse_frontmatter("Nur Text, kein Frontmatter")
    assert fm == {}
    assert body == "Nur Text, kein Frontmatter"


def test_parse_frontmatter_unterminated():
    # Öffnendes --- aber kein schließendes → als Body behandeln
    fm, body = _parse_frontmatter("---\nname: foo\nkein ende")
    assert fm == {}


# ── Trigger-Matching ──────────────────────────────────────────────────────────

@pytest.fixture
def seeded_index(monkeypatch):
    idx = {
        "training": {"name": "training", "description": "Trainingsplan",
                     "triggers": ["training", "workout"], "platforms": [], "body": "..."},
        "lampe": {"name": "lampe", "description": "Licht",
                  "triggers": ["lampe", "licht"], "platforms": [], "body": "..."},
    }
    monkeypatch.setattr(smd, "_INDEX", idx)
    monkeypatch.setattr(smd, "_maybe_rescan", lambda: None)  # kein Datei-Scan im Test
    return idx


def test_get_relevant_exact_match(seeded_index):
    res = get_relevant_skills("mach die lampe an")
    assert res and res[0]["name"] == "lampe"


def test_get_relevant_prefix_flexion(seeded_index):
    # "trainieren" soll über Präfix "train" den training-Skill treffen
    res = get_relevant_skills("ich will heute trainieren")
    assert any(s["name"] == "training" for s in res)


def test_get_relevant_no_match(seeded_index):
    assert get_relevant_skills("wie ist das wetter") == []


def test_get_relevant_ranks_by_score(seeded_index):
    # Query trifft beide Trigger von 'lampe' (lampe + licht) → höher als 'training'
    res = get_relevant_skills("lampe und licht und workout")
    assert res[0]["name"] == "lampe"


# ── Path-Traversal-Schutz ─────────────────────────────────────────────────────

def test_safe_path_normal_name():
    p = _safe_skill_path("mein_skill")
    assert p.name == "mein_skill.md"


@pytest.mark.parametrize("bad", ["../evil", "../../etc/passwd", "foo/bar", "a/../../b"])
def test_safe_path_rejects_traversal(bad):
    with pytest.raises(ValueError):
        _safe_skill_path(bad)

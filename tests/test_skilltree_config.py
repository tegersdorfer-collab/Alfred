import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.config import AXES, NODE_DEFS, QUEST_POOL, axis_by_key

def test_five_start_axes_present():
    keys = {a["key"] for a in AXES}
    assert keys == {"koerper", "wissen", "schaffen", "geist", "disziplin"}

def test_every_axis_has_components_with_valid_retention():
    valid = {"fast", "slow", "permanent"}
    for a in AXES:
        assert a["components"], f"{a['key']} ohne Komponenten"
        for kind, comp in a["components"].items():
            assert comp["retention"] in valid
            assert comp["weight"] > 0

def test_axis_by_key_roundtrip():
    assert axis_by_key("koerper")["label"] == "Körper"
    assert axis_by_key("nope") is None

def test_node_defs_reference_existing_axes():
    axis_keys = {a["key"] for a in AXES}
    for nd in NODE_DEFS:
        assert nd["axis"] in axis_keys

def test_quests_reference_existing_axes():
    axis_keys = {a["key"] for a in AXES}
    for q in QUEST_POOL:
        assert q["axis"] in axis_keys
        assert q["target_count"] > 0

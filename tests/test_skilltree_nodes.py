import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.skilltree.nodes import unlocked_nodes

NODES = [
    {"key": "dl_100", "label": "100 kg Kreuzheben", "axis": "koerper", "signal_kind": "deadlift", "threshold": 100.0},
    {"key": "dl_140", "label": "140 kg Kreuzheben", "axis": "koerper", "signal_kind": "deadlift", "threshold": 140.0},
]

def test_node_unlocks_when_threshold_ever_reached():
    sigs = [{"axis": "koerper", "kind": "deadlift", "value": 110.0, "ts": "2026-05-01", "source": "fitness", "count": 1}]
    keys = [n["key"] for n in unlocked_nodes(sigs, NODES)]
    assert keys == ["dl_100"]  # 110 ≥ 100, aber < 140

def test_node_stays_unlocked_even_if_later_value_lower():
    # permanent: einmal erreicht bleibt freigeschaltet, auch wenn die Form später sinkt
    sigs = [
        {"axis": "koerper", "kind": "deadlift", "value": 145.0, "ts": "2026-03-01", "source": "f", "count": 1},
        {"axis": "koerper", "kind": "deadlift", "value": 90.0, "ts": "2026-07-01", "source": "f", "count": 1},
    ]
    assert {n["key"] for n in unlocked_nodes(sigs, NODES)} == {"dl_100", "dl_140"}

def test_no_signal_no_unlock():
    assert unlocked_nodes([], NODES) == []

def test_node_ignores_same_kind_other_axis():
    # gleicher signal_kind auf fremder Achse darf ein Node nicht freischalten
    sigs = [{"axis": "wissen", "kind": "deadlift", "value": 200.0, "ts": "2026-05-01", "source": "x", "count": 1}]
    assert unlocked_nodes(sigs, NODES) == []

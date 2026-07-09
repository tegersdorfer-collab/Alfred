"""Tests für die reine Nachrichten-Normalisierung des Ollama-Providers
(llm/local.py::_build_messages) — in jedem LLM-Call genutzt, kein Netzwerk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.local import OllamaProvider, _embed_cache_key
from llm.base import Message


def _provider():
    # Konstruktor baut nur einen AsyncClient (kein Netzwerk-Call)
    return OllamaProvider(model="test:1b", embed_model="emb:1b")


def test_build_messages_prepends_system():
    p = _provider()
    out = p._build_messages([{"role": "user", "content": "hi"}], system="Du bist Mantis")
    assert out[0] == {"role": "system", "content": "Du bist Mantis"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_build_messages_no_system():
    p = _provider()
    out = p._build_messages([{"role": "user", "content": "hi"}], system=None)
    assert len(out) == 1 and out[0]["role"] == "user"


def test_build_messages_accepts_message_objects():
    p = _provider()
    out = p._build_messages([Message(role="user", content="frage")], system=None)
    assert out == [{"role": "user", "content": "frage"}]


def test_build_messages_mixed_dict_and_object():
    p = _provider()
    msgs = [Message(role="user", content="a"), {"role": "assistant", "content": "b"}]
    out = p._build_messages(msgs, system=None)
    assert [m["content"] for m in out] == ["a", "b"]


def test_embed_cache_key_strips_and_truncates():
    assert _embed_cache_key("  hallo  ") == "hallo"
    assert len(_embed_cache_key("x" * 1000)) == 512

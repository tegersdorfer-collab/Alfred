"""Tests für Orchestrator.lzg_embed — der synchrone Embedding-Wrapper darf den
Event-Loop nie einfrieren und muss aus Worker-Threads funktionieren.

(Der alte Code rief asyncio.get_event_loop() im Worker-Thread auf → RuntimeError
→ Embeddings über die API waren immer leer; auf dem Loop-Thread blockierte er
den ganzen Loop 10s. Beides hier abgedeckt.)
"""

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import Orchestrator


class FakeEmbedLLM:
    async def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


def _fake_orch(loop) -> types.SimpleNamespace:
    """Minimales Objekt mit den Attributen, die lzg_embed braucht."""
    return types.SimpleNamespace(_main_loop=loop, embed_llm=FakeEmbedLLM())


def test_embed_from_worker_thread_works():
    async def main():
        fake = _fake_orch(asyncio.get_running_loop())
        # so wie die API-Router es tun: sync-Aufruf in einem Worker-Thread
        return await asyncio.to_thread(Orchestrator.lzg_embed, fake, "hallo")

    assert asyncio.run(main()) == [1.0, 2.0, 3.0]


def test_embed_on_loop_thread_returns_empty_instead_of_freezing():
    async def main():
        fake = _fake_orch(asyncio.get_running_loop())
        # Direktaufruf AUF dem Loop-Thread → darf nicht blockieren, gibt []
        return Orchestrator.lzg_embed(fake, "hallo")

    assert asyncio.run(main()) == []


def test_embed_without_running_loop_returns_empty():
    fake = _fake_orch(None)
    assert Orchestrator.lzg_embed(fake, "hallo") == []

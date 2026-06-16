"""
Ollama-Backend für den Agent-Loop.
Übersetzt das einheitliche Backend-Interface in Ollama-API-Calls.
"""
import logging

import ollama as _ollama

from core.llm_gate import GATE
from core.backends.base import AgentBackend, StreamCb
import config

log = logging.getLogger(__name__)


class OllamaBackend(AgentBackend):
    def __init__(self, model: str | None = None, keep_alive: str | None = None):
        self._model = model or config.AGENT_MODEL_STRONG
        self._keep_alive = keep_alive or config.OLLAMA_KEEP_ALIVE
        self._client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)

    @property
    def model_name(self) -> str:
        return self._model

    def _extract_tool_calls(self, message) -> list[dict]:
        calls = []
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                calls.append({
                    "function": {
                        "name": tc.function.name,
                        "arguments": (
                            dict(tc.function.arguments)
                            if hasattr(tc.function.arguments, "items")
                            else tc.function.arguments
                        ),
                    }
                })
        return calls

    async def call(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        stream_cb: StreamCb | None,
        temperature: float,
        max_tokens: int,
        think: bool = False,
        force_tool_call: bool = False,
    ) -> tuple[str, list[dict]]:
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        kwargs = dict(model=self._model, messages=messages, options=options, think=think,
                     keep_alive=self._keep_alive)
        if tools:
            kwargs["tools"] = tools

        if stream_cb:
            parts: list[str] = []
            tool_calls: list[dict] = []
            last_len = 0
            async with GATE:
                async for chunk in await self._client.chat(**kwargs, stream=True):
                    m = chunk.message
                    if m.content:
                        parts.append(m.content)
                        full = "".join(parts)
                        if len(full) - last_len >= 50:
                            last_len = len(full)
                            try:
                                await stream_cb(full)
                            except Exception:
                                pass
                    calls = self._extract_tool_calls(m)
                    if calls:
                        tool_calls.extend(calls)
            full = "".join(parts)
            if full and not tool_calls:
                try:
                    await stream_cb(full)
                except Exception:
                    pass
            return full, tool_calls

        async with GATE:
            resp = await self._client.chat(**kwargs)
        return resp.message.content or "", self._extract_tool_calls(resp.message)

    async def warmup(self) -> None:
        try:
            async with GATE:
                await self._client.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": "ok"}],
                    options={"num_predict": 1},
                    keep_alive=self._keep_alive,
                )
            log.info(f"🔥 Modell {self._model} aufgewärmt")
        except Exception as e:
            log.debug(f"Warmup fehlgeschlagen: {e}")

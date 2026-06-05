"""
Claude API Provider – für schwere Tasks die lokales Modell überfordern.
Nur gezielt einsetzen um API-Kosten zu minimieren.
"""
from typing import AsyncIterator
import anthropic

from .base import LLMProvider, Message
import config


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        self._model = model or config.CLAUDE_MODEL
        self._client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    @property
    def model_name(self) -> str:
        return self._model

    def _to_anthropic(self, messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages
                if m.role in ("user", "assistant")]

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            messages=self._to_anthropic(messages),
        )
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens,
            messages=self._to_anthropic(messages),
        )
        if system:
            kwargs["system"] = system
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, text: str) -> list[float]:
        # Claude hat kein Embedding-API → Fehler werfen damit Caller
        # auf OllamaProvider für Embeddings zurückfällt
        raise NotImplementedError(
            "Claude hat kein Embedding-API. Nutze OllamaProvider.embed()."
        )

"""
Ollama Provider – lokale LLM-Inference.
Modell über OLLAMA_MODEL in .env konfigurierbar.
"""
import asyncio
from collections import OrderedDict
from typing import AsyncIterator
import ollama as _ollama

from .base import LLMProvider, Message
from core.llm_gate import GATE
import config


class OllamaProvider(LLMProvider):
    def __init__(self, model: str | None = None, embed_model: str | None = None):
        self._model = model or config.OLLAMA_MODEL
        self._embed_model = embed_model or config.LZG_EMBED_MODEL
        self._client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)
        self._embed_cache: OrderedDict[str, list[float]] = OrderedDict()
        self._embed_cache_max = 256

    @property
    def model_name(self) -> str:
        return self._model

    def _build_messages(
        self, messages: list, system: str | None
    ) -> list[dict]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for m in messages:
            if isinstance(m, dict):
                result.append({"role": m["role"], "content": m["content"]})
            else:
                result.append({"role": m.role, "content": m.content})
        return result

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        think: bool = False,
        format: str | dict | None = None,
    ) -> str:
        kwargs = dict(
            model=self._model,
            messages=self._build_messages(messages, system),
            options={"temperature": temperature, "num_predict": max_tokens,
                     "keep_alive": config.OLLAMA_KEEP_ALIVE},
            think=think,
        )
        if format:                       # 'json' oder JSON-Schema → erzwingt valides JSON
            kwargs["format"] = format
        async with GATE:
            response = await self._client.chat(**kwargs)
        return response.message.content

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        async for chunk in await self._client.chat(
            model=self._model,
            messages=self._build_messages(messages, system),
            options={"temperature": temperature, "num_predict": max_tokens},
            stream=True,
        ):
            if chunk.message.content:
                yield chunk.message.content

    async def embed(self, text: str) -> list[float]:
        key = text.strip()[:512]
        if key in self._embed_cache:
            return self._embed_cache[key]
        async with GATE:
            response = await self._client.embed(
                model=self._embed_model,
                input=text,
            )
        emb = response.embeddings[0]
        # LRU: ältesten Eintrag entfernen wenn voll
        if key in self._embed_cache:
            self._embed_cache.move_to_end(key)
        else:
            if len(self._embed_cache) >= self._embed_cache_max:
                self._embed_cache.popitem(last=False)
            self._embed_cache[key] = emb
        return emb

    async def check_model(self) -> bool:
        """Prüft ob das Modell verfügbar ist."""
        try:
            models = await self._client.list()
            names = [m.model for m in models.models]
            return any(self._model in n for n in names)
        except Exception:
            return False

    async def pull_if_missing(self) -> None:
        """Lädt Modell herunter falls nicht vorhanden."""
        if not await self.check_model():
            print(f"📥 Lade Modell {self._model}...")
            await self._client.pull(self._model)
            print(f"✅ {self._model} bereit")

        embed_ok = False
        try:
            models = await self._client.list()
            names = [m.model for m in models.models]
            embed_ok = any(self._embed_model in n for n in names)
        except Exception:
            pass

        if not embed_ok:
            print(f"📥 Lade Embedding-Modell {self._embed_model}...")
            await self._client.pull(self._embed_model)
            print(f"✅ {self._embed_model} bereit")

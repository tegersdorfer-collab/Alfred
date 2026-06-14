"""
MLX Provider – große lokale Modelle via Apple MLX (Apple Silicon optimiert).
Läuft auf M-Chips mit Unified Memory, kein CUDA nötig.

Gedacht für Background-Tasks (proaktiv, Aufgaben, Briefing) wo 5-30 Min Ladezeit ok ist.
Chat läuft über Haiku, nicht hier.

Modell wird lazy geladen (erst beim ersten Aufruf) und dann warm gehalten.
"""
import asyncio
import logging
import threading
from typing import AsyncIterator

from .base import LLMProvider, Message

log = logging.getLogger(__name__)

_load_lock = threading.Lock()
_model = None
_tokenizer = None
_current_model_name: str | None = None


def _load_model(model_id: str):
    """Lädt Modell + Tokenizer synchron (blockiert, dauert Minuten bei großen Modellen)."""
    global _model, _tokenizer, _current_model_name
    with _load_lock:
        if _model is not None and _current_model_name == model_id:
            return
        log.info(f"🧠 MLX: Lade Modell '{model_id}' — kann einige Minuten dauern…")
        try:
            from mlx_lm import load
            _model, _tokenizer = load(model_id)
            _current_model_name = model_id
            log.info(f"✅ MLX: Modell '{model_id}' geladen")
        except Exception as e:
            log.error(f"MLX Ladefehler: {e}")
            raise


def _generate_sync(
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Synchrone Inferenz — wird in einem Thread-Pool ausgeführt."""
    _load_model(model_id)
    from mlx_lm import generate
    result = generate(
        _model,
        _tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        temp=temperature,
        verbose=False,
    )
    return result


def _build_prompt(messages: list[Message], system: str | None, tokenizer) -> str:
    """Baut Chat-Prompt via tokenizer.apply_chat_template (falls vorhanden)."""
    chat = []
    if system:
        chat.append({"role": "system", "content": system})
    for m in messages:
        role = m.role if isinstance(m, Message) else m["role"]
        content = m.content if isinstance(m, Message) else m["content"]
        if role in ("user", "assistant"):
            chat.append({"role": role, "content": content})

    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template(
                chat, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            pass

    # Fallback: einfaches Format
    parts = []
    if system:
        parts.append(f"System: {system}\n")
    for m in chat:
        prefix = "User" if m["role"] == "user" else "Assistant"
        parts.append(f"{prefix}: {m['content']}")
    parts.append("Assistant:")
    return "\n".join(parts)


class MLXProvider(LLMProvider):
    """
    LLM-Provider für große lokale Modelle via Apple MLX.
    Modell-ID ist ein HuggingFace-Repo, z.B.:
        'mlx-community/Qwen2.5-72B-Instruct-4bit'
        'mlx-community/Llama-3.3-70B-Instruct-4bit'

    Nutze MLX_MODEL in .env um das Modell festzulegen.
    Nutze MLX_ENABLED=false um MLX zu deaktivieren (Fallback auf Ollama).
    """

    def __init__(self, model_id: str):
        self._model_id = model_id

    @property
    def model_name(self) -> str:
        return self._model_id

    def _prompt(self, messages: list[Message], system: str | None) -> str:
        # Tokenizer erst verfügbar nach _load_model
        _load_model(self._model_id)
        return _build_prompt(messages, system, _tokenizer)

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
        format: str | dict | None = None,
        think: bool = False,
    ) -> str:
        if format == "json":
            system = (system or "") + "\n\nAntworte ausschließlich mit validem JSON."
        prompt = await asyncio.to_thread(self._prompt, messages, system)
        log.info(f"🧠 MLX: Generiere Antwort (max {max_tokens} Tokens)…")
        result = await asyncio.to_thread(
            _generate_sync, self._model_id, prompt, max_tokens, temperature
        )
        log.info(f"✅ MLX: Antwort fertig ({len(result)} Zeichen)")
        return result.strip()

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> AsyncIterator[str]:
        # MLX unterstützt kein echtes async streaming — komplette Antwort auf einmal
        result = await self.chat(messages, system, temperature, max_tokens)
        yield result

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "MLXProvider hat kein Embedding-API. Nutze OllamaProvider.embed()."
        )

    async def preload(self) -> None:
        """Lädt das Modell vor (non-blocking, läuft im Hintergrund)."""
        log.info(f"🔄 MLX: Starte Preload von '{self._model_id}' im Hintergrund…")
        try:
            await asyncio.to_thread(_load_model, self._model_id)
        except Exception as e:
            log.error(f"MLX Preload fehlgeschlagen: {e}")

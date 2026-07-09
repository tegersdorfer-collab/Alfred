"""
RoutedLLMProvider — wählt je nach Aufgabe den optimalen lokalen LLM-Spezialisten.

Routing-Logik (Keyword-basiert, kein extra Router-Modell nötig):
  - Code/Skill-Generierung  → BG_CODE_MODEL    (Qwen2.5-Coder-7B)
  - Briefing/Insights       → BG_REASONING_MODEL (DeepSeek-R1-14B)
  - Alles andere            → BG_DEFAULT_MODEL  (qwen3.5:9b, bleibt Default)

Für den Rest von Mantis ist RoutedLLMProvider ein normaler LLMProvider —
kein Caller muss geändert werden.
"""
import logging
from .base import LLMProvider
from .local import OllamaProvider
import config

log = logging.getLogger(__name__)

# Keywords die auf Reasoning-Modell routen (Briefings, komplexe Synthese)
_REASONING_KEYWORDS = (
    "briefing", "morgen-briefing", "morgenupdate", "abend-review", "wöchentlicher rückblick",
    "pattern", "muster erkenn", "insight", "analyse", "analysiere", "weekly",
    "zusammenfassung der woche", "tages-zusammenfassung", "reflexion",
)

# Keywords die auf Code-Modell routen (Skill-Factory)
_CODE_KEYWORDS = (
    "def ", "async def ", "```python", "import ", "class ",
    "python-skill", "create_skill", "schreibe eine funktion",
    "python funktion", "python-funktion", "schreib python",
    "skill erstellen", "neuen skill", "skill schreiben",
)


def _detect_route(prompt: str) -> str:
    """Gibt 'reasoning', 'code' oder 'default' zurück."""
    lower = prompt.lower()
    if any(k in lower for k in _CODE_KEYWORDS):
        return "code"
    if any(k in lower for k in _REASONING_KEYWORDS):
        return "reasoning"
    return "default"


class RoutedLLMProvider(LLMProvider):
    """bg_llm-Ersatz der transparent zwischen Spezialisten routet."""

    def __init__(
        self,
        default_model:   str | None = None,
        reasoning_model: str | None = None,
        code_model:      str | None = None,
    ):
        self._default_model   = default_model   or getattr(config, "BG_DEFAULT_MODEL",   config.OLLAMA_MODEL)
        self._reasoning_model = reasoning_model or getattr(config, "BG_REASONING_MODEL", "")
        self._code_model      = code_model      or getattr(config, "BG_CODE_MODEL",      "")

        self._providers: dict[str, OllamaProvider] = {
            "default": OllamaProvider(model=self._default_model),
        }
        if self._reasoning_model:
            self._providers["reasoning"] = OllamaProvider(model=self._reasoning_model)
        if self._code_model:
            self._providers["code"] = OllamaProvider(model=self._code_model)

        log.info(
            f"RoutedLLMProvider: default={self._default_model} | "
            f"reasoning={self._reasoning_model or '–'} | "
            f"code={self._code_model or '–'}"
        )

    @property
    def model_name(self) -> str:
        return f"routed({self._default_model})"

    def _pick(self, prompt: str) -> OllamaProvider:
        route = _detect_route(prompt)
        provider = self._providers.get(route) or self._providers["default"]
        if route != "default":
            log.debug(f"Route → {route} ({provider._model})")
        return provider

    def _pick_from_messages(self, messages: list) -> OllamaProvider:
        combined = " ".join(
            (m["content"] if isinstance(m, dict) else m.content)
            for m in messages
        )
        return self._pick(combined)

    async def chat(self, messages, system=None, **kwargs) -> str:
        provider = self._pick_from_messages(messages)
        return await provider.chat(messages, system=system, **kwargs)

    async def complete(self, prompt: str, **kwargs) -> str:
        provider = self._pick(prompt)
        return await provider.complete(prompt, **kwargs)

    async def stream(self, messages, system=None, **kwargs):
        provider = self._pick_from_messages(messages)
        async for chunk in provider.stream(messages, system=system, **kwargs):
            yield chunk

    async def embed(self, text: str) -> list[float]:
        return await self._providers["default"].embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._providers["default"].embed_batch(texts)

    async def pull_if_missing(self) -> None:
        for name, p in self._providers.items():
            await p.pull_if_missing()

    async def warmup(self) -> None:
        """Nur Default vorwärmen — Reasoning/Code werden bei Bedarf geladen."""
        await self._providers["default"].pull_if_missing()

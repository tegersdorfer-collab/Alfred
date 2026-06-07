"""
Abstrakte Basisklasse für LLM-Provider.
Tausche einfach den Provider aus — Interface bleibt gleich.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class Message:
    role: str   # "user" | "assistant" | "system"
    content: str


class LLMProvider(ABC):
    """
    Einheitliches Interface für alle LLM-Provider.
    Implementiere diese Klasse für: Ollama, Claude, OpenAI, Gemini, etc.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        format: str | dict | None = None,
    ) -> str:
        """Einmalige Antwort generieren.
        format='json' (oder ein JSON-Schema-dict) erzwingt valide JSON-Ausgabe."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Antwort als Stream (Token für Token)."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Text in Embedding-Vektor umwandeln (für LZG)."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name des aktuellen Modells."""
        ...

"""
ClaudeCodeProvider – nutzt die `claude` CLI statt der Anthropic API.
Läuft über das Claude-Abo, keine API-Kosten.
Geeignet für schwere/komplexe Tasks die Qwen überfordern.
"""
import asyncio
import logging
import shutil
from typing import AsyncIterator

from llm.base import LLMProvider, Message

log = logging.getLogger(__name__)

CLAUDE_BIN = shutil.which("claude") or "claude"


class ClaudeCodeProvider(LLMProvider):
    """
    Ruft `claude -p <prompt>` als Subprocess auf.
    Kein Streaming, kein Embedding – nur chat().
    """

    @property
    def model_name(self) -> str:
        return "claude-code-cli"

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        # Baut einen einzelnen Prompt aus Messages + optionalem System-Prompt
        parts = []
        if system:
            parts.append(f"[System]\n{system}\n")
        for msg in messages:
            role = "User" if msg.role == "user" else "Assistant"
            parts.append(f"[{role}]\n{msg.content}")
        prompt = "\n\n".join(parts)

        cmd = [CLAUDE_BIN, "-p", prompt, "--output-format", "text"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                err = stderr.decode().strip()
                log.warning(f"claude CLI Fehler (rc={proc.returncode}): {err[:200]}")
                raise RuntimeError(f"claude CLI: {err[:200]}")

            result = stdout.decode().strip()
            log.debug(f"ClaudeCode: {len(result)} Zeichen zurück")
            return result

        except asyncio.TimeoutError:
            log.error("claude CLI Timeout nach 120s")
            raise RuntimeError("claude CLI Timeout")

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        # Kein echtes Streaming – gibt Ergebnis am Stück zurück
        result = await self.chat(messages, system=system,
                                 temperature=temperature, max_tokens=max_tokens)
        yield result

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("ClaudeCodeProvider unterstützt kein Embedding")

    @staticmethod
    def is_available() -> bool:
        """Prüft ob die claude CLI installiert ist."""
        return shutil.which("claude") is not None

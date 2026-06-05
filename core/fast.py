"""
Schneller Hilfs-LLM (llama3.2:3b) für günstige Entscheidungen:
Klassifikation, Ja/Nein-Urteile, kurze Zusammenfassungen.
Viel schneller als das 14B-Hauptmodell.
"""
import logging

import ollama as _ollama

from core.llm_gate import GATE
import config

log = logging.getLogger(__name__)
_client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)


async def ask(prompt: str, max_tokens: int = 20, temperature: float = 0.1) -> str:
    try:
        async with GATE:
            resp = await _client.chat(
                model=config.OLLAMA_FAST_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature, "num_predict": max_tokens,
                         "keep_alive": config.OLLAMA_KEEP_ALIVE},
            )
        return (resp.message.content or "").strip()
    except Exception as e:
        log.debug(f"fast.ask fehlgeschlagen: {e}")
        return ""


async def yes_no(question: str) -> bool:
    out = await ask(f"{question}\n\nAntworte NUR mit JA oder NEIN.", max_tokens=5)
    return out.strip().upper().startswith("JA") or out.strip().upper().startswith("YES")


async def warmup() -> None:
    try:
        await _client.chat(
            model=config.OLLAMA_FAST_MODEL,
            messages=[{"role": "user", "content": "ok"}],
            options={"num_predict": 1, "keep_alive": config.OLLAMA_KEEP_ALIVE},
        )
        log.info(f"🔥 Schnellmodell {config.OLLAMA_FAST_MODEL} aufgewärmt")
    except Exception as e:
        log.debug(f"Fast-Warmup fehlgeschlagen: {e}")

"""
Agentischer Kern – ReAct-Loop mit nativem Tool-Calling (Qwen3 via Ollama).
Das Modell entscheidet selbst, welche Tools es in welcher Reihenfolge nutzt.
Unterstützt Streaming der finalen Antwort (live-edit nach Telegram/Dashboard).
"""
import json
import logging
from typing import Awaitable, Callable

import ollama as _ollama

from core import tools as toolreg
from core.db import log_event
from core.llm_gate import GATE
from core.status import BUS
import config

log = logging.getLogger(__name__)

StreamCb = Callable[[str], Awaitable[None]]


class Agent:
    def __init__(self, model: str | None = None, max_steps: int = 5):
        self._model = model or config.OLLAMA_MODEL
        self._client = _ollama.AsyncClient(host=config.OLLAMA_BASE_URL)
        self._max_steps = max_steps

    async def run(
        self,
        messages: list[dict],
        system: str,
        stream_cb: StreamCb | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1500,
        use_tools: bool = True,
        allowed_tools: list[str] | None = None,
        force_tools: bool = False,
        think: bool = False,
        model: str | None = None,
        keep_alive: str | None = None,
    ) -> tuple[str, list[dict]]:
        """
        Führt den Agent-Loop aus.
        `model`/`keep_alive` überschreiben pro Aufruf das Default-Modell (für Routing).
        Gibt (finale_antwort, tool_trace) zurück.
        tool_trace = [{"tool": name, "args": {...}, "result": "..."}]
        """
        # Messages zu dicts normalisieren (akzeptiert Message-Dataclass oder dict)
        norm: list[dict] = []
        for m in messages:
            if isinstance(m, dict):
                norm.append(m)
            else:
                norm.append({"role": m.role, "content": m.content})
        msgs: list[dict] = [{"role": "system", "content": system}] + norm
        if not use_tools or allowed_tools == []:
            schemas = None                       # reines Gespräch → kein Tool-Prefill
        elif allowed_tools:
            schemas = toolreg.ollama_schemas(only=allowed_tools)
        else:
            schemas = toolreg.ollama_schemas()
        trace: list[dict] = []

        for step in range(self._max_steps):
            is_first = step == 0
            # Ersten Schritt erzwingen wenn Aktion erkannt und Tools vorhanden
            force = force_tools and is_first and bool(schemas)
            BUS.emit("thinking", "Denke nach…", detail=model or self._model)
            content, tool_calls = await self._call(
                msgs,
                tools=schemas,
                stream_cb=stream_cb,   # live streamen; bei Tool-Calls danach resetten
                temperature=temperature,
                max_tokens=max_tokens,
                think=think and is_first,
                model=model,
                keep_alive=keep_alive,
                force_tool_call=force,
            )

            if not tool_calls:
                # Kein Tool-Call obwohl erwartet → einmal retry mit expliziter Anweisung
                if force_tools and is_first and schemas:
                    log.debug("Kein Tool-Call trotz force_tools – retry mit explizitem Hint")
                    msgs.append({"role": "assistant", "content": content or ""})
                    msgs.append({
                        "role": "user",
                        "content": "[SYSTEM] Du hast gerade KEIN Tool aufgerufen. "
                                   "Rufe jetzt sofort das passende Tool auf – antworte nicht mit Text."
                    })
                    content, tool_calls = await self._call(
                        msgs, tools=schemas, stream_cb=None,
                        temperature=0.3, max_tokens=200,
                        model=model, keep_alive=keep_alive,
                    )
                    if not tool_calls:
                        # Immer noch kein Tool → originale Antwort zurückgeben
                        return content.strip() or (msgs[-2].get("content", "")).strip(), trace
                    # Tool-Call kam beim Retry → weiter im Loop
                    msgs = msgs[:-2]  # Retry-Nachrichten wieder entfernen
                else:
                    # Fertig – wurde bereits live gestreamt
                    return content.strip(), trace

            # Tool-Calls: Platzhalter zurücksetzen, dann ausführen
            if stream_cb:
                try:
                    await stream_cb("🔧 …")
                except Exception:
                    pass
            msgs.append({
                "role": "assistant",
                "content": content or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                BUS.emit("tool", f"🔧 {name}", detail=_short(args) or None)
                result = await toolreg.execute(name, args)
                trace.append({"tool": name, "args": args, "result": result[:500]})
                log_event("tool", f"{name}({_short(args)})", {"result": result[:300]})
                msgs.append({"role": "tool", "content": result, "name": name})

        # Max-Steps erreicht → finale Antwort ohne Tools (streamen)
        content, _ = await self._call(
            msgs, tools=None, stream_cb=stream_cb,
            temperature=temperature, max_tokens=max_tokens,
            model=model, keep_alive=keep_alive,
        )
        return content.strip(), trace

    async def _call(
        self,
        msgs: list[dict],
        tools: list[dict] | None,
        stream_cb: StreamCb | None,
        temperature: float,
        max_tokens: int,
        think: bool = False,
        model: str | None = None,
        keep_alive: str | None = None,
        force_tool_call: bool = False,
    ) -> tuple[str, list[dict]]:
        """Ein einzelner LLM-Call. Streamt wenn stream_cb gesetzt und keine Tools."""
        mdl = model or self._model
        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "keep_alive": keep_alive or config.OLLAMA_KEEP_ALIVE,
        }

        def _extract_calls(m):
            calls = []
            if getattr(m, "tool_calls", None):
                for tc in m.tool_calls:
                    calls.append({
                        "function": {
                            "name": tc.function.name,
                            "arguments": dict(tc.function.arguments)
                                         if hasattr(tc.function.arguments, "items")
                                         else tc.function.arguments,
                        }
                    })
            return calls

        # Streaming-Call (auch mit Tools – moderne Ollama-Versionen liefern tool_calls im Stream)
        if stream_cb:
            parts: list[str] = []
            tool_calls: list[dict] = []
            last_len = 0
            kwargs = dict(model=mdl, messages=msgs, options=options,
                          stream=True, think=think)
            if tools:
                kwargs["tools"] = tools
            async with GATE:
                async for chunk in await self._client.chat(**kwargs):
                    m = chunk.message
                    if m.content:
                        parts.append(m.content)
                        full = "".join(parts)
                        if len(full) - last_len >= 50:   # Telegram-Ratelimit schonen
                            last_len = len(full)
                            try:
                                await stream_cb(full)
                            except Exception:
                                pass
                    calls = _extract_calls(m)
                    if calls:
                        tool_calls.extend(calls)
            full = "".join(parts)
            if full and not tool_calls:
                try:
                    await stream_cb(full)
                except Exception:
                    pass
            return full, tool_calls

        # Nicht-Streaming Call (mit oder ohne Tools)
        kwargs = dict(model=mdl, messages=msgs, options=options, think=think)
        if tools:
            kwargs["tools"] = tools
        async with GATE:
            resp = await self._client.chat(**kwargs)
        m = resp.message
        return m.content or "", _extract_calls(m)

    async def warmup(self, model: str | None = None) -> None:
        """Lädt das Modell in den RAM (vermeidet Cold-Start bei erster Nachricht)."""
        mdl = model or self._model
        try:
            await self._client.chat(
                model=mdl,
                messages=[{"role": "user", "content": "ok"}],
                options={"num_predict": 1, "keep_alive": config.OLLAMA_KEEP_ALIVE},
            )
            log.info(f"🔥 Modell {mdl} aufgewärmt")
        except Exception as e:
            log.debug(f"Warmup fehlgeschlagen: {e}")


def _short(args: dict) -> str:
    try:
        s = json.dumps(args, ensure_ascii=False)
        return s[:60]
    except Exception:
        return str(args)[:60]

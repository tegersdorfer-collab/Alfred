"""
Globaler Ollama-Gate: serialisiert ALLE Modell-Aufrufe (chat, embed, stream, fast).
Auf einem lokalen Single-GPU-Mac vermeidet das Modell-Thrashing – jeder Call
bekommt die Hardware exklusiv und ist dadurch maximal schnell.
"""
import asyncio

GATE = asyncio.Lock()

"""Modell-Feld pro Kategorie für den Jarvis-Benchmark.

Beschluss (2026-07-09): volles Feld, aber KEIN qwen2.5-coder-Download — ornith
übernimmt die Coding-Rolle. Judge = Claude (neutral, blind).

Ein Eintrag ist entweder eine Ollama-Modell-ID oder "claude:<alias>" für die API.
"""

# Kleine, schnelle Router (frisch gezogen) + zwei 9B als Qualitäts-Obergrenze.
ROUTING = [
    "qwen2.5:0.5b", "llama3.2:1b", "qwen3:1.7b", "gemma2:2b", "gemma4:e2b",
    "qwen3.5:9b", "ornith:9b",
]

# Die eigentliche Jarvis-Erfahrung. Claude Haiku als Cloud-Referenz (Obergrenze).
CHAT = [
    "ornith:9b", "qwen3.5:9b", "gemma4:e2b", "deepseek-r1:14b", "claude:haiku",
]

# ornith ersetzt das (nicht geladene) Coding-Modell.
CODING = [
    "ornith:9b", "qwen3.5:9b", "deepseek-r1:14b",
]

REASONING = [
    "ornith:9b", "qwen3.5:9b", "deepseek-r1:14b", "gemma4:e2b",
]

BY_CATEGORY = {
    "routing": ROUTING,
    "chat": CHAT,
    "coding": CODING,
    "reasoning": REASONING,
}

# Judge (blind, neutral): ein Claude-Modell, das NICHT im lokalen Feld steht.
JUDGE_MODEL = "claude-sonnet-4-5"  # stärker als die Kandidaten, blind bewertend


def all_ollama_models() -> list[str]:
    seen = []
    for models in BY_CATEGORY.values():
        for m in models:
            if not m.startswith("claude:") and m not in seen:
                seen.append(m)
    return seen

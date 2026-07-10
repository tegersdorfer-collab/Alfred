"""Ergänzt den Reasoning-Vergleich um deepseek-r1:14b MIT aktiviertem Thinking.

Der Haupt-Benchmark lief mit think=False (Jarvis-Schnellmodus), was ein Reasoning-
Modell benachteiligt. Hier bekommt deepseek-r1 sein Thinking — die Antwortqualität
sollte steigen, die Latenz aber deutlich (Thinking erzeugt viele Tokens).

Ergebnis wird als Pseudo-Modell "deepseek-r1:14b-think" an raw.jsonl angehängt, damit
Report/Judge es automatisch mit aufnehmen.

    python3.14 -m bench.deepseek_thinking
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bench.run import _append, _strip_think
from bench.tasks import tasks_for_category

MODEL = "deepseek-r1:14b"
TAG = "deepseek-r1:14b-think"


def main() -> None:
    import ollama
    client = ollama.Client(host=config.OLLAMA_BASE_URL)
    print(f"Warmup {MODEL} (thinking) ...", flush=True)
    client.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1}, keep_alive="15m", think=True)

    for t in tasks_for_category("reasoning"):
        t0 = time.perf_counter()
        resp = client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": t["prompt"]}],
            options={"temperature": 0.2, "num_predict": 4096},
            keep_alive="15m", think=True,
        )
        wall = time.perf_counter() - t0
        # Bei think=True liegt die Antwort in message.content; Denkspur ggf. separat
        content = _strip_think(resp.message.content or "")
        ec = getattr(resp, "eval_count", 0) or 0
        ed = getattr(resp, "eval_duration", 0) or 0
        pe = getattr(resp, "prompt_eval_duration", 0) or 0
        _append({
            "model": TAG, "task_id": t["id"], "category": "reasoning",
            "output": content, "wall_s": round(wall, 3),
            "prefill_s": round(pe / 1e9, 3), "gen_tokens": ec,
            "tokens_per_s": round(ec / (ed / 1e9), 1) if ed else None,
        })
        print(f"  {t['id']:8} {wall:6.1f}s  gen_tokens={ec}", flush=True)

    print("Fertig — deepseek-thinking angehängt.", flush=True)


if __name__ == "__main__":
    main()

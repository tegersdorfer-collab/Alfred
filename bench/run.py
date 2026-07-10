"""Führt alle (Modell, Aufgabe)-Paare aus und schreibt Rohmetriken nach
bench/results/raw.jsonl (inkrementell, wiederaufnehmbar).

Äußere Schleife = Modell, damit jedes Ollama-Modell nur EINMAL geladen wird
(16-GB-Mac: Modelle passen nur einzeln in den RAM). think=False überall, weil
Jarvis auf schnelle Antworten zielt — Reasoning-Modelle (deepseek-r1) werden also
im „Schnellmodus" gemessen; ausgeleakte <think>-Blöcke werden entfernt.

    python3.14 -m bench.run            # alle offenen Paare
    python3.14 -m bench.run --fresh    # raw.jsonl vorher löschen
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bench import models as M
from bench.tasks import ALL_TASKS, tasks_for_category

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
RAW_PATH = os.path.join(RESULTS_DIR, "raw.jsonl")

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def _done_keys() -> set:
    if not os.path.exists(RAW_PATH):
        return set()
    keys = set()
    with open(RAW_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                keys.add((r["model"], r["task_id"]))
            except Exception:
                pass
    return keys


def _append(record: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(RAW_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Ollama ────────────────────────────────────────────────────────────────────

def _run_ollama(client, model: str, task: dict) -> dict:
    t0 = time.perf_counter()
    resp = client.chat(
        model=model,
        messages=[{"role": "user", "content": task["prompt"]}],
        options={"temperature": 0.2, "num_predict": 512},
        keep_alive="3m",
        think=False,
    )
    wall = time.perf_counter() - t0
    content = _strip_think(resp.message.content or "")
    ec = getattr(resp, "eval_count", 0) or 0
    ed = getattr(resp, "eval_duration", 0) or 0
    pe = getattr(resp, "prompt_eval_duration", 0) or 0
    return {
        "output": content,
        "wall_s": round(wall, 3),
        "prefill_s": round(pe / 1e9, 3),          # ≈ Time-to-first-token (warm)
        "gen_tokens": ec,
        "tokens_per_s": round(ec / (ed / 1e9), 1) if ed else None,
    }


# ── Claude ────────────────────────────────────────────────────────────────────

def _run_claude(client, alias: str, task: dict) -> dict:
    model = {"haiku": config.CLAUDE_CHAT_MODEL}.get(alias, config.CLAUDE_CHAT_MODEL)
    t0 = time.perf_counter()
    resp = client.messages.create(
        model=model, max_tokens=512,
        messages=[{"role": "user", "content": task["prompt"]}],
    )
    wall = time.perf_counter() - t0
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    out_tokens = getattr(resp.usage, "output_tokens", 0)
    return {
        "output": text.strip(),
        "wall_s": round(wall, 3),
        "prefill_s": None,                         # Cloud: kein sauberes TTFT hier
        "gen_tokens": out_tokens,
        "tokens_per_s": round(out_tokens / wall, 1) if wall else None,
    }


def main() -> None:
    if "--fresh" in sys.argv and os.path.exists(RAW_PATH):
        os.remove(RAW_PATH)

    import ollama
    oclient = ollama.Client(host=config.OLLAMA_BASE_URL)
    aclient = None
    if any(m.startswith("claude:") for cat in M.BY_CATEGORY.values() for m in cat):
        import anthropic
        aclient = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    done = _done_keys()
    # Modell → Liste der Aufgaben (aus allen Kategorien, in denen es antritt)
    model_tasks: dict[str, list] = {}
    for cat, mods in M.BY_CATEGORY.items():
        for mod in mods:
            model_tasks.setdefault(mod, []).extend(tasks_for_category(cat))

    total = sum(len(ts) for ts in model_tasks.values())
    done_count = len(done)
    print(f"{total} (Modell,Aufgabe)-Paare, {done_count} bereits erledigt.", flush=True)

    for model, tasks in model_tasks.items():
        pending = [t for t in tasks if (model, t["id"]) not in done]
        if not pending:
            continue
        is_claude = model.startswith("claude:")
        print(f"\n=== {model} ({len(pending)} offen) ===", flush=True)
        # Warmup (nur Ollama, damit die erste Messung nicht den Cold-Load enthält)
        if not is_claude:
            try:
                oclient.chat(model=model, messages=[{"role": "user", "content": "hi"}],
                             options={"num_predict": 1}, keep_alive="3m", think=False)
            except Exception as e:
                print(f"  Warmup fehlgeschlagen ({e}) — überspringe Modell", flush=True)
                continue
        for t in pending:
            try:
                if is_claude:
                    metrics = _run_claude(aclient, model.split(":", 1)[1], t)
                else:
                    metrics = _run_ollama(oclient, model, t)
                rec = {"model": model, "task_id": t["id"], "category": t["category"], **metrics}
                print(f"  {t['id']:8} {metrics['wall_s']:6.2f}s  "
                      f"{(str(metrics['tokens_per_s']) + ' tok/s') if metrics['tokens_per_s'] else '':>12}", flush=True)
            except Exception as e:
                rec = {"model": model, "task_id": t["id"], "category": t["category"],
                       "output": "", "error": str(e)[:200], "wall_s": None,
                       "prefill_s": None, "gen_tokens": 0, "tokens_per_s": None}
                print(f"  {t['id']:8} FEHLER: {str(e)[:80]}", flush=True)
            _append(rec)

    print("\nFertig. Rohdaten:", RAW_PATH, flush=True)


if __name__ == "__main__":
    main()

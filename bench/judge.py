"""Bewertet die Rohergebnisse.

- Routing: objektiv per Exact-Match gegen `expected` (kein Judge nötig).
- chat/coding/reasoning: BLIND von Claude bewertet — pro Aufgabe werden alle
  Modell-Antworten anonymisiert (gemischt, als A/B/C… gelabelt) an den Judge
  gegeben, damit kein Modellname die Note beeinflusst.

Schreibt bench/results/judged.jsonl (ein Datensatz pro (Modell, Aufgabe) mit `score` 0..1).

    python3.14 -m bench.judge
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from bench import models as M
from bench.tasks import ALL_TASKS
from core.jsonutil import extract_json

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
RAW_PATH = os.path.join(RESULTS_DIR, "raw.jsonl")
JUDGED_PATH = os.path.join(RESULTS_DIR, "judged.jsonl")

_TASK_BY_ID = {t["id"]: t for t in ALL_TASKS}


def _load_raw() -> list[dict]:
    rows = []
    with open(RAW_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _norm_label(text: str) -> str:
    """Erstes Wort, klein, ohne Satzzeichen — für den Routing-Exact-Match."""
    t = (text or "").strip().lower()
    for ch in ".,!?:;\"'`*()[]":
        t = t.replace(ch, " ")
    return t.split()[0] if t.split() else ""


def _score_routing(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        task = _TASK_BY_ID.get(r["task_id"])
        if not task or task.get("scoring") != "exact":
            continue
        expected = _norm_label(task["expected"])
        got = _norm_label(r.get("output", ""))
        out.append({**_slim(r), "score": 1.0 if got == expected else 0.0,
                    "expected": task["expected"], "got_label": got})
    return out


def _slim(r: dict) -> dict:
    return {k: r.get(k) for k in ("model", "task_id", "category", "wall_s",
                                  "prefill_s", "gen_tokens", "tokens_per_s")}


def _judge_open(rows: list[dict], client, judge_model: str) -> list[dict]:
    # nach Aufgabe gruppieren
    by_task: dict[str, list] = {}
    for r in rows:
        task = _TASK_BY_ID.get(r["task_id"])
        if task and task.get("scoring") == "judge" and not r.get("error"):
            by_task.setdefault(r["task_id"], []).append(r)

    out = []
    for tid, entries in by_task.items():
        task = _TASK_BY_ID[tid]
        # Deterministisch mischen (Reproduzierbarkeit), Modellnamen verbergen
        rnd = random.Random(tid)
        shuffled = entries[:]
        rnd.shuffle(shuffled)
        labels = [chr(ord("A") + i) for i in range(len(shuffled))]
        block = "\n\n".join(
            f"Antwort {lab}:\n{(e.get('output') or '(leer)')[:1500]}"
            for lab, e in zip(labels, shuffled)
        )
        prompt = (
            "Du bist ein strenger, fairer Bewerter. Bewerte jede Antwort auf die Aufgabe "
            f"nach dieser Rubrik (1–10):\n{task['rubric']}\n\n"
            f"AUFGABE:\n{task['prompt']}\n\n"
            f"ANTWORTEN:\n{block}\n\n"
            "Gib NUR ein JSON-Objekt zurück, das jedem Antwort-Buchstaben eine ganzzahlige "
            f"Note 1–10 zuordnet, z.B. {{\"A\": 7, \"B\": 9}}. Buchstaben: {', '.join(labels)}."
        )
        try:
            resp = client.messages.create(
                model=judge_model, max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            scores = extract_json(text, default={}) or {}
        except Exception as e:
            print(f"  Judge-Fehler bei {tid}: {str(e)[:80]}", flush=True)
            scores = {}
        for lab, e in zip(labels, shuffled):
            raw_score = scores.get(lab)
            norm = (float(raw_score) / 10.0) if isinstance(raw_score, (int, float)) else None
            out.append({**_slim(e), "score": norm, "judge_raw": raw_score})
        print(f"  {tid}: {scores}", flush=True)
    return out


def main() -> None:
    rows = _load_raw()
    print(f"{len(rows)} Rohdatensätze geladen.", flush=True)

    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Judge-Modell mit Fallback auf das bekannt funktionierende Chat-Modell
    judge_model = M.JUDGE_MODEL
    try:
        client.messages.create(model=judge_model, max_tokens=5,
                               messages=[{"role": "user", "content": "ok"}])
    except Exception as e:
        print(f"Judge-Modell {judge_model} nicht nutzbar ({str(e)[:60]}) → Fallback {config.CLAUDE_CHAT_MODEL}", flush=True)
        judge_model = config.CLAUDE_CHAT_MODEL

    judged = _score_routing(rows)
    print(f"Routing objektiv bewertet: {len(judged)}", flush=True)
    print("Blind-Judging der offenen Aufgaben ...", flush=True)
    judged += _judge_open(rows, client, judge_model)

    with open(JUDGED_PATH, "w", encoding="utf-8") as f:
        for r in judged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nBewertet: {len(judged)} → {JUDGED_PATH}", flush=True)


if __name__ == "__main__":
    main()

"""Aggregiert bench/results/judged.jsonl zu Tabellen pro Kategorie.

Zeigt Qualität UND Speed nebeneinander — bewusst OHNE einen einzelnen Gesamt-
Sieger auszurufen (Speed ist nicht immer entscheidend). Schreibt results/report.md.

    python3.14 -m bench.report
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
JUDGED_PATH = os.path.join(RESULTS_DIR, "judged.jsonl")
REPORT_PATH = os.path.join(RESULTS_DIR, "report.md")

CATS = ["routing", "chat", "coding", "reasoning"]


def _load() -> list[dict]:
    rows = []
    with open(JUDGED_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return statistics.mean(xs) if xs else None


def _agg(rows: list[dict], cat: str) -> list[dict]:
    by_model: dict[str, list] = {}
    for r in rows:
        if r["category"] == cat:
            by_model.setdefault(r["model"], []).append(r)
    out = []
    for model, rs in by_model.items():
        scores = [r["score"] for r in rs if isinstance(r.get("score"), (int, float))]
        walls = [r["wall_s"] for r in rs if isinstance(r.get("wall_s"), (int, float))]
        tps = [r["tokens_per_s"] for r in rs if isinstance(r.get("tokens_per_s"), (int, float))]
        prefills = [r["prefill_s"] for r in rs if isinstance(r.get("prefill_s"), (int, float))]
        out.append({
            "model": model,
            "n": len(rs),
            "quality": _mean(scores),                          # 0..1
            "median_wall": statistics.median(walls) if walls else None,
            "mean_wall": _mean(walls),
            "tps": _mean(tps),
            "prefill": _mean(prefills),
        })
    out.sort(key=lambda x: (x["quality"] is not None, x["quality"] or 0), reverse=True)
    return out


def _fmt(v, suffix="", pct=False, dash="—"):
    if v is None:
        return dash
    if pct:
        return f"{v*100:.0f}%"
    return f"{v:.2f}{suffix}"


def _table(cat: str, agg: list[dict]) -> str:
    qhead = "Genauigkeit" if cat == "routing" else "Qualität (Ø/10)"
    lines = [
        f"### {cat.capitalize()}",
        "",
        f"| Modell | {qhead} | Median-Latenz | Ø-Latenz | Prefill (≈TTFT) | Tokens/s | n |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in agg:
        q = _fmt(a["quality"], pct=(cat == "routing")) if cat == "routing" else \
            (f"{a['quality']*10:.1f}" if a["quality"] is not None else "—")
        lines.append(
            f"| {a['model']} | {q} | {_fmt(a['median_wall'],'s')} | {_fmt(a['mean_wall'],'s')} | "
            f"{_fmt(a['prefill'],'s')} | {_fmt(a['tps'])} | {a['n']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    rows = _load()
    parts = ["# Jarvis-Modell-Benchmark — Ergebnisse", "",
             f"Datensätze: {len(rows)}. Qualität: Routing = Exact-Match-Genauigkeit, "
             "offene Kategorien = Ø der blinden Claude-Bewertung (1–10). "
             "Speed im Schnellmodus (think=False).", ""]
    for cat in CATS:
        agg = _agg(rows, cat)
        if agg:
            parts.append(_table(cat, agg))
    report = "\n".join(parts)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\n→ {REPORT_PATH}")


if __name__ == "__main__":
    main()

"""Health-Scoring-Engine — reine Funktionen, kein I/O.

Normiert einzelne Metriken gegen die persönliche Baseline (oder Richtwerte) auf
0–100 und aggregiert sie zu Domain-Scores (Recovery/Sleep/Activity/Body). Fehlende
Werte werden ehrlich als "kein Score" behandelt (Graceful Degradation), nie erfunden.

Arbeitet über die Dict-Form der Health-Rows (siehe web/routers/_helpers._health_dict):
date, steps, active_calories, exercise_minutes, sleep_duration, sleep_deep,
resting_hr, hrv, weight, blood_oxygen.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

# Metriken, für die eine persönliche Baseline gebildet wird (Dict-Feldnamen der
# Health-Rows). Reihenfolge egal.
BASELINE_METRICS = (
    "steps", "active_calories", "exercise_minutes", "sleep_duration",
    "sleep_deep", "resting_hr", "hrv", "weight", "blood_oxygen",
)

DOMAIN_LABELS = {"recovery": "Recovery", "sleep": "Sleep", "activity": "Activity", "body": "Body"}
METRIC_LABELS = {
    "steps": "Schritte", "active_calories": "Aktiv-Kalorien",
    "exercise_minutes": "Trainingsminuten", "hrv": "HRV", "resting_hr": "Ruhepuls",
    "sleep_duration": "Schlafdauer", "sleep_deep": "Tiefschlaf",
    "blood_oxygen": "SpO₂", "weight": "Gewicht",
}


def compute_baselines(rows: list[dict], window: int = 60, min_n: int = 7) -> dict:
    """Pro Metrik den persönlichen Median + robuste Streuung (MAD) über die
    letzten `window` Tage.

    - Sortiert nach Datum, nutzt die jüngsten `window` Rows.
    - Ignoriert fehlende Werte.
    - < `min_n` Werte → Median ja, aber `spread=None` (Cold-Start → score_metric
      fällt auf Richtwerte zurück).
    - Keine Werte → {"median": None, "spread": None}.
    """
    recent = sorted(rows, key=lambda r: r.get("date") or "")[-window:] if window else list(rows)
    out: dict = {}
    for metric in BASELINE_METRICS:
        vals = [r[metric] for r in recent if r.get(metric) is not None]
        if not vals:
            out[metric] = {"median": None, "spread": None}
            continue
        median = float(statistics.median(vals))
        if len(vals) < min_n:
            out[metric] = {"median": median, "spread": None}
            continue
        mad = float(statistics.median([abs(v - median) for v in vals]))
        out[metric] = {"median": median, "spread": mad}
    return out


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _guideline_score(value: float, g: dict) -> float:
    """Trapez-Score: lo→0, ideal_lo..ideal_hi→100, hi→0, dazwischen linear.

    Deckt Zielbereiche (Schlaf 7–9 h) und offene "höher ist besser"-Metriken ab
    (ideal_hi/hi = inf → ab ideal_lo dauerhaft 100).
    """
    lo, ideal_lo, ideal_hi, hi = g["lo"], g["ideal_lo"], g["ideal_hi"], g["hi"]
    if value <= lo or value >= hi:
        return 0.0
    if ideal_lo <= value <= ideal_hi:
        return 100.0
    if value < ideal_lo:
        return round(100 * (value - lo) / (ideal_lo - lo), 1)
    return round(100 * (hi - value) / (hi - ideal_hi), 1)


def score_metric(
    value: float | None,
    baseline: dict | None = None,
    guideline: dict | None = None,
    higher_is_better: bool = True,
) -> float | None:
    """Eine Metrik auf 0–100 normieren.

    Baseline-Weg (bevorzugt): linear über ±2σ um den persönlichen Median —
    Median → 50, +2σ → 100, -2σ → 0 (bei higher_is_better; sonst invertiert).
    Fehlt der Wert, gibt es keinen Score (None).
    """
    if value is None:
        return None
    if baseline and baseline.get("spread"):
        median = baseline["median"]
        spread = baseline["spread"]
        z = (value - median) / (2 * spread)
        if not higher_is_better:
            z = -z
        return round(_clamp(50 + 50 * z, 0.0, 100.0), 1)
    if guideline:
        return _guideline_score(value, guideline)
    return None


# Richtwerte (Cold-Start) je Metrik — Trapez lo→ideal→hi. Tunebar.
_INF = float("inf")
_G_HRV = {"lo": 0.0, "ideal_lo": 60.0, "ideal_hi": _INF, "hi": _INF}          # ms, höher besser
_G_RHR = {"lo": 38.0, "ideal_lo": 42.0, "ideal_hi": 58.0, "hi": 90.0}          # Ruhepuls-Band
_G_DEEP = {"lo": 0.0, "ideal_lo": 1.5, "ideal_hi": _INF, "hi": _INF}           # h Tiefschlaf
_G_SLEEP = {"lo": 4.0, "ideal_lo": 7.0, "ideal_hi": 9.0, "hi": 11.0}           # h gesamt
_G_STEPS = {"lo": 0.0, "ideal_lo": 8000.0, "ideal_hi": _INF, "hi": _INF}
_G_ACAL = {"lo": 0.0, "ideal_lo": 500.0, "ideal_hi": _INF, "hi": _INF}
_G_EXMIN = {"lo": 0.0, "ideal_lo": 30.0, "ideal_hi": _INF, "hi": _INF}

# Domain-Definition: je Sub-Metrik Gewicht, Richtung, Richtwert. Gewichte pro
# Domain müssen sich nicht auf 1 summieren (werden renormiert).
# v1: recovery/sleep/activity. Body (Gewicht-Trend) und "Load gestern" (Cross-Day)
# sind bewusst offen (siehe Spec) und folgen, sobald die Semantik entschieden ist.
DEFAULT_CONFIG: dict = {
    "recovery": [
        {"metric": "hrv", "weight": 0.45, "higher_is_better": True, "guideline": _G_HRV},
        {"metric": "resting_hr", "weight": 0.30, "higher_is_better": False, "guideline": _G_RHR},
        {"metric": "sleep_deep", "weight": 0.25, "higher_is_better": True, "guideline": _G_DEEP},
    ],
    "sleep": [
        {"metric": "sleep_duration", "weight": 0.60, "higher_is_better": True, "guideline": _G_SLEEP},
        {"metric": "sleep_deep", "weight": 0.40, "higher_is_better": True, "guideline": _G_DEEP},
    ],
    "activity": [
        {"metric": "steps", "weight": 0.40, "higher_is_better": True, "guideline": _G_STEPS},
        {"metric": "active_calories", "weight": 0.30, "higher_is_better": True, "guideline": _G_ACAL},
        {"metric": "exercise_minutes", "weight": 0.30, "higher_is_better": True, "guideline": _G_EXMIN},
    ],
}


def compute_body_trend(
    rows: list[dict], metric: str = "weight", stable_threshold: float = 0.5,
) -> dict | None:
    """Gewicht (o.ä.) als Trend statt erzwungenem Score.

    → {"latest", "delta_7d", "delta_30d", "direction"}; None ohne Daten. Body ist
    bewusst kein 0–100-Score (ohne Ziel keine sinnvolle „Güte") — die Ansicht zeigt
    Richtung + Veränderung. Vergleichswert ist der jüngste Messpunkt am/ vor -N Tagen.
    """
    pts = sorted(
        [(r["date"], r[metric]) for r in rows
         if r.get(metric) is not None and r.get("date")],
        key=lambda p: p[0],
    )
    if not pts:
        return None
    latest_date = date.fromisoformat(pts[-1][0])
    latest = pts[-1][1]

    def _delta(n: int) -> float | None:
        cutoff = latest_date - timedelta(days=n)
        prior = [v for (d, v) in pts if date.fromisoformat(d) <= cutoff]
        return round(latest - prior[-1], 2) if prior else None

    d7, d30 = _delta(7), _delta(30)
    ref = d30 if d30 is not None else d7
    if ref is None or abs(ref) < stable_threshold:
        direction = "stable"
    else:
        direction = "down" if ref < 0 else "up"
    return {"latest": latest, "delta_7d": d7, "delta_30d": d30, "direction": direction}


def score_history(rows: list[dict], config: dict = DEFAULT_CONFIG) -> list[dict]:
    """Jeden Tag gegen die gemeinsame (Fenster-)Baseline scoren.

    → chronologisch sortierte Liste von {"date", "domains": {...}}. Der letzte
    Eintrag ist „heute". Die Baseline wird einmal über alle Rows gebildet.
    """
    if not rows:
        return []
    baselines = compute_baselines(rows)
    ordered = sorted(rows, key=lambda r: r.get("date") or "")
    return [
        {"date": r.get("date"), "domains": compute_domain_scores(r, baselines, config)}
        for r in ordered
    ]


def compute_domain_scores(
    row: dict,
    baselines: dict,
    config: dict = DEFAULT_CONFIG,
    min_coverage: float = 0.5,
) -> dict:
    """Sub-Metriken zu Domain-Scores aggregieren.

    Je Domain: gewichteter Mittelwerte der vorhandenen Sub-Scores; fehlende
    Metriken fliegen raus und die Gewichte werden renormiert. Fällt die Abdeckung
    (Anteil vorhandenen Gewichts) unter `min_coverage`, gibt es keinen Score,
    sondern status="insufficient_data" — ehrlich statt erfunden.
    """
    result: dict = {}
    for domain, comps in config.items():
        total_w = sum(c["weight"] for c in comps)
        components = []
        used_w = 0.0
        weighted_sum = 0.0
        for c in comps:
            value = row.get(c["metric"])
            sub = score_metric(
                value,
                baseline=baselines.get(c["metric"]),
                guideline=c.get("guideline"),
                higher_is_better=c.get("higher_is_better", True),
            )
            used = sub is not None
            components.append({
                "metric": c["metric"], "value": value, "score": sub,
                "weight": c["weight"], "used": used,
            })
            if used:
                used_w += c["weight"]
                weighted_sum += sub * c["weight"]
        coverage = round(used_w / total_w, 2) if total_w else 0.0
        if used_w > 0 and coverage >= min_coverage:
            result[domain] = {
                "score": round(weighted_sum / used_w, 1), "status": "ok",
                "coverage": coverage, "components": components,
            }
        else:
            result[domain] = {
                "score": None, "status": "insufficient_data",
                "coverage": coverage, "components": components,
            }
    return result


def health_narrative(today: dict, body: dict | None = None) -> str:
    """Deterministischer Klartext-Read aus den Domain-Scores.

    Nennt die vorhandenen Scores, den schwächsten Bereich + dessen Haupttreiber,
    fehlende Domains ehrlich als „offen", optional den Gewichts-Trend. Bewusst
    ohne LLM (verlässlich, offline, testbar) — eine LLM-Verfeinerung kann später
    diesen Text als Faktenbasis nehmen.
    """
    domains = today.get("domains", {})
    ok = [(k, v) for k, v in domains.items()
          if v.get("status") == "ok" and v.get("score") is not None]
    missing = [k for k, v in domains.items() if v.get("status") != "ok"]
    if not ok:
        return ("Noch keine belastbaren Health-Scores — sobald die COROS "
                "synchronisiert, füllen sie sich.")
    ok.sort(key=lambda kv: kv[1]["score"])
    headline = ", ".join(f"{DOMAIN_LABELS.get(k, k)} {round(v['score'])}" for k, v in ok)
    weak_key, weak = ok[0]
    text = headline + "."
    used = [c for c in weak.get("components", [])
            if c.get("used") and c.get("score") is not None]
    if used:
        driver = min(used, key=lambda c: c["score"])
        text += (f" Schwächster Bereich: {DOMAIN_LABELS.get(weak_key, weak_key)} — "
                 f"Haupttreiber {METRIC_LABELS.get(driver['metric'], driver['metric'])}.")
    else:
        text += f" Schwächster Bereich: {DOMAIN_LABELS.get(weak_key, weak_key)}."
    if missing:
        text += " " + ", ".join(DOMAIN_LABELS.get(k, k) for k in missing) + \
                " noch offen (Daten fehlen)."
    if body and body.get("latest") is not None:
        arrow = {"down": "↓", "up": "↑", "stable": "→"}.get(body.get("direction"), "")
        text += f" Gewicht {body['latest']} kg {arrow}."
    return text

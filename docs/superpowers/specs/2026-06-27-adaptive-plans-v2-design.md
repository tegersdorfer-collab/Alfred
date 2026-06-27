# Adaptiv-Plan v2 — Design / Spec

**Datum:** 2026-06-27
**Scope:** Alfreds Trainingsplan-Generierung deutlich aufwerten: durchdachter Prompt mit
voller Muskelabdeckung (inkl. Unterarme/Nacken/Bauch/Waden/hintere Schulter) und
A/B-Varianten pro Slot, die im Zyklus automatisch alternieren. Danach direkt neu generieren.

Baut auf `2026-06-26-adaptive-training-plans-design.md` auf. Der abschluss-basierte Zyklus
LOWER → JOGGEN → UPPER bleibt; geändert wird nur, **was** ein Lower/Upper-Tag enthält.

**Wichtig:** Fast vollständig backend-seitig. Die BodyOS-App ruft weiter `today-plan` auf und
erhält dieselbe Response-Struktur (eine flache `exercises`-Liste für den Tag) — die A/B-Wahl
passiert serverseitig. Keine App-Änderung außer ggf. dem Varianten-Label im `day_label`.

---

## 1. Generierungs-Prompt v2 (dauerhaft)

`build_prompt` in `domains/plan_generator.py` wird komplett ersetzt. Vorgaben:

- **Rolle:** erfahrener Strength-Coach / Personal Trainer. Ziel: maximal sinnvoller, sicherer
  Plan für das Profil (Ziel, Equipment, Erfahrung, Hinweise/Verletzungen).
- **Tagesstruktur:** schwerer Haupt-Compound → zweiter Compound → Akzessorisch/Isolation →
  bewusst vernachlässigte Muskeln.
- **Volle Abdeckung über A+B zusammen:** neben Brust/Rücken/Beine/Schulter/Arme auch
  **Unterarme, Nacken, Bauch/Core, Waden und hintere Schulter** einplanen.
- **Ziel-gerechte Schemata:** Hypertrophie überwiegend 3–4 Sätze × 6–12 Wdh, etwas Schweres
  (4–6) für die Hauptübung; realistische Startgewichte in kg; equipment-bewusst.
- **Variation:** Übungen sollen sich von der letzten Block-Auswahl unterscheiden; A und B
  eines Slots sollen sich klar unterscheiden (andere Übungen/Akzente).
- **Output: ein einziger JSON-Call** mit allen vier Listen (Schema unten).

## 2. Output-Schema & Validierung

```json
{
  "lowerA":[{"name":"...","weight":100,"reps":5,"sets":4,"rpe":8}],
  "lowerB":[...], "upperA":[...], "upperB":[...]
}
```

`normalize_plan(raw)` (in `domains/plan_generator.py`) wird auf A/B umgestellt:
- Validiert/säubert jede der vier Listen (gleiche Logik wie bisher: name nötig, sets 1–6,
  reps 1–30, weight/rpe optional, kaputte Einträge raus).
- **Pflicht:** `lowerA` **und** `upperA` müssen nicht-leer sein, sonst `None`.
- **Lenient:** fehlt/leer `lowerB` → `lowerB = lowerA`; analog `upperB = upperA`. So bleibt der
  Plan nutzbar, nur mit weniger Abwechslung.
- Rückgabe: Dict mit genau `lowerA/lowerB/upperA/upperB`.
- Müll/kein gültiges JSON → `generate_and_save` gibt `None`, alter Plan bleibt aktiv.

`max_tokens` für den Generierungs-Call auf ~2500 erhöhen (vier Listen).

## 3. A/B-Varianten-Auswahl (serverseitig)

Neue Hilfsfunktion in `domains/fitness.py`:
```python
def slot_workout_count(slot: str) -> int:
    """Wie oft slot (lower/upper) schon als Workout abgeschlossen wurde."""
    row = db.query_one(
        "SELECT COUNT(*) c FROM training_cycle_events WHERE slot=%s AND kind='workout'",
        (slot,))
    return row["c"] if row else 0
```

Variantenwahl: `variant = "A" if slot_workout_count(slot) % 2 == 0 else "B"`.
→ erste Lower-Session A, nächste B, dann wieder A … (wechselt automatisch jede Runde).

Diese Auswahl ist eine pure Funktion über dem Count, separat testbar:
```python
def pick_variant(slot_count: int) -> str:
    return "A" if slot_count % 2 == 0 else "B"
```
(in `domains/plan_generator.py`).

## 4. today-plan konsumiert die Variante

`web/routers/fitness.py` → `today_plan()`:
- Für Lower/Upper: `variant = plan_generator.pick_variant(fitness.slot_workout_count(day_type))`.
- Übungsquelle: `plan_json.get(day_type + variant)` (z.B. `"lowerA"`); fehlt sie oder kein
  aktiver Plan → `plan_generator.DEFAULT_PLAN[day_type]` (Fallback, unverändert).
- `day_label` ergänzen: `f"{CYCLE_LABEL[slot]} · {variant}"` (z.B. „Lower Body · A").
- `plan_source`/`plan_week` wie bisher. Jog-Tag unverändert.
- `build_sets`/`rest_sec`/Intensität bleiben unverändert (greifen pro Übung der gewählten Liste).

## 5. Nach dem Umbau: neu generieren

Nach erfolgreichem Backend-Umbau einmal `POST /api/fitness/plan/generate` ausführen, damit ein
frischer v2-Plan (mit A/B + voller Abdeckung) aktiv ist und Timo ihn sofort sieht.

## Testing

- `normalize_plan` (pure): gültiges A/B → alle vier Listen; fehlendes `upperA` → None;
  fehlendes `lowerB` → `lowerB == lowerA`; unrealistische sets/reps gekappt.
- `pick_variant` (pure): 0→A, 1→B, 2→A, 3→B.
- today-plan-Fallback: kein aktiver Plan → DEFAULT_PLAN, korrektes `day_type`.
- Bestehende Tests dürfen nicht brechen.
- End-to-End: Profil setzen → generieren → today-plan liefert `plan_source=alfred`,
  `day_label` mit Variante, nicht-leere Übungsliste.

## Nicht in diesem Scope

- Volle Session-Kontrolle (Sätze hinzufügen/tauschen, per-Satz-RPE, Skip-Fix) → **Spec 2**.
- App-UI-Änderungen über das Varianten-Label hinaus.

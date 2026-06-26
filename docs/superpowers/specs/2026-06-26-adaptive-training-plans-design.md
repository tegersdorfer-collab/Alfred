# Alfred adaptive Trainingspläne — Design / Spec

**Datum:** 2026-06-26
**Scope:** Alfred generiert vollautomatisch individuelle Trainingspläne (Übungen pro
LOWER/UPPER-Slot), fest für ~6 Wochen, danach mit neuer Übungsauswahl. Pläne werden
server-seitig gespeichert; `today-plan` konsumiert sie statt hardcodierter Listen.

Baut auf dem Trainingszyklus-Feature auf (siehe `2026-06-26-training-cycle-rework-design.md`):
Der Zyklus LOWER → JOGGEN → UPPER bleibt; der adaptive Plan füllt nur die Übungslisten
der Kraft-Tage (LOWER/UPPER). Joggen bleibt extern (Strava/HealthKit).

---

## Ziel

Statt fixer, von Hand gepflegter Übungslisten erstellt Alfred individuelle Pläne basierend
auf einem kleinen Nutzerprofil. Der Plan bleibt 6 Wochen stabil (damit Progression messbar
ist), danach generiert Alfred selbstständig einen neuen Block mit variierter Übungsauswahl.
Übungen, die im Plan stehen aber noch nicht in der Bibliothek sind, legt Alfred automatisch
an — kein Xcode-Rebuild nötig, da BodyOS Übungen rein server-getrieben rendert.

## 1. Trainingsprofil

Klein gehalten, gespeichert als Settings-Key `training_profile` (JSON-Blob via
`db.set_setting`/`db.get_setting`):

```json
{
  "goal": "muscle",          // muscle | strength | recomp
  "equipment": "gym",        // gym | home | minimal
  "experience": "advanced",  // beginner | intermediate | advanced
  "notes": ""                // Freitext: Verletzungen, Vorlieben, Ausschlüsse
}
```

Default bei fehlendem Profil: `{goal: "muscle", equipment: "gym", experience: "intermediate", notes: ""}`.

**Endpoints:**
- `GET /api/fitness/profile` → aktuelles Profil (oder Default).
- `PUT /api/fitness/profile` → Profil speichern (Body = obige Struktur, teilweise erlaubt).

## 2. Generierung (vollautomatisch)

### Trigger
- **Auto:** Alfreds Idle-Loop (Maintenance-Tick in `core/idle_loop.py`) prüft: kein aktiver
  Plan **oder** aktiver Plan älter als 42 Tage → Generierung anstoßen. Nur ein Versuch pro
  Tag (kein Hämmern bei Fehlern).
- **Manuell:** `POST /api/fitness/plan/generate` (für den ersten Plan / sofortige Neugenerierung).

### LLM
**Claude Haiku** (`orch.chat_llm`) — läuft nur ~alle 6 Wochen, Qualität bei strukturiertem
Output zählt. Fallback auf lokales qwen (`orch.bg_llm`) wenn Claude nicht erreichbar.
Aufruf wie bestehender Import-Endpoint: `chat(messages=..., temperature, max_tokens,
format="json")`.

### Input an die KI
- Das Trainingsprofil (Ziel, Equipment, Erfahrung, Hinweise).
- Übungen des letzten Plans (damit die neue Auswahl variiert).
- Zuletzt trainiertes Volumen je Muskelgruppe (`fitness.muscle_volume`) + zuletzt genutzte
  Übungen aus der Historie.

### Output (erwartetes JSON)
```json
{
  "lower": [{"name": "Squat", "weight": 100, "reps": 5, "sets": 4, "rpe": 8}, ...],
  "upper": [{"name": "Bench Press", "weight": 80, "reps": 6, "sets": 4, "rpe": 8}, ...]
}
```

### Validierung & Speicherung
- Pure Funktion `normalize_plan(raw: dict) -> dict | None`:
  - Verlangt nicht-leere Listen `lower` **und** `upper`.
  - Jede Übung braucht `name` (str) + `reps` (int) + `sets` (int); `weight`/`rpe` optional.
  - Säubert Typen, kappt unrealistische Werte (sets 1–6, reps 1–30), verwirft Übungen ohne
    Namen. Gibt `None` zurück, wenn lower oder upper danach leer wäre.
- Bei gültigem Plan: jede Übung `ensure_exercise(name)`, dann
  `save_training_plan(name="Alfred-Block", goal=<profil.goal>, weeks=6, plan=<normalized>)`.
- Bei `None` / LLM-Fehler: **alter Plan bleibt aktiv**, Fehler wird geloggt, kein Schreiben.

## 3. today-plan konsumiert den Plan

`web/routers/fitness.py` → `today_plan()`:
- Für LOWER/UPPER: aktiven Plan laden (`fitness.active_plan()`), `plan_json[slot]` als
  Übungsliste nehmen. Für jede Übung `build_sets(name, weight, reps, sets, rpe)` (Progressive
  Overload aus letzten geloggten Sätzen bleibt obendrauf).
- **Fallback:** Kein aktiver Plan oder Slot fehlt/leer → die bisherigen hardcodierten
  Default-Listen (als Konstante `DEFAULT_PLAN` ausgelagert). today-plan bricht nie.
- Jog-Tag unverändert (leere Übungsliste).

Die BodyOS-App ändert sich für die Plan-Konsumierung **nicht** — sie rendert weiter, was
today-plan liefert.

## 4. BodyOS UI

- **Neuer Settings-Screen „Trainingsprofil"** (`BodySettingsView` erweitern oder eigener
  View): Ziel/Equipment/Erfahrung als Picker, Hinweise als TextField → `PUT /api/fitness/profile`.
- **Heute-View**: kleines Badge „Plan: Woche X/6 · von Alfred" (X aus Plan-`created_at`
  berechnet) + Button **„Neuen Plan generieren"** → `POST /api/fitness/plan/generate`.

## Testing

- `normalize_plan(raw)` (pure): gültiges JSON → normalisiert; fehlendes upper → None;
  unrealistische sets/reps → gekappt; Übung ohne Namen → verworfen; leeres lower → None.
- `needs_regen(plan, today)` (pure): kein Plan → True; Plan < 42 Tage → False;
  Plan ≥ 42 Tage → True.
- today-plan-Fallback: kein aktiver Plan → hardcodierte Defaults, `day_type` korrekt.
- Bestehende Tests dürfen nicht brechen.

## Nicht in diesem Scope (YAGNI)

- Periodisierung innerhalb der 6 Wochen (Set/Rep-Wellen) — die tägliche Intensität via
  HRV/Schlaf deckt Tagesform schon ab.
- Freigabe-/Review-Flow vor Planwechsel — bewusst vollautomatisch gewählt.
- Anpassung der Übungsauswahl an Tagesform/Recovery — Plan ist der 6-Wochen-Rahmen,
  Tagessteuerung bleibt der Intensitäts-Faktor.

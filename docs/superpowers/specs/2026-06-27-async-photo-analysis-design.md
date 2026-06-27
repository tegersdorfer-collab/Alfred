# Asynchrone Foto-Kalorien-Analyse — Design / Spec

**Datum:** 2026-06-27
**Scope:** Den blockierenden Foto-Kalorien-Scan in BodyOS asynchron machen: Foto knipsen
→ Mahlzeit erscheint sofort als „wird analysiert…" → füllt sich selbst mit Makros, sobald
das Vision-Modell fertig ist. Plus Beschreibungsfeld beim Foto und Tap-to-Edit zum Korrigieren.

Behebt nebenbei den Timeout: Der Upload kehrt sofort zurück, die langsame lokale
Vision-Analyse läuft im Hintergrund ohne HTTP-Timeout.

---

## Ziel

Statt auf das langsame lokale Vision-Modell zu warten (und in Timeouts zu laufen), wird das
Foto sofort als „Pending"-Mahlzeit angelegt und im Hintergrund analysiert. Der Nutzer kann
sofort weitermachen; das Ergebnis erscheint, wenn es fertig ist.

## 1. Backend — asynchrone Analyse

`meals` erhält eine Spalte (Migration, idempotent):
```sql
ALTER TABLE meals ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'done';
```
(`'done'` als Default → bestehende Mahlzeiten bleiben sichtbar.)

`POST /api/nutrition/analyze-photo` (umgebaut):
1. Bild + `text` (Beschreibung) aus dem Multipart lesen.
2. **Sofort** eine Mahlzeit anlegen: `status='analyzing'`, `description` = Beschreibung (falls
   vorhanden) sonst „Wird analysiert…", `meal_type='snack'`, Makros NULL, `date=heute`.
3. Einen Hintergrund-Task starten (`asyncio.create_task`, Referenz in einem modulweiten Set
   halten gegen GC), der:
   - das Vision-Modell aufruft (wie bisher, `num_ctx=8192`), `extract_json` + `_sum_food_items`,
   - die Mahlzeit per UPDATE füllt: Name (Beschreibung falls gesetzt, sonst `food_name`),
     calories/protein_g/carbs_g/fat_g, `status='done'`,
   - bei Exception/leerem Ergebnis `status='failed'` setzt.
4. **Sofort** `{ "ok": true, "meal_id": <id>, "status": "analyzing" }` zurückgeben.

Neue Funktionen in `domains/nutrition.py`:
- `create_pending_meal(description) -> int` — legt die Pending-Mahlzeit an.
- `complete_meal(meal_id, name, calories, protein, carbs, fat) -> None` — füllt + `status='done'`.
- `fail_meal(meal_id) -> None` — `status='failed'`.
- `update_meal(meal_id, name, calories, protein, carbs, fat) -> None` — für Tap-to-Edit.

`today-nutrition` (bzw. die Mahlzeiten-Serialisierung) liefert `status` pro Mahlzeit mit.

**Robustheit:** Beim Start (`orchestrator`/Migration) verwaiste `status='analyzing'`-Mahlzeiten
(älter als z.B. heute, oder generell beim Start) auf `failed` setzen, damit nichts ewig dreht:
`UPDATE meals SET status='failed' WHERE status='analyzing'` als Startup-Cleanup.

## 2. Beschreibung beim Foto

Der `text`-Annotation-Parameter existiert schon und geht in den Vision-Prompt. Neu:
- App zeigt nach dem Knipsen/Wählen ein kleines Sheet „Beschreibung (optional)".
- Der Text geht als `text` an `analyze-photo` (Modell-Hinweis) **und** wird Mahlzeit-Name,
  falls angegeben.

## 3. Tap-to-Edit (Korrigieren)

Neuer Endpoint `PUT /api/nutrition/{id}` → `nutrition.update_meal(...)` (Name + Makros).
In der App: Mahlzeit in der Liste antippen → Edit-Sheet (vorausgefüllt mit aktuellen Werten)
→ Speichern.

## 4. App-Flow (`NutritionView`)

- **Foto-Pfad:** Kamera/Galerie → Beschreibung-Sheet → „Analysieren" → `analyzePhoto` (multipart
  mit Beschreibung) → kehrt sofort zurück → `vm.load()` → die Pending-Mahlzeit ist in der Liste.
- **Mahlzeiten-Liste:** `status='analyzing'` → Spinner + „wird analysiert…" statt Makros;
  `status='failed'` → „Analyse fehlgeschlagen" + Hinweis (löschen/erneut).
- **Polling:** Solange mindestens eine Mahlzeit `analyzing` ist, alle ~3 s `vm.load()` (Timer),
  stoppt automatisch, wenn keine mehr analysiert.
- **Tap-to-Edit:** Tippen auf eine Mahlzeit → Edit-Sheet (Name + Makros) → `PUT`.
- Der bisherige blockierende `AnalysisView` entfällt aus dem Foto-Pfad (Datei kann bleiben,
  wird aber nicht mehr aus `NutritionView` aufgerufen).

## 5. Testing

- **Backend pure/integration:** Migration idempotent; `create_pending_meal` legt
  `status='analyzing'` an; `complete_meal` füllt Makros + `status='done'`; `update_meal` ändert
  Werte; `_sum_food_items` (bereits getestet); Startup-Cleanup setzt analyzing→failed.
- **App:** Build + Deploy + Sichtung: Foto → Beschreibung → erscheint sofort als „wird
  analysiert…" → füllt sich → antippen/editieren; währenddessen andere Tabs nutzbar.

## Nicht in diesem Scope (YAGNI)

- Persistente Job-Queue / Wiederaufnahme nach Server-Neustart (in-memory Background-Task +
  Startup-Cleanup reichen; ein verwaister Task ist selten und wird als `failed` markiert).
- Push-Notification bei Fertigstellung (Polling reicht, solange die View offen ist).
- Bild dauerhaft speichern (Bytes gehen direkt in den Background-Task).

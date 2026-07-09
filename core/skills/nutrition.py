"""
Nutrition-Tools — aus core/skills.py extrahiert (verhaltensgleich).
Registriert sich via @T.register beim Import (durch core/skills/__init__.py).
"""
import logging

from core import tools as T
from domains import nutrition

log = logging.getLogger("core.skills")


@T.register("log_meal",
    "Protokolliert eine Mahlzeit. SCHÄTZE die Makros (Kalorien, Protein, Kohlenhydrate, "
    "Fett) realistisch selbst, wenn Timo sie nicht nennt (z.B. 'zwei Marmeladentoasts' "
    "≈ 300 kcal, 8g Protein, 50g Carbs, 8g Fett). Gib immer geschätzte Werte mit.",
    {"description": {"type": "string"},
     "meal_type": {"type": "string", "description": "breakfast | lunch | dinner | snack"},
     "calories": {"type": "integer", "description": "geschätzte Kalorien"},
     "protein_g": {"type": "number", "description": "geschätztes Protein in g"},
     "carbs_g": {"type": "number", "description": "geschätzte Kohlenhydrate in g"},
     "fat_g": {"type": "number", "description": "geschätztes Fett in g"}},
    ["description"], "nutrition")
async def _log_meal(description: str, meal_type: str = "snack",
                    calories: int = None, protein_g: float = None,
                    carbs_g: float = None, fat_g: float = None):
    nutrition.log_meal(description=description, meal_type=meal_type,
                       calories=calories, protein_g=protein_g,
                       carbs_g=carbs_g, fat_g=fat_g)
    macro = []
    if calories: macro.append(f"{int(calories)} kcal")
    if protein_g: macro.append(f"{int(protein_g)}g P")
    if carbs_g: macro.append(f"{int(carbs_g)}g C")
    if fat_g: macro.append(f"{int(fat_g)}g F")
    return f"Mahlzeit erfasst: {description}" + (f" ({', '.join(macro)})" if macro else "")

@T.register("nutrition_today", "Zeigt heutige Mahlzeiten und Makro-Summen.", {}, [], "nutrition")
async def _nutrition_today():
    t = nutrition.day_totals()
    meals = nutrition.meals_for()
    head = f"Heute: {int(t['kcal'])} kcal, {int(t['protein'])}g Protein, {int(t['carbs'])}g Carbs, {int(t['fat'])}g Fett."
    body = "\n".join(f"  {m['meal_type']}: {m['description']}" for m in meals)
    return head + ("\n" + body if body else "")

@T.register("nutrition_advice",
    "Gibt kontextuellen Ernährungs-Rat basierend auf aktuellem Tagesstand (Kalorien, Protein, "
    "Mahlzeiten) + heutige Health-Daten (Schritte, HRV, Schlaf). Ideal für Fragen wie "
    "'Soll ich Pizza essen?', 'Wie viel Kalorien habe ich noch?', 'Reicht mein Protein?'.",
    {"question": {"type": "string", "description": "Die Frage zu Ernährung oder Essen"}},
    ["question"], "nutrition")
async def _nutrition_advice(question: str):
    from domains import nutrition
    from core import db as _db

    totals = nutrition.day_totals()
    meals = nutrition.meals_for()

    goal_cal = _db.get_setting("calorie_goal", 2200)
    goal_prot = _db.get_setting("protein_goal", 150)

    remaining_cal = goal_cal - (totals.get("calories") or 0)
    remaining_prot = goal_prot - (totals.get("protein_g") or 0)

    health_row = _db.query_one(
        "SELECT steps, hrv, sleep_total_h, resting_hr FROM health_data ORDER BY date DESC LIMIT 1"
    )

    lines = [
        f"Frage: {question}",
        "\nHeutiger Ernährungs-Stand:",
        f"  Kalorien: {int(totals.get('calories') or 0)} / {goal_cal} kcal (noch {int(remaining_cal)} übrig)",
        f"  Protein: {int(totals.get('protein_g') or 0)} / {goal_prot}g (noch {int(remaining_prot)}g übrig)",
    ]
    if meals:
        lines.append(f"  Mahlzeiten heute: {', '.join(m['description'] for m in meals[:4])}")
    if health_row:
        lines.append("\nHeutige Health-Daten:")
        if health_row.get("steps"):
            lines.append(f"  Schritte: {health_row['steps']}")
        if health_row.get("hrv"):
            lines.append(f"  HRV: {health_row['hrv']} ms")
        if health_row.get("sleep_total_h"):
            lines.append(f"  Schlaf: {health_row['sleep_total_h']:.1f}h")

    return "\n".join(lines)

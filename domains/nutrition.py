"""
Ernährungs-Domäne: Mahlzeiten + Makros.
"""
from datetime import date

from core import db


# ── Reine Rechenlogik für adaptive Bulk-Ziele (kein DB — testbar) ─────────────

def bmr_mifflin(weight_kg: float, height_cm: float, age: int, male: bool = True) -> float:
    """Grundumsatz nach Mifflin-St-Jeor (männlich: +5, weiblich: -161)."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if male else -161)


def linear_slope_per_week(xs_days: list[int], weights: list[float]) -> float | None:
    """Least-Squares-Steigung als kg/Woche aus Tages-Offsets + Gewichten.

    None wenn < 2 Punkte oder keine x-Varianz (alle am selben Tag) — dann ist
    keine Trendaussage möglich.
    """
    n = len(xs_days)
    if n < 2:
        return None
    mx = sum(xs_days) / n
    my = sum(weights) / n
    denom = sum((xi - mx) ** 2 for xi in xs_days)
    if denom <= 0:
        return None
    slope_per_day = sum((xs_days[i] - mx) * (weights[i] - my) for i in range(n)) / denom
    return round(slope_per_day * 7, 3)


def bulk_adjustment(actual_kg_per_week: float, target_kg_per_week: float,
                    current_adj: int, step: int, max_adj: int) -> tuple[str, int]:
    """Entscheidet die kumulierte kcal-Anpassung aus Ist- vs. Ziel-Zunahme.

    Gibt (status, neue_anpassung) zurück: too_slow → mehr essen (+step),
    too_fast → weniger (−step), on_track → unverändert. Gedeckelt auf ±max_adj.
    """
    diff = actual_kg_per_week - target_kg_per_week
    if diff < -0.05:
        return "too_slow", min(current_adj + step, max_adj)
    if diff > 0.1:
        return "too_fast", max(current_adj - step, -max_adj)
    return "on_track", current_adj


def macros_for(kcal_goal: int, weight_kg: float) -> dict:
    """Makro-Verteilung: 2.2 g Protein/kg, 1.0 g Fett/kg, Rest Kohlenhydrate (min 50 g)."""
    protein_g = round(weight_kg * 2.2)
    fat_g = round(weight_kg * 1.0)
    carbs_g = round((kcal_goal - protein_g * 4 - fat_g * 9) / 4)
    return {"protein": protein_g, "fat": fat_g, "carbs": max(carbs_g, 50)}


def log_meal(description: str, meal_type: str = "snack",
             calories: int | None = None, protein_g: float | None = None,
             carbs_g: float | None = None, fat_g: float | None = None,
             on_date: date | None = None) -> int:
    d = on_date or date.today()
    return db.insert_returning(
        """INSERT INTO meals (date, meal_type, description, calories, protein_g, carbs_g, fat_g)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (d, meal_type, description, calories, protein_g, carbs_g, fat_g),
    )


def create_pending_meal(description: str, on_date: date | None = None) -> int:
    d = on_date or date.today()
    return db.insert_returning(
        "INSERT INTO meals (date, meal_type, description, status) "
        "VALUES (%s,'snack',%s,'analyzing') RETURNING id",
        (d, description or "Wird analysiert…"))


def complete_meal(meal_id: int, name: str, calories, protein, carbs, fat) -> None:
    db.execute(
        "UPDATE meals SET description=%s, calories=%s, protein_g=%s, carbs_g=%s, fat_g=%s, "
        "status='done' WHERE id=%s",
        (name, calories, protein, carbs, fat, meal_id))


def fail_meal(meal_id: int) -> None:
    db.execute("UPDATE meals SET status='failed' WHERE id=%s", (meal_id,))


def update_meal(meal_id: int, name: str | None, calories, protein, carbs, fat) -> None:
    db.execute(
        "UPDATE meals SET description=COALESCE(%s,description), calories=%s, protein_g=%s, "
        "carbs_g=%s, fat_g=%s WHERE id=%s",
        (name, calories, protein, carbs, fat, meal_id))


def meals_for(d: date | None = None) -> list[dict]:
    d = d or date.today()
    return db.query("SELECT * FROM meals WHERE date=%s ORDER BY created_at", (d,))


def history(days: int = 14) -> list[dict]:
    """Tages-Makros der letzten N Tage (für Chart)."""
    rows = db.query(
        """SELECT date, COALESCE(SUM(calories),0) kcal, COALESCE(SUM(protein_g),0) protein,
                  COALESCE(SUM(carbs_g),0) carbs, COALESCE(SUM(fat_g),0) fat
           FROM meals WHERE date >= CURRENT_DATE - %s GROUP BY date ORDER BY date""",
        (days,),
    )
    from datetime import timedelta
    by = {str(r["date"]): r for r in rows}
    out = []
    for i in range(days - 1, -1, -1):
        d = str(date.today() - timedelta(days=i))
        r = by.get(d)
        out.append({"date": d,
                    "kcal": int(r["kcal"]) if r else 0,
                    "protein": float(r["protein"]) if r else 0,
                    "carbs": float(r["carbs"]) if r else 0,
                    "fat": float(r["fat"]) if r else 0})
    return out


def day_totals(d: date | None = None) -> dict:
    d = d or date.today()
    row = db.query_one(
        """SELECT COALESCE(SUM(calories),0) kcal, COALESCE(SUM(protein_g),0) protein,
                  COALESCE(SUM(carbs_g),0) carbs, COALESCE(SUM(fat_g),0) fat,
                  COUNT(*) n
           FROM meals WHERE date=%s""",
        (d,),
    )
    return row or {"kcal": 0, "protein": 0, "carbs": 0, "fat": 0, "n": 0}

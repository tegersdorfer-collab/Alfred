"""
Ernährungs-Domäne: Mahlzeiten + Makros.
"""
from datetime import date

from core import db


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

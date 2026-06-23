"""
domains/body.py

Körpermessungs-Tracking: Umfänge, Körperfett, Gewicht (ergänzend zu health_data).
Speichert pro Tag einen Eintrag mit den gemessenen Werten.
"""
from datetime import date, datetime
from typing import Optional

from core import db


def log_measurement(
    date_: date | None = None,
    weight_kg: float | None = None,
    waist_cm: float | None = None,
    chest_cm: float | None = None,
    hips_cm: float | None = None,
    bicep_cm: float | None = None,
    thigh_cm: float | None = None,
    neck_cm: float | None = None,
    body_fat: float | None = None,
    notes: str | None = None,
) -> int:
    d = date_ or date.today()
    fields = {k: v for k, v in {
        "weight_kg": weight_kg, "waist_cm": waist_cm, "chest_cm": chest_cm,
        "hips_cm": hips_cm, "bicep_cm": bicep_cm, "thigh_cm": thigh_cm,
        "neck_cm": neck_cm, "body_fat": body_fat, "notes": notes,
    }.items() if v is not None}

    if not fields:
        raise ValueError("Mindestens ein Messwert erforderlich")

    cols = list(fields.keys())
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols)
    sql = (
        f"INSERT INTO body_measurements (date, {', '.join(cols)}) "
        f"VALUES (%s, {', '.join(['%s']*len(cols))}) "
        f"ON CONFLICT (date) DO UPDATE SET {updates} "
        f"RETURNING id"
    )
    return db.insert_returning(sql, tuple([d] + [fields[c] for c in cols]))


def get_recent(days: int = 30) -> list[dict]:
    rows = db.query(
        "SELECT * FROM body_measurements ORDER BY date DESC LIMIT %s", (days,)
    )
    return [dict(r) for r in rows]


def get_on_date(d: date) -> dict | None:
    row = db.query_one("SELECT * FROM body_measurements WHERE date=%s", (d,))
    return dict(row) if row else None


def progress_summary(weeks: int = 8) -> str:
    rows = db.query(
        "SELECT * FROM body_measurements ORDER BY date DESC LIMIT %s", (weeks * 7,)
    )
    if len(rows) < 2:
        return "Zu wenig Daten für Fortschrittsvergleich."
    first, last = rows[-1], rows[0]
    lines = [f"Messzeitraum: {first['date']} → {last['date']}"]
    for col, label in [
        ("weight_kg", "Gewicht"), ("waist_cm", "Taille"), ("chest_cm", "Brust"),
        ("hips_cm", "Hüfte"), ("bicep_cm", "Bizeps"), ("body_fat", "Körperfett%"),
    ]:
        v1, v2 = first.get(col), last.get(col)
        if v1 is not None and v2 is not None:
            delta = v2 - v1
            sign = "+" if delta > 0 else ""
            unit = "%" if col == "body_fat" else ("kg" if "kg" in col else "cm")
            lines.append(f"  {label}: {v1}{unit} → {v2}{unit} ({sign}{delta:.1f}{unit})")
    return "\n".join(lines)

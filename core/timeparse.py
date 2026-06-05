"""Robuste Zeit-/Datum-Parser für Tool-Argumente vom LLM."""
from datetime import date, datetime, timedelta


def parse_datetime(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().lower()
    now = datetime.now()
    # Relative Schlüsselwörter
    if s in ("jetzt", "now"):
        return now
    if s.startswith("in "):
        try:
            parts = s.split()
            n = int(parts[1])
            unit = parts[2]
            if unit.startswith("min"):
                return now + timedelta(minutes=n)
            if unit.startswith("std") or unit.startswith("hour") or unit.startswith("stund"):
                return now + timedelta(hours=n)
            if unit.startswith("tag") or unit.startswith("day"):
                return now + timedelta(days=n)
        except Exception:
            pass
    base = None
    if s.startswith("morgen"):
        base = now + timedelta(days=1)
        s = s.replace("morgen", "").strip()
    elif s.startswith("heute"):
        base = now
        s = s.replace("heute", "").strip()
    if base is not None:
        # optionale Uhrzeit
        for fmt in ("%H:%M", "%H"):
            try:
                t = datetime.strptime(s, fmt)
                return base.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            except ValueError:
                continue
        return base.replace(hour=9, minute=0, second=0, microsecond=0)
    # Absolute Formate
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M", "%d.%m.%Y", "%Y-%m-%d", "%H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%H:%M":
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except ValueError:
            continue
    return None


def parse_date(s: str) -> date | None:
    dt = parse_datetime(s)
    return dt.date() if dt else None

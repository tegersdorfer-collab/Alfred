"""Robuste Zeit-/Datum-Parser für Tool-Argumente vom LLM."""
from datetime import date, datetime, timedelta

_WEEKDAYS_DE = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonntag": 6,
    "mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
}


def _next_weekday(now: datetime, wd: int) -> datetime:
    """Gibt nächsten Wochentag >= morgen zurück."""
    days_ahead = wd - now.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


def parse_datetime(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().lower()
    # datetime-local format (from HTML input)
    if "t" in s and len(s) >= 16:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                pass
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
    remainder = s

    # übermorgen / übermorgen
    if s.startswith("übermorgen") or s.startswith("uebermorgen"):
        base = now + timedelta(days=2)
        remainder = s.replace("übermorgen", "").replace("uebermorgen", "").strip()
    elif s.startswith("morgen"):
        base = now + timedelta(days=1)
        remainder = s.replace("morgen", "").strip()
    elif s.startswith("heute"):
        base = now
        remainder = s.replace("heute", "").strip()
    else:
        # Wochentag (z.B. "montag 10:00", "nächsten freitag 14:00")
        clean = s.replace("nächsten", "").replace("naechsten", "").replace("kommenden", "").strip()
        for wd_name, wd_num in _WEEKDAYS_DE.items():
            if clean.startswith(wd_name):
                base = _next_weekday(now, wd_num)
                remainder = clean[len(wd_name):].strip()
                break

    if base is not None:
        remainder = remainder.lstrip("um ,:")
        for fmt in ("%H:%M", "%H.%M", "%H uhr", "%H"):
            try:
                t = datetime.strptime(remainder, fmt)
                return base.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            except ValueError:
                continue
        # Keine Uhrzeit → 9:00 als Default
        return base.replace(hour=9, minute=0, second=0, microsecond=0)

    # Absolute Formate
    for fmt in (
        "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%d.%m. %H:%M",
        "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
        "%d.%m.%Y", "%d.%m.%y", "%d.%m.", "%Y-%m-%d",
        "%H:%M",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            # Fehlende Jahresangabe → aktuelles Jahr
            if dt.year == 1900:
                dt = dt.replace(year=now.year)
                if dt.date() < now.date():
                    dt = dt.replace(year=now.year + 1)
            # Nur Uhrzeit → heute
            if fmt == "%H:%M":
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except ValueError:
            continue
    return None


def parse_date(s: str) -> date | None:
    dt = parse_datetime(s)
    return dt.date() if dt else None

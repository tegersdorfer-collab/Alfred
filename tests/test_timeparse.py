"""Unit-Tests für core/timeparse.py (LLM-Zeitangaben-Parser, kein DB nötig)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime, timedelta

from core.timeparse import parse_datetime, parse_date, _next_weekday


class TestRelative:
    def test_morgen_mit_uhrzeit(self):
        dt = parse_datetime("morgen 14:00")
        expected = date.today() + timedelta(days=1)
        assert dt.date() == expected
        assert (dt.hour, dt.minute) == (14, 0)

    def test_morgen_ohne_uhrzeit_default_9(self):
        dt = parse_datetime("morgen")
        assert dt.date() == date.today() + timedelta(days=1)
        assert (dt.hour, dt.minute) == (9, 0)

    def test_uebermorgen(self):
        dt = parse_datetime("übermorgen 8:30")
        assert dt.date() == date.today() + timedelta(days=2)
        assert (dt.hour, dt.minute) == (8, 30)

    def test_heute_mit_um(self):
        dt = parse_datetime("heute um 18:30")
        assert dt.date() == date.today()
        assert (dt.hour, dt.minute) == (18, 30)

    def test_in_minuten(self):
        dt = parse_datetime("in 30 minuten")
        expected = datetime.now() + timedelta(minutes=30)
        assert abs((dt.replace(tzinfo=None) - expected).total_seconds()) < 5

    def test_in_stunden(self):
        dt = parse_datetime("in 2 stunden")
        expected = datetime.now() + timedelta(hours=2)
        assert abs((dt.replace(tzinfo=None) - expected).total_seconds()) < 5

    def test_in_tagen(self):
        dt = parse_datetime("in 3 tagen")
        expected = datetime.now() + timedelta(days=3)
        assert abs((dt.replace(tzinfo=None) - expected).total_seconds()) < 5

    def test_jetzt(self):
        dt = parse_datetime("jetzt")
        assert abs((dt.replace(tzinfo=None) - datetime.now()).total_seconds()) < 5


class TestWeekday:
    def test_naechster_wochentag_liegt_in_zukunft(self):
        dt = parse_datetime("montag 10:00")
        assert dt.weekday() == 0
        assert dt.date() > date.today()
        assert (dt.hour, dt.minute) == (10, 0)

    def test_naechsten_prefix(self):
        dt = parse_datetime("nächsten freitag 14:00")
        assert dt.weekday() == 4
        assert dt.date() > date.today()

    def test_next_weekday_never_today(self):
        now = datetime.now()
        # Der eigene Wochentag muss auf nächste Woche fallen, nicht heute
        result = _next_weekday(now, now.weekday())
        assert result.date() == (now + timedelta(days=7)).date()


class TestAbsolute:
    def test_volles_datum_mit_zeit(self):
        dt = parse_datetime("24.12.2026 18:00")
        assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 12, 24, 18)

    def test_datum_ohne_jahr_ergaenzt_jahr(self):
        dt = parse_datetime("24.12.")
        assert (dt.month, dt.day) == (12, 24)
        # Nie in der Vergangenheit
        assert dt.date() >= date.today()

    def test_nur_uhrzeit_ist_heute(self):
        dt = parse_datetime("15:45")
        assert dt.date() == date.today()
        assert (dt.hour, dt.minute) == (15, 45)

    def test_iso_format(self):
        dt = parse_datetime("2026-08-01 09:00")
        assert (dt.year, dt.month, dt.day) == (2026, 8, 1)

    def test_html_datetime_local(self):
        dt = parse_datetime("2026-07-10T09:30")
        assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 7, 10, 9, 30)


class TestRobustness:
    def test_leerer_string(self):
        assert parse_datetime("") is None

    def test_unsinn(self):
        assert parse_datetime("blafasel xyz") is None

    def test_ergebnis_ist_tz_aware(self):
        dt = parse_datetime("morgen 12:00")
        assert dt.tzinfo is not None

    def test_parse_date(self):
        d = parse_date("morgen")
        assert d == date.today() + timedelta(days=1)

    def test_parse_date_none(self):
        assert parse_date("quatsch") is None

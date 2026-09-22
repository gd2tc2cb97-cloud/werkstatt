"""Kleine Helfer: Datum/Zeit-Berechnung, erlaubter Erfassungszeitraum."""

from datetime import date, datetime, timedelta

# Mitarbeiter dürfen Einträge für die letzten 2 Tage nachtragen
# und für morgen im Voraus anlegen.
DAYS_BACK = 2
DAYS_FORWARD = 1


def allowed_entry_range(today=None):
    today = today or date.today()
    return today - timedelta(days=DAYS_BACK), today + timedelta(days=DAYS_FORWARD)


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_in_allowed_range(value):
    try:
        d = parse_date(value)
    except ValueError:
        return False
    start, end = allowed_entry_range()
    return start <= d <= end


def compute_minutes(start_time, end_time, break_minutes):
    fmt = "%H:%M"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    diff = (end - start).total_seconds() / 60
    if diff < 0:
        diff += 24 * 60  # Schichtende nach Mitternacht
    worked = diff - int(break_minutes or 0)
    return max(0, round(worked))


def format_hours(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h}:{m:02d}"

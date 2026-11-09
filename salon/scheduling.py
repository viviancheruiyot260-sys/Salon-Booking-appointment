"""Opening hours, phone checks and display helpers.

This module does not touch the database. Booking views call it, then
store whatever they decide in Django models.
"""

import re
from datetime import datetime, time, timedelta

from django.utils import timezone

# Monday is 0. Closing time is when the studio closes, not the last start.
WEEKDAY_HOURS = {
    0: (time(8, 0), time(19, 0)),
    1: (time(8, 0), time(19, 0)),
    2: (time(8, 0), time(19, 0)),
    3: (time(8, 0), time(19, 0)),
    4: (time(8, 0), time(19, 0)),
    5: (time(8, 0), time(18, 0)),
    6: (time(10, 0), time(16, 0)),
}

WEEKDAY_LABELS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

SLOT_MINUTES = 30
MAX_ADVANCE_DAYS = 90
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def local_now():
    return timezone.localtime()


def local_today():
    return local_now().date()


def normalize_kenyan_mobile(value):
    """Return +2547… or +2541…, or None when the number is not a Kenyan mobile."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in {"1", "7"}:
        digits = "254" + digits
    if re.fullmatch(r"254[17]\d{8}", digits):
        return "+" + digits
    return None


def normalize_whatsapp_number(value):
    """Digits only, without a plus, for wa.me links."""
    normalized = normalize_kenyan_mobile(value)
    if not normalized:
        return ""
    return normalized[1:]


def format_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if re.fullmatch(r"254[17]\d{8}", digits):
        local = digits[3:]
        return f"+254 {local[:3]} {local[3:6]} {local[6:]}"
    return value or ""


def format_ksh(amount):
    return f"KSh {int(amount):,}"


def format_time_label(value):
    hour = value.hour
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{value.minute:02d} {suffix}"


def format_date_label(value):
    return value.strftime("%A, %d %B %Y")


def duration_label(minutes):
    minutes = int(minutes)
    if minutes < 60:
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit}"
    hours, remainder = divmod(minutes, 60)
    if remainder == 0:
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit}"
    hour_unit = "hour" if hours == 1 else "hours"
    return f"{hours} {hour_unit} {remainder} minutes"


def hours_label(day):
    opening, closing = WEEKDAY_HOURS[day.weekday()]
    return (
        f"{WEEKDAY_LABELS[day.weekday()]} {format_time_label(opening)} "
        f"to {format_time_label(closing)}"
    )


def _iter_slots(start, stop):
    cursor = datetime.combine(datetime.min.date(), start)
    end = datetime.combine(datetime.min.date(), stop)
    while cursor < end:
        yield cursor.time()
        cursor += timedelta(minutes=SLOT_MINUTES)


def all_slot_times():
    earliest = min(opening for opening, _closing in WEEKDAY_HOURS.values())
    latest = max(closing for _opening, closing in WEEKDAY_HOURS.values())
    return list(_iter_slots(earliest, latest))


def slots_for_day(day):
    opening, closing = WEEKDAY_HOURS[day.weekday()]
    return list(_iter_slots(opening, closing))


def hours_payload():
    payload = {}
    for weekday, (opening, closing) in WEEKDAY_HOURS.items():
        payload[str(weekday)] = {
            "label": (
                f"{WEEKDAY_LABELS[weekday]} hours are "
                f"{format_time_label(opening)} to {format_time_label(closing)}."
            ),
            "open": opening.strftime("%H:%M"),
            "close": closing.strftime("%H:%M"),
        }
    return payload


def aware_on(day, clock):
    combined = datetime.combine(day, clock)
    return timezone.make_aware(combined, timezone.get_current_timezone())


def intervals_overlap(start_a, duration_a, start_b, duration_b):
    end_a = start_a + timedelta(minutes=duration_a)
    end_b = start_b + timedelta(minutes=duration_b)
    return start_a < end_b and start_b < end_a


def slot_problem(day, start, duration_minutes):
    """Return (field_name, message) when a requested slot should be rejected."""
    today = local_today()
    if day < today:
        return (
            "appointment_date",
            "Choose today or a future date. Past dates are not accepted.",
        )
    if day > today + timedelta(days=MAX_ADVANCE_DAYS):
        return (
            "appointment_date",
            f"Choose a date within the next {MAX_ADVANCE_DAYS} days.",
        )
    if start not in all_slot_times() or start.second or start.microsecond:
        return (
            "appointment_time",
            "Choose a start time from the list. Requests begin on the hour or half hour.",
        )

    opening, closing = WEEKDAY_HOURS[day.weekday()]
    if start < opening or start >= closing:
        return (
            "appointment_time",
            f"That time is outside our opening hours ({hours_label(day)}).",
        )

    starts_at = aware_on(day, start)
    finishes_at = starts_at + timedelta(minutes=int(duration_minutes))
    closes_at = aware_on(day, closing)
    if finishes_at > closes_at:
        return (
            "appointment_time",
            (
                f"This service takes {duration_label(duration_minutes)} and would finish "
                f"after closing ({format_time_label(closing)}). Choose an earlier time."
            ),
        )

    now = local_now()
    if day == today and starts_at <= now:
        return (
            "appointment_time",
            "That time has already passed today. Choose a later time or another date.",
        )
    return None


def clean_text(value, limit):
    text = str(value or "")
    text = re.sub(r"[\u0000-\u001f\u007f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def clean_notes(value, limit=500):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]

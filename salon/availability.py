from datetime import timedelta

from salon.models import OCCUPYING_STATUSES, Booking
from salon.scheduling import (
    aware_on,
    format_time_label,
    intervals_overlap,
    local_today,
    slot_problem,
    slots_for_day,
)

SUGGESTION_LIMIT = 4
SAME_DAY_SUGGESTIONS = 3
SUGGESTION_DAYS_AHEAD = 7


def _occupied(service, days, exclude_pk=None):
    """Pending or confirmed bookings in the same category, grouped by day.

    Each category (hair, spa, nails) takes one appointment at a time, so a
    manicure does not block a haircut at the same hour.
    """
    rows = (
        Booking.objects.filter(
            appointment_date__in=list(days),
            status__in=OCCUPYING_STATUSES,
            service__category=service.category,
        )
        .select_related("service")
    )
    if exclude_pk:
        rows = rows.exclude(pk=exclude_pk)
    by_day = {}
    for row in rows:
        start = aware_on(row.appointment_date, row.appointment_time)
        by_day.setdefault(row.appointment_date, []).append((start, row.service.duration_minutes))
    return by_day


def _free(day, start, duration, taken):
    begins = aware_on(day, start)
    return not any(
        intervals_overlap(begins, duration, other_start, other_duration)
        for other_start, other_duration in taken.get(day, [])
    )


def slot_is_free(service, day, start, exclude_pk=None):
    taken = _occupied(service, [day], exclude_pk=exclude_pk)
    return _free(day, start, service.duration_minutes, taken)


def overlapping_requests(booking):
    """Other pending or confirmed bookings in the same category that overlap this one."""
    if not booking.appointment_date or not booking.appointment_time:
        return []
    start = aware_on(booking.appointment_date, booking.appointment_time)
    duration = booking.service.duration_minutes
    same_day = (
        Booking.objects.filter(
            appointment_date=booking.appointment_date,
            status__in=OCCUPYING_STATUSES,
            service__category=booking.service.category,
        )
        .exclude(pk=booking.pk)
        .select_related("service")
    )
    return [
        other
        for other in same_day
        if intervals_overlap(
            start,
            duration,
            aware_on(other.appointment_date, other.appointment_time),
            other.service.duration_minutes,
        )
    ]


def _label(day, start):
    if day == local_today():
        prefix = "Today"
    elif day == local_today() + timedelta(days=1):
        prefix = "Tomorrow"
    else:
        prefix = f"{day:%a} {day.day} {day:%b}"
    return f"{prefix}, {format_time_label(start)}"


def suggest_times(service, day, start, limit=SUGGESTION_LIMIT):
    """Open start times near the one that was taken.

    Up to three on the same day, closest first, then the earliest open
    times on the following days.
    """
    duration = service.duration_minutes
    days = [day + timedelta(days=offset) for offset in range(SUGGESTION_DAYS_AHEAD + 1)]
    taken = _occupied(service, days)
    requested = start.hour * 60 + start.minute

    def open_slots(on_day):
        return [
            slot
            for slot in slots_for_day(on_day)
            if slot_problem(on_day, slot, duration) is None
            and _free(on_day, slot, duration, taken)
        ]

    same_day = sorted(
        (slot for slot in open_slots(day) if slot != start),
        key=lambda slot: (abs(slot.hour * 60 + slot.minute - requested), slot),
    )[:SAME_DAY_SUGGESTIONS]
    picks = [(day, slot) for slot in sorted(same_day)]
    for later in days[1:]:
        if len(picks) >= limit:
            break
        for slot in open_slots(later):
            picks.append((later, slot))
            if len(picks) >= limit:
                break

    return [
        {
            "value": f"{pick_day.isoformat()}T{pick_start:%H:%M}",
            "label": _label(pick_day, pick_start),
        }
        for pick_day, pick_start in picks[:limit]
    ]


def recent_duplicate(phone, service, day, start, window_minutes):
    if window_minutes <= 0:
        return None
    from django.utils import timezone

    cutoff = timezone.now() - timedelta(minutes=window_minutes)
    return (
        Booking.objects.filter(
            customer_phone=phone,
            service=service,
            appointment_date=day,
            appointment_time=start,
            status__in=OCCUPYING_STATUSES,
            created_at__gte=cutoff,
        )
        .order_by("-created_at")
        .first()
    )

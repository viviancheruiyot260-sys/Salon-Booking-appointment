import logging
import secrets
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from salon.availability import recent_duplicate, slot_is_free, suggest_times
from salon.forms import BookingForm, annotate_field_errors, idempotency_key
from salon.models import (
    Booking,
    BookingStatus,
    Service,
    ServiceCategory,
    generate_booking_reference,
)
from salon.notifications import (
    build_whatsapp_link,
    email_customer_confirmation,
    notify_owner_by_email,
)
from salon.scheduling import format_date_label, format_time_label, hours_payload

logger = logging.getLogger("salon")

SESSION_TOKEN = "booking_form_token"
SESSION_REFERENCE = "booking_reference"
SESSION_NOTICE = "booking_notice"
SESSION_CUSTOMER_EMAIL = "booking_customer_email"


def home(request):
    selected = request.GET.get("category", "").strip().lower()
    if selected not in ServiceCategory.values:
        selected = ""
    services = Service.objects.active().catalogue_order()
    if selected:
        services = services.filter(category=selected)
    categories = []
    for value, label in ServiceCategory.choices:
        categories.append(
            {
                "value": value,
                "label": label,
                "count": Service.objects.active().filter(category=value).count(),
                "selected": value == selected,
            }
        )
    return render(
        request,
        "salon/home.html",
        {
            "services": services,
            "categories": categories,
            "selected_category": selected,
            "service_total": Service.objects.active().count(),
        },
    )


def service_detail(request, slug):
    service = get_object_or_404(Service.objects.active(), slug=slug)
    related = (
        Service.objects.active()
        .filter(category=service.category)
        .exclude(pk=service.pk)
        .catalogue_order()[:3]
    )
    return render(
        request,
        "salon/service_detail.html",
        {"service": service, "related": related},
    )


def _service_payload():
    rows = []
    for service in Service.objects.active().catalogue_order():
        rows.append(
            {
                "id": service.pk,
                "name": service.name,
                "price": service.price_display,
                "duration": service.duration_display,
                "category": service.get_category_display(),
            }
        )
    return rows


def _hours_payload():
    return hours_payload()


def _issue_token(request):
    token = secrets.token_urlsafe(16)
    request.session[SESSION_TOKEN] = token
    return token


def _remember(request, booking, notice, customer_email=""):
    request.session[SESSION_REFERENCE] = booking.reference
    request.session[SESSION_NOTICE] = notice
    if notice != "duplicate":
        request.session[SESSION_CUSTOMER_EMAIL] = customer_email


def _selected_service(form):
    raw = form.data.get("service") if form.is_bound else form.initial.get("service")
    if not raw:
        return None
    return Service.objects.active().filter(pk=raw).first()


def _render_booking(request, form, token, suggestions=None, slot_taken=False):
    annotate_field_errors(form)
    return render(
        request,
        "salon/booking.html",
        {
            "form": form,
            "form_token": token,
            "selected_service": _selected_service(form),
            "service_data": _service_payload(),
            "hours_data": _hours_payload(),
            "slot_taken": slot_taken,
            "suggestions": suggestions or [],
        },
    )


def _with_picked_slot(post):
    """Apply a suggested slot (YYYY-MM-DDTHH:MM) chosen from the taken-time list."""
    picked = (post.get("pick_slot") or "").strip()
    if not picked:
        return post
    try:
        chosen = datetime.strptime(picked, "%Y-%m-%dT%H:%M")
    except ValueError:
        return post
    data = post.copy()
    data["appointment_date"] = chosen.date().isoformat()
    data["appointment_time"] = chosen.strftime("%H:%M")
    return data


@never_cache
@require_http_methods(["GET", "POST"])
def book_appointment(request):
    if request.method == "GET":
        initial = {}
        slug = request.GET.get("service", "").strip()
        if slug:
            service = Service.objects.active().filter(slug=slug).first()
            if service:
                initial["service"] = service.pk
        token = _issue_token(request)
        form = BookingForm(initial=initial)
        return _render_booking(request, form, token)

    posted_token = request.POST.get("form_token", "")
    expected_token = request.session.get(SESSION_TOKEN, "")
    form = BookingForm(_with_picked_slot(request.POST))
    token_matches = bool(posted_token) and posted_token == expected_token

    if not token_matches:
        if form.is_valid():
            cleaned = form.cleaned_data
            key = idempotency_key(
                posted_token,
                cleaned["customer_phone"],
                cleaned["service"].pk,
                cleaned["appointment_date"],
                cleaned["appointment_time"],
            )
            existing = Booking.objects.filter(idempotency_key=key).first()
            if existing:
                _remember(request, existing, "duplicate")
                return redirect("salon:booking_success")
        form.add_error(
            None,
            "This form expired or was already used. Refresh the page and submit it once.",
        )
        return _render_booking(request, form, expected_token or _issue_token(request))

    if not form.is_valid():
        return _render_booking(request, form, expected_token)

    cleaned = form.cleaned_data
    service = Service.objects.active().filter(pk=cleaned["service"].pk).first()
    if service is None:
        form.add_error("service", "That service is not available for booking.")
        return _render_booking(request, form, expected_token)

    key = idempotency_key(
        posted_token,
        cleaned["customer_phone"],
        service.pk,
        cleaned["appointment_date"],
        cleaned["appointment_time"],
    )
    existing = Booking.objects.filter(idempotency_key=key).first()
    if existing is None:
        existing = recent_duplicate(
            cleaned["customer_phone"],
            service,
            cleaned["appointment_date"],
            cleaned["appointment_time"],
            settings.BOOKING_DUPLICATE_WINDOW_MINUTES,
        )
    if existing:
        _remember(request, existing, "duplicate")
        _issue_token(request)
        return redirect("salon:booking_success")

    booking = form.save(commit=False)
    booking.service = service
    booking.quoted_price_ksh = service.price_ksh
    booking.status = BookingStatus.CONFIRMED
    booking.idempotency_key = key
    slot_taken = False
    try:
        with transaction.atomic():
            # Serialises bookings per category on PostgreSQL; SQLite already locks on write.
            list(Service.objects.select_for_update().filter(category=service.category).values_list("pk", flat=True))
            raced = recent_duplicate(
                booking.customer_phone,
                service,
                booking.appointment_date,
                booking.appointment_time,
                settings.BOOKING_DUPLICATE_WINDOW_MINUTES,
            )
            if raced:
                existing = raced
            elif not slot_is_free(service, booking.appointment_date, booking.appointment_time):
                existing = None
                slot_taken = True
            else:
                booking.reference = generate_booking_reference()
                booking.save()
                existing = None
    except IntegrityError:
        existing = Booking.objects.filter(idempotency_key=key).first()
        if existing is None:
            raise

    if existing is not None:
        _remember(request, existing, "duplicate")
        _issue_token(request)
        return redirect("salon:booking_success")

    if slot_taken:
        day = cleaned["appointment_date"]
        start = cleaned["appointment_time"]
        form.add_error(
            "appointment_time",
            f"{format_time_label(start)} on {format_date_label(day)} is already booked. "
            "Pick one of the open times below or choose another time.",
        )
        return _render_booking(
            request,
            form,
            expected_token,
            suggestions=suggest_times(service, day, start),
            slot_taken=True,
        )

    logger.info("Booking %s confirmed.", booking.reference)
    email_status = notify_owner_by_email(booking)
    customer_email_status = email_customer_confirmation(booking)
    _remember(request, booking, email_status, customer_email_status)
    _issue_token(request)
    return redirect("salon:booking_success")


@never_cache
@require_http_methods(["GET"])
def booking_success(request):
    reference = request.session.get(SESSION_REFERENCE, "")
    booking = None
    if reference:
        booking = Booking.objects.filter(reference=reference).select_related("service").first()
    whatsapp_url = ""
    whatsapp_message = ""
    whatsapp_shortened = False
    if booking:
        whatsapp_url, whatsapp_message, whatsapp_shortened = build_whatsapp_link(booking)
    return render(
        request,
        "salon/booking_success.html",
        {
            "booking": booking,
            "notice": request.session.get(SESSION_NOTICE, ""),
            "customer_email_status": request.session.get(SESSION_CUSTOMER_EMAIL, ""),
            "whatsapp_url": whatsapp_url,
            "whatsapp_message": whatsapp_message,
            "whatsapp_shortened": whatsapp_shortened,
        },
    )


def csrf_failure(request, reason=""):
    return render(request, "salon/csrf_failure.html", status=403)

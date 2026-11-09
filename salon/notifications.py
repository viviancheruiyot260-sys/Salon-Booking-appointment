"""Owner notifications.

A saved booking stays saved when email fails. WhatsApp is only a link
the customer can open; this module never sends a WhatsApp message.
"""

import logging
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string

from salon.scheduling import format_phone, normalize_whatsapp_number

logger = logging.getLogger("salon")

WHATSAPP_URL_LIMIT = 1900


def owner_whatsapp_digits():
    return normalize_whatsapp_number(getattr(settings, "OWNER_WHATSAPP_NUMBER", ""))


def whatsapp_is_placeholder():
    return owner_whatsapp_digits() == "254700000000"


def _message(booking, notes, shortened):
    lines = [
        "Glow & Grace appointment booked online",
        f"Reference: {booking.reference}",
        f"Status: {booking.get_status_display()}",
        f"Name: {booking.customer_name}",
        f"Phone: {booking.phone_display}",
        f"Service: {booking.service.name}",
        f"Date: {booking.date_display}",
        f"Time: {booking.time_display}",
        f"Price: {booking.price_display}",
    ]
    if notes:
        lines.extend(["", "Notes:", notes])
    if shortened:
        lines.extend(["", "(Notes were shortened so this link stays usable. The full note is saved with the booking.)"])
    return "\n".join(lines)


def build_whatsapp_link(booking):
    """Return url, message and whether notes were shortened for length."""
    number = owner_whatsapp_digits()
    if not number:
        return "", "", False
    notes = booking.notes or ""
    message = _message(booking, notes, shortened=False)
    url = f"https://wa.me/{number}?text={quote(message)}"
    if len(url) <= WHATSAPP_URL_LIMIT:
        return url, message, False
    shortened_notes = notes
    while True:
        shortened_notes = shortened_notes[: max(0, len(shortened_notes) - 40)].rstrip()
        visible = f"{shortened_notes}…" if shortened_notes else ""
        message = _message(booking, visible, shortened=True)
        url = f"https://wa.me/{number}?text={quote(message)}"
        if len(url) <= WHATSAPP_URL_LIMIT or not shortened_notes:
            return url, message, True


def general_whatsapp_url():
    number = owner_whatsapp_digits()
    if not number:
        return ""
    text = "Hello Glow & Grace, I would like to ask about your services."
    return f"https://wa.me/{number}?text={quote(text)}"


def _backend_is_local():
    backend = settings.EMAIL_BACKEND
    return any(name in backend for name in ("console", "locmem", "dummy", "filebased"))


def email_customer_confirmation(booking):
    """Email the booking details to the customer. Returns sent, console, failed or skipped. Never raises."""
    recipient = (booking.customer_email or "").strip()
    if not recipient:
        return "skipped"

    number = owner_whatsapp_digits()
    has_real_number = bool(number) and not whatsapp_is_placeholder()
    reply_to = [
        address
        for address in (getattr(settings, "OWNER_EMAIL", ""), getattr(settings, "PUBLIC_CONTACT_EMAIL", ""))
        if address
    ][:1]
    context = {
        "booking": booking,
        "salon": settings.SALON,
        "can_reply": bool(reply_to),
        "studio_phone": format_phone(number) if has_real_number else "",
        "studio_whatsapp": f"https://wa.me/{number}" if has_real_number else "",
    }
    message = EmailMultiAlternatives(
        subject=f"Your Glow & Grace appointment is confirmed ({booking.reference})",
        body=render_to_string("salon/emails/booking_confirmation.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        reply_to=reply_to,
    )
    message.attach_alternative(
        render_to_string("salon/emails/booking_confirmation.html", context),
        "text/html",
    )
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.error(
            "Customer confirmation email failed for booking %s (%s).",
            booking.reference,
            type(exc).__name__,
        )
        return "failed"

    if _backend_is_local():
        logger.info("Booking %s customer email written with the %s backend.", booking.reference, settings.EMAIL_BACKEND)
        return "console"
    logger.info("Booking %s customer email handed to the mail server.", booking.reference)
    return "sent"


def notify_owner_by_email(booking):
    """Return sent, skipped, console or failed. Never raises."""
    owner = (getattr(settings, "OWNER_EMAIL", "") or "").strip()
    if not owner:
        logger.info("Booking %s saved. Owner email is not configured.", booking.reference)
        return "skipped"

    backend = settings.EMAIL_BACKEND
    body = "\n".join(
        [
            "A new appointment was booked online. The time was free, so it was confirmed automatically.",
            "If the studio cannot honour it, change its status to Cancelled in the admin and contact the customer.",
            "",
            f"Reference: {booking.reference}",
            f"Name: {booking.customer_name}",
            f"Phone: {booking.phone_display}",
            f"Email: {booking.customer_email or 'Not provided'}",
            f"Service: {booking.service.name}",
            f"Date: {booking.date_display}",
            f"Time: {booking.time_display}",
            f"Price: {booking.price_display}",
            f"Status: {booking.get_status_display()}",
            "",
            "Notes:",
            booking.notes or "None",
        ]
    )
    try:
        send_mail(
            subject=f"New appointment {booking.reference}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[owner],
            fail_silently=False,
        )
    except Exception as exc:
        logger.error(
            "Email notification failed for booking %s (%s).",
            booking.reference,
            type(exc).__name__,
        )
        return "failed"

    if _backend_is_local():
        logger.info("Booking %s email written with the %s backend.", booking.reference, backend)
        return "console"
    logger.info("Booking %s email handed to the configured mail server.", booking.reference)
    return "sent"

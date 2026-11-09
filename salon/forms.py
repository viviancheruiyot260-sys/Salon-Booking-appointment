import hashlib
import re
from datetime import datetime, timedelta

from django import forms

from salon.models import Booking, Service
from salon.scheduling import (
    all_slot_times,
    clean_notes,
    clean_text,
    format_time_label,
    local_today,
    normalize_kenyan_mobile,
    slot_problem,
)

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,119}$")


class BookingForm(forms.ModelForm):
    appointment_time = forms.TypedChoiceField(
        label="Preferred appointment time",
        choices=[],
        coerce=lambda value: datetime.strptime(value, "%H:%M").time(),
        empty_value=None,
    )

    class Meta:
        model = Booking
        fields = [
            "customer_name",
            "customer_phone",
            "customer_email",
            "service",
            "appointment_date",
            "appointment_time",
            "notes",
        ]
        widgets = {
            "customer_name": forms.TextInput(
                attrs={"autocomplete": "name", "maxlength": "120"}
            ),
            "customer_phone": forms.TextInput(
                attrs={
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "placeholder": "0712 345 678",
                    "maxlength": "20",
                }
            ),
            "customer_email": forms.EmailInput(
                attrs={"autocomplete": "email", "placeholder": "you@example.com"}
            ),
            "appointment_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4, "maxlength": "500"}),
        }
        labels = {
            "customer_name": "Full name",
            "customer_phone": "Kenyan phone number",
            "customer_email": "Email for your booking confirmation",
            "service": "Service",
            "appointment_date": "Appointment date",
            "notes": "Notes",
        }
        help_texts = {
            "customer_phone": "Use a Safaricom, Airtel or Telkom mobile number, such as 0712 345 678.",
            "customer_email": "Optional. We will email your booking details here as soon as you book.",
            "appointment_date": "Today or a later day, up to 90 days ahead.",
            "notes": "Optional. Hair length, allergies or anything the studio should know. 500 characters maximum.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        services = Service.objects.active().catalogue_order()
        self.fields["service"].queryset = services
        self.fields["service"].empty_label = "Select a service"
        self.fields["service"].label_from_instance = (
            lambda service: f"{service.name} — {service.price_display} — {service.duration_display}"
        )
        self.fields["customer_email"].required = False
        self.fields["notes"].required = False
        today = local_today()
        date_widget = self.fields["appointment_date"].widget
        date_widget.attrs["min"] = today.isoformat()
        date_widget.attrs["max"] = (today + timedelta(days=90)).isoformat()
        self.fields["appointment_time"].choices = [("", "Select a time")] + [
            (slot.strftime("%H:%M"), format_time_label(slot)) for slot in all_slot_times()
        ]
        self.fields["appointment_time"].help_text = (
            "Opening hours: Monday to Friday 8:00 AM–7:00 PM, Saturday 8:00 AM–6:00 PM, "
            "Sunday 10:00 AM–4:00 PM. If the time is free, it is booked for you straight away."
        )
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " form-control").strip()
        self.fields["service"].widget.attrs["class"] = "form-select"
        self.fields["appointment_time"].widget.attrs["class"] = "form-select"

    def clean_customer_name(self):
        name = clean_text(self.cleaned_data.get("customer_name"), 120)
        if not NAME_PATTERN.fullmatch(name):
            raise forms.ValidationError(
                "Enter your full name using letters, spaces, apostrophes or hyphens."
            )
        return name

    def clean_customer_phone(self):
        phone = normalize_kenyan_mobile(self.cleaned_data.get("customer_phone"))
        if not phone:
            raise forms.ValidationError(
                "Enter a valid Kenyan mobile number, such as 0712 345 678 or +254 712 345 678."
            )
        return phone

    def clean_notes(self):
        raw = self.cleaned_data.get("notes") or ""
        if len(str(raw).replace("\r\n", "\n")) > 500:
            raise forms.ValidationError("Keep notes to 500 characters or fewer.")
        return clean_notes(raw, 500)

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get("appointment_date")
        start = cleaned.get("appointment_time")
        service = cleaned.get("service")
        if not day or not start or not service:
            return cleaned
        if not service.is_active:
            self.add_error("service", "That service is not available for booking.")
            return cleaned
        problem = slot_problem(day, start, service.duration_minutes)
        if problem:
            self.add_error(problem[0], problem[1])
        return cleaned


def idempotency_key(token, phone, service_id, day, start):
    raw = f"{token}|{phone}|{service_id}|{day.isoformat()}|{start.strftime('%H:%M')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def annotate_field_errors(form):
    for name in form.errors:
        if name == "__all__" or name not in form.fields:
            continue
        widget = form.fields[name].widget
        widget.attrs["aria-invalid"] = "true"
        parts = []
        if form.fields[name].help_text:
            parts.append(f"id_{name}-help")
        parts.append(f"id_{name}-error")
        widget.attrs["aria-describedby"] = " ".join(parts)

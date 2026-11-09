import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case, IntegerField, When

from salon.scheduling import (
    REFERENCE_ALPHABET,
    clean_text,
    duration_label,
    format_date_label,
    format_ksh,
    format_phone,
    format_time_label,
    local_today,
    normalize_kenyan_mobile,
)


class ServiceCategory(models.TextChoices):
    HAIR = "hair", "Hair"
    SPA = "spa", "Spa & Wellness"
    NAILS = "nails", "Nails"


class ServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def catalogue_order(self):
        return self.alias(
            category_order=Case(
                When(category=ServiceCategory.HAIR, then=0),
                When(category=ServiceCategory.SPA, then=1),
                When(category=ServiceCategory.NAILS, then=2),
                default=3,
                output_field=IntegerField(),
            )
        ).order_by("category_order", "name")


class Service(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    category = models.CharField(max_length=20, choices=ServiceCategory.choices)
    description = models.TextField()
    price_ksh = models.PositiveIntegerField(
        "price (KSh)",
        validators=[MinValueValidator(1)],
        help_text="Whole Kenyan shillings. Sample prices are fictional.",
    )
    duration_minutes = models.PositiveIntegerField(
        "duration (minutes)",
        validators=[MinValueValidator(1)],
    )
    image = models.ImageField(
        upload_to="services/",
        blank=True,
        help_text="Optional. Cards use a colour panel when this is empty.",
    )
    is_active = models.BooleanField(
        "active",
        default=True,
        help_text="Inactive services stay hidden and cannot be requested.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ServiceQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price_ksh__gte=1),
                name="service_price_at_least_one",
            ),
            models.CheckConstraint(
                check=models.Q(duration_minutes__gte=1),
                name="service_duration_at_least_one",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def price_display(self):
        return format_ksh(self.price_ksh)

    @property
    def duration_display(self):
        return duration_label(self.duration_minutes)

    @property
    def card_image_url(self):
        """Uploaded photo, or the bundled sample picture for this slug."""
        if self.image:
            return self.image.url
        relative = f"images/photos/{self.slug}.jpg"
        if (settings.BASE_DIR / "static" / relative).is_file():
            from django.templatetags.static import static

            return static(relative)
        return ""


class BookingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


OCCUPYING_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED)


class Booking(models.Model):
    reference = models.CharField(max_length=20, unique=True)
    customer_name = models.CharField("full name", max_length=120)
    customer_phone = models.CharField("phone number", max_length=16)
    customer_email = models.EmailField("email", blank=True)
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    quoted_price_ksh = models.PositiveIntegerField(
        "quoted price (KSh)",
        validators=[MinValueValidator(1)],
        help_text="Copied from the service when the request is saved. Later price edits do not change it.",
    )
    appointment_date = models.DateField()
    appointment_time = models.TimeField("preferred time")
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
    )
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["appointment_date", "appointment_time"]),
            models.Index(fields=["status", "appointment_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quoted_price_ksh__gte=1),
                name="booking_quoted_price_at_least_one",
            ),
        ]

    def __str__(self):
        return f"{self.reference} — {self.customer_name}"

    def clean(self):
        super().clean()
        if self.customer_phone:
            normalized = normalize_kenyan_mobile(self.customer_phone)
            if not normalized:
                raise ValidationError(
                    {"customer_phone": "Enter a valid Kenyan mobile number, such as 0712 345 678."}
                )
            self.customer_phone = normalized
        if self.customer_name:
            self.customer_name = clean_text(self.customer_name, 120)

    @property
    def price_display(self):
        return format_ksh(self.quoted_price_ksh)

    @property
    def phone_display(self):
        return format_phone(self.customer_phone)

    @property
    def date_display(self):
        return format_date_label(self.appointment_date)

    @property
    def time_display(self):
        return format_time_label(self.appointment_time)

    @property
    def when_display(self):
        return f"{self.date_display} at {self.time_display}"


def generate_booking_reference():
    day = local_today()
    for _attempt in range(8):
        suffix = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(4))
        reference = f"GG-{day:%Y%m%d}-{suffix}"
        if not Booking.objects.filter(reference=reference).exists():
            return reference
    raise RuntimeError("Could not generate a unique booking reference.")

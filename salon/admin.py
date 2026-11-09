from django.contrib import admin, messages
from django import forms

from salon.models import Booking, BookingStatus, Service, generate_booking_reference


class BookingAdminForm(forms.ModelForm):
    class Meta:
        model = Booking
        exclude = ("idempotency_key",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            return
        if "reference" in self.fields:
            self.fields["reference"].required = False
            self.fields["reference"].help_text = "Leave blank to generate a reference."
        if "quoted_price_ksh" in self.fields:
            self.fields["quoted_price_ksh"].required = False
            self.fields["quoted_price_ksh"].help_text = (
                "Leave blank to copy the service price at the time you save."
            )

    def clean_reference(self):
        reference = (self.cleaned_data.get("reference") or "").strip()
        if reference:
            return reference
        if self.instance.pk:
            return self.instance.reference
        return generate_booking_reference()

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("quoted_price_ksh") and cleaned.get("service"):
            cleaned["quoted_price_ksh"] = cleaned["service"].price_ksh
        return cleaned


@admin.action(description="Mark selected requests as confirmed")
def mark_confirmed(modeladmin, request, queryset):
    updated = queryset.update(status=BookingStatus.CONFIRMED)
    modeladmin.message_user(request, f"{updated} request(s) marked confirmed.", messages.SUCCESS)


@admin.action(description="Mark selected requests as cancelled")
def mark_cancelled(modeladmin, request, queryset):
    updated = queryset.update(status=BookingStatus.CANCELLED)
    modeladmin.message_user(request, f"{updated} request(s) marked cancelled.", messages.SUCCESS)


@admin.action(description="Mark selected requests as completed")
def mark_completed(modeladmin, request, queryset):
    updated = queryset.update(status=BookingStatus.COMPLETED)
    modeladmin.message_user(request, f"{updated} request(s) marked completed.", messages.SUCCESS)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "price_ksh",
        "duration_minutes",
        "is_active",
        "updated_at",
    )
    list_editable = ("price_ksh", "duration_minutes", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    ordering = ("category", "name")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    form = BookingAdminForm
    list_display = (
        "reference",
        "customer_name",
        "customer_phone",
        "service",
        "appointment_date",
        "appointment_time",
        "quoted_price_ksh",
        "status",
        "created_at",
    )
    list_display_links = ("reference",)
    list_editable = ("status",)
    list_filter = ("status", "appointment_date", "service__category", "service")
    search_fields = ("reference", "customer_name", "customer_phone", "customer_email")
    date_hierarchy = "appointment_date"
    autocomplete_fields = ("service",)
    readonly_fields = ("created_at", "updated_at")
    actions = (mark_confirmed, mark_cancelled, mark_completed)
    fieldsets = (
        ("Request", {"fields": ("reference", "status", "service", "quoted_price_ksh")}),
        ("Customer", {"fields": ("customer_name", "customer_phone", "customer_email", "notes")}),
        ("Appointment", {"fields": ("appointment_date", "appointment_time")}),
        ("Record", {"fields": ("created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = ["created_at", "updated_at"]
        if obj:
            fields = ["reference", "quoted_price_ksh", *fields]
        return fields

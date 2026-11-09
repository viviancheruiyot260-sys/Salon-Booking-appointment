from django.apps import AppConfig
from django.contrib import admin


class SalonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "salon"
    verbose_name = "Glow & Grace"

    def ready(self):
        admin.site.site_header = "Glow & Grace"
        admin.site.site_title = "Glow & Grace admin"
        admin.site.index_title = "Appointment requests and services"

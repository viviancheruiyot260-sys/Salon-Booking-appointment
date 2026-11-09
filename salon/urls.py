from django.urls import path

from salon import views

app_name = "salon"

urlpatterns = [
    path("", views.home, name="home"),
    path("services/<slug:slug>/", views.service_detail, name="service_detail"),
    path("book/", views.book_appointment, name="booking"),
    path("book/success/", views.booking_success, name="booking_success"),
]

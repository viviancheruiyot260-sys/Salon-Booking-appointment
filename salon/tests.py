from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from salon import scheduling
from salon.availability import suggest_times
from salon.management.commands.load_sample_services import SAMPLE_SERVICES
from salon.models import Booking, Service, ServiceCategory, generate_booking_reference
from salon.notifications import build_whatsapp_link
from salon.scheduling import normalize_kenyan_mobile


NAIROBI = ZoneInfo("Africa/Nairobi")


def next_weekday(weekday):
    today = scheduling.local_today()
    delta = (weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


class SchedulingTests(SimpleTestCase):
    def test_kenyan_mobile_formats(self):
        expected = "+254712345678"
        for raw in ("0712345678", "0712 345 678", "+254712345678", "254712345678", "712345678", "07-1234-5678"):
            self.assertEqual(normalize_kenyan_mobile(raw), expected, raw)
        self.assertEqual(normalize_kenyan_mobile("0112345678"), "+254112345678")

    def test_rejects_numbers_that_are_not_kenyan_mobiles(self):
        for raw in ("", "12345", "0800123456", "254800000000", "+1 202 555 0143", "07123"):
            self.assertIsNone(normalize_kenyan_mobile(raw), raw)

    def test_past_date_is_rejected_before_a_booking_exists(self):
        yesterday = scheduling.local_today() - timedelta(days=1)
        field, message = scheduling.slot_problem(yesterday, time(10, 0), 30)
        self.assertEqual(field, "appointment_date")
        self.assertIn("Past dates", message)


class CatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("load_sample_services")

    def test_homepage_explains_the_studio_and_the_request(self):
        response = self.client.get(reverse("salon:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Beauty & Wellness, All in One Place.", html=True)
        self.assertContains(
            response,
            "Explore our salon, spa and nail services, view prices upfront, and book your appointment online in just a few simple steps.",
        )
        self.assertContains(response, "Book an Appointment")
        self.assertContains(response, "Explore Our Services")
        self.assertContains(response, "KSh 750")
        self.assertContains(response, "3 hours")

    def test_category_filter_limits_the_catalogue(self):
        response = self.client.get(reverse("salon:home"), {"category": "nails"})
        self.assertContains(response, "Basic Manicure")
        self.assertContains(response, "Gel Manicure")
        self.assertContains(response, "KSh 700")
        self.assertNotContains(response, "Knotless Braids")
        self.assertNotContains(response, "Relaxation Massage")
        book = reverse("salon:booking") + "?service=basic-manicure"
        self.assertContains(response, book)

    def test_unknown_category_shows_the_full_catalogue(self):
        response = self.client.get(reverse("salon:home"), {"category": "shoes"})
        self.assertContains(response, "Knotless Braids")
        self.assertContains(response, "Basic Manicure")

    def test_service_detail_and_missing_service(self):
        response = self.client.get(reverse("salon:service_detail", args=["wash-and-blow-dry"]))
        self.assertContains(response, "Wash and Blow-Dry")
        self.assertContains(response, reverse("salon:booking") + "?service=wash-and-blow-dry")
        missing = self.client.get(reverse("salon:service_detail", args=["not-a-service"]))
        self.assertEqual(missing.status_code, 404)

    def test_inactive_service_is_hidden(self):
        Service.objects.filter(slug="coco-twists").update(is_active=False)
        response = self.client.get(reverse("salon:home"), {"category": "hair"})
        self.assertNotContains(response, "Coco Twists")
        detail = self.client.get(reverse("salon:service_detail", args=["coco-twists"]))
        self.assertEqual(detail.status_code, 404)

    def test_sample_command_is_safe_to_repeat_and_keeps_price_edits(self):
        from django.core.management import call_command

        Service.objects.filter(slug="wash-and-blow-dry").update(price_ksh=111)
        call_command("load_sample_services")
        self.assertEqual(Service.objects.count(), len(SAMPLE_SERVICES))
        self.assertEqual(Service.objects.get(slug="wash-and-blow-dry").price_ksh, 111)
        self.assertEqual(Service.objects.get(slug="nail-art-add-on").price_ksh, 300)
        self.assertEqual(Service.objects.get(slug="nail-art-add-on").duration_minutes, 15)


@override_settings(OWNER_WHATSAPP_NUMBER="254700000000", OWNER_EMAIL="")
class BookingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manicure = Service.objects.create(
            name="Basic Manicure",
            slug="basic-manicure",
            category=ServiceCategory.NAILS,
            description="Shaping, cuticle care and regular polish.",
            price_ksh=700,
            duration_minutes=30,
        )
        cls.braids = Service.objects.create(
            name="Knotless Braids",
            slug="knotless-braids",
            category=ServiceCategory.HAIR,
            description="Medium knotless braids.",
            price_ksh=3500,
            duration_minutes=180,
        )
        cls.inactive = Service.objects.create(
            name="Retired Facial",
            slug="retired-facial",
            category=ServiceCategory.SPA,
            description="No longer offered.",
            price_ksh=1500,
            duration_minutes=45,
            is_active=False,
        )

    def future_day(self):
        return scheduling.local_today() + timedelta(days=7)

    def start_form(self, **query):
        response = self.client.get(reverse("salon:booking"), query)
        self.assertEqual(response.status_code, 200)
        return self.client.session["booking_form_token"]

    def payload(self, token, **overrides):
        data = {
            "form_token": token,
            "customer_name": "Jane Wanjiku",
            "customer_phone": "0712 345 678",
            "customer_email": "jane@example.com",
            "service": str(self.manicure.pk),
            "appointment_date": self.future_day().isoformat(),
            "appointment_time": "10:00",
            "notes": "Please keep the colour soft.",
            "quoted_price_ksh": "1",
            "price": "5",
        }
        data.update(overrides)
        return data

    def post_booking(self, **overrides):
        token = self.start_form()
        return self.client.post(reverse("salon:booking"), self.payload(token, **overrides))

    def test_preselects_the_requested_service(self):
        response = self.client.get(reverse("salon:booking"), {"service": "basic-manicure"})
        self.assertContains(response, "Basic Manicure")
        self.assertContains(response, "KSh 700")
        self.assertContains(response, "selected")

    def test_validation_errors_are_shown_and_values_are_kept(self):
        token = self.start_form()
        response = self.client.post(
            reverse("salon:booking"),
            self.payload(token, customer_name="1234", customer_phone="0800 111 222", customer_email="not-an-email"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(response, "Enter your full name using letters")
        self.assertContains(response, "Enter a valid Kenyan mobile number")
        self.assertContains(response, "Enter a valid email address.")
        self.assertContains(response, "0800 111 222")
        self.assertContains(response, "Please correct the highlighted fields")

    def test_past_date_is_rejected(self):
        yesterday = scheduling.local_today() - timedelta(days=1)
        response = self.post_booking(appointment_date=yesterday.isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(response, "Past dates are not accepted.")

    def test_past_time_today_is_rejected(self):
        fixed = datetime(2026, 10, 28, 15, 0, tzinfo=NAIROBI)
        with patch("salon.scheduling.local_now", return_value=fixed):
            response = self.post_booking(
                appointment_date="2026-10-28",
                appointment_time="10:00",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(response, "already passed today")

    def test_sunday_time_outside_hours_and_overrunning_service(self):
        sunday = next_weekday(6)
        early = self.post_booking(appointment_date=sunday.isoformat(), appointment_time="08:00")
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(early, "outside our opening hours")
        late = self.post_booking(
            service=str(self.braids.pk),
            appointment_date=sunday.isoformat(),
            appointment_time="15:00",
        )
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(late, "would finish after closing")

    def test_successful_booking_saves_server_price_and_reference(self):
        response = self.post_booking()
        self.assertRedirects(response, reverse("salon:booking_success"))
        booking = Booking.objects.get()
        self.assertEqual(booking.status, "confirmed")
        self.assertEqual(booking.customer_phone, "+254712345678")
        self.assertEqual(booking.quoted_price_ksh, 700)
        self.assertRegex(booking.reference, r"^GG-\d{8}-[A-HJ-NP-Z2-9]{4}$")
        self.manicure.price_ksh = 9999
        self.manicure.save(update_fields=["price_ksh"])
        booking.refresh_from_db()
        self.assertEqual(booking.quoted_price_ksh, 700)
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "Your appointment is confirmed.")
        self.assertContains(page, booking.when_display)
        self.assertContains(page, booking.reference)
        self.assertContains(page, "KSh 700")
        self.assertEqual(page.status_code, 200)

    def test_inactive_service_is_rejected(self):
        response = self.post_booking(service=str(self.inactive.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertContains(response, "valid choice")

    def test_header_injection_in_the_name_is_rejected(self):
        response = self.post_booking(customer_name="Jane\nBcc: bad@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)

    def test_notes_are_escaped_on_the_success_page(self):
        self.post_booking(notes="<script>alert(1)</script>")
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(page, "<script>alert(1)</script>")

    def test_whatsapp_link_uses_the_configured_number_and_booking_details(self):
        self.post_booking()
        booking = Booking.objects.select_related("service").get()
        url, message, shortened = build_whatsapp_link(booking)
        self.assertFalse(shortened)
        self.assertTrue(url.startswith("https://wa.me/254700000000?text="))
        self.assertIn(booking.reference, message)
        self.assertIn("Jane Wanjiku", message)
        self.assertIn("Basic Manicure", message)
        self.assertIn("KSh 700", message)
        self.assertIn("+254 712 345 678", message)
        self.assertIn("Please keep the colour soft.", message)
        self.assertIn("Status: Confirmed", message)
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "Send booking details on WhatsApp")
        self.assertContains(page, url)

    def test_success_page_without_the_session_hides_customer_details(self):
        self.post_booking()
        booking = Booking.objects.get()
        stranger = Client()
        page = stranger.get(reverse("salon:booking_success"))
        self.assertContains(page, "No booking is open in this browser")
        self.assertNotContains(page, booking.customer_name)
        self.assertNotContains(page, "712 345 678")
        self.assertNotContains(page, "Your appointment is confirmed.")

    def test_duplicate_submission_does_not_create_a_second_row(self):
        token = self.start_form()
        data = self.payload(token)
        first = self.client.post(reverse("salon:booking"), data)
        second = self.client.post(reverse("salon:booking"), data)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "already saved")

    def test_a_fresh_form_for_the_same_slot_is_also_collapsed(self):
        self.post_booking()
        self.post_booking()
        self.assertEqual(Booking.objects.count(), 1)

    def test_taken_time_is_refused_with_open_times_and_no_other_customer_details(self):
        self.post_booking(customer_name="Amina Yusuf", customer_phone="0712000001")
        first = Booking.objects.get()
        response = self.post_booking(customer_name="Brian Otieno", customer_phone="0733000002", notes="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertContains(response, "That time is already booked")
        self.assertContains(response, "is already booked. Pick one of the open times below")
        self.assertContains(response, 'name="pick_slot"')
        suggestions = response.context["suggestions"]
        self.assertTrue(suggestions)
        taken_value = f"{self.future_day().isoformat()}T10:00"
        self.assertNotIn(taken_value, [slot["value"] for slot in suggestions])
        self.assertContains(response, "Brian Otieno")
        self.assertNotContains(response, "Amina Yusuf")
        self.assertNotContains(response, first.reference)
        self.assertNotContains(response, "0712000001")

    def test_picking_a_suggested_time_books_it_straight_away(self):
        self.post_booking(customer_name="Amina Yusuf", customer_phone="0712000001")
        token = self.start_form()
        data = self.payload(token, customer_name="Brian Otieno", customer_phone="0733000002")
        refused = self.client.post(reverse("salon:booking"), data)
        choice = refused.context["suggestions"][0]["value"]
        booked = self.client.post(reverse("salon:booking"), {**data, "pick_slot": choice})
        self.assertRedirects(booked, reverse("salon:booking_success"))
        second = Booking.objects.get(customer_name="Brian Otieno")
        self.assertEqual(second.status, "confirmed")
        self.assertEqual(f"{second.appointment_date.isoformat()}T{second.appointment_time:%H:%M}", choice)

    def test_suggestions_skip_booked_times_and_respect_closing(self):
        sunday = next_weekday(6)
        Booking.objects.create(
            reference="GG-20261101-SUN1",
            customer_name="Existing Guest",
            customer_phone="+254712345678",
            service=self.braids,
            quoted_price_ksh=3500,
            appointment_date=sunday,
            appointment_time=time(10, 0),
            status="confirmed",
        )
        suggestions = suggest_times(self.braids, sunday, time(10, 0))
        self.assertEqual(len(suggestions), 4)
        same_day = [slot["value"] for slot in suggestions if slot["value"].startswith(sunday.isoformat())]
        self.assertEqual(same_day, [f"{sunday.isoformat()}T13:00"])
        self.assertEqual(suggestions[0]["value"], f"{sunday.isoformat()}T13:00")

    def test_other_categories_and_cancelled_bookings_do_not_block_the_time(self):
        Booking.objects.create(
            reference="GG-20261101-HAIR",
            customer_name="Hair Guest",
            customer_phone="+254712000003",
            service=self.braids,
            quoted_price_ksh=3500,
            appointment_date=self.future_day(),
            appointment_time=time(9, 0),
            status="confirmed",
        )
        Booking.objects.create(
            reference="GG-20261101-GONE",
            customer_name="Cancelled Guest",
            customer_phone="+254712000004",
            service=self.manicure,
            quoted_price_ksh=700,
            appointment_date=self.future_day(),
            appointment_time=time(10, 0),
            status="cancelled",
        )
        response = self.post_booking()
        self.assertRedirects(response, reverse("salon:booking_success"))
        self.assertEqual(Booking.objects.filter(status="confirmed").count(), 2)

    def test_reference_retries_when_the_suffix_already_exists(self):
        day = scheduling.local_today()
        Booking.objects.create(
            reference=f"GG-{day:%Y%m%d}-AAAA",
            customer_name="Existing Guest",
            customer_phone="+254712345678",
            service=self.manicure,
            quoted_price_ksh=700,
            appointment_date=self.future_day(),
            appointment_time=time(11, 0),
            status="pending",
        )
        sequence = iter(["A", "A", "A", "A", "B", "B", "B", "B"])
        with patch("salon.models.secrets.choice", side_effect=lambda alphabet: next(sequence)):
            reference = generate_booking_reference()
        self.assertEqual(reference, f"GG-{day:%Y%m%d}-BBBB")

    @override_settings(
        OWNER_EMAIL="owner@example.com",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="bookings@example.com",
    )
    def test_owner_email_includes_the_reference_and_not_a_second_copy(self):
        self.post_booking()
        self.post_booking()
        self.assertEqual(Booking.objects.count(), 1)
        owner_mail = [message for message in mail.outbox if message.to == ["owner@example.com"]]
        self.assertEqual(len(owner_mail), 1)
        booking = Booking.objects.get()
        self.assertIn(booking.reference, owner_mail[0].subject)
        self.assertNotIn(booking.customer_name, owner_mail[0].subject)
        self.assertIn("Jane Wanjiku", owner_mail[0].body)
        self.assertNotIn("EMAIL_HOST_PASSWORD", owner_mail[0].body)

    @override_settings(
        EMAIL_BACKEND="salon.test_backends.InboxEmailBackend",
        DEFAULT_FROM_EMAIL="bookings@example.com",
        OWNER_EMAIL="owner@example.com",
    )
    def test_customer_receives_the_booking_details_by_email(self):
        self.post_booking(customer_name="Jane O'Neil", notes="Soft pink, please.")
        booking = Booking.objects.get()
        customer_mail = [message for message in mail.outbox if message.to == ["jane@example.com"]]
        self.assertEqual(len(customer_mail), 1)
        message = customer_mail[0]
        self.assertIn(booking.reference, message.subject)
        self.assertNotIn("O'Neil", message.subject)
        self.assertEqual(message.reply_to, ["owner@example.com"])
        for expected in (
            "Hello Jane O'Neil,",
            "Basic Manicure",
            booking.date_display,
            booking.time_display,
            "KSh 700",
            "Kilimani, Nairobi",
            "Soft pink, please.",
        ):
            self.assertIn(expected, message.body)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn(booking.reference, html)
        self.assertIn("Jane O&#x27;Neil", html)
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "We have emailed your booking details to")
        self.assertContains(page, "jane@example.com")

    @override_settings(EMAIL_BACKEND="salon.test_backends.InboxEmailBackend", OWNER_EMAIL="")
    def test_no_customer_email_when_none_was_given_and_none_on_repeat(self):
        self.post_booking(customer_email="")
        self.assertEqual(len(mail.outbox), 0)
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "Add an email address next time")

        mail.outbox.clear()
        token = self.start_form()
        data = self.payload(token, appointment_time="12:00")
        self.client.post(reverse("salon:booking"), data)
        self.client.post(reverse("salon:booking"), data)
        self.assertEqual(len(mail.outbox), 1)

    def test_local_mail_backend_is_not_described_as_delivered(self):
        self.post_booking()
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "was not sent to a real inbox")
        self.assertNotContains(page, "We have emailed your booking details")

    @override_settings(
        OWNER_EMAIL="owner@example.com",
        EMAIL_BACKEND="salon.test_backends.BrokenEmailBackend",
        DEFAULT_FROM_EMAIL="bookings@example.com",
    )
    def test_email_failure_does_not_drop_the_saved_booking(self):
        response = self.post_booking()
        self.assertRedirects(response, reverse("salon:booking_success"))
        self.assertEqual(Booking.objects.count(), 1)
        page = self.client.get(reverse("salon:booking_success"))
        self.assertContains(page, "could not be sent")
        self.assertContains(page, "We could not email your booking details")
        self.assertContains(page, "still booked")
        self.assertNotContains(page, "secret-user")
        self.assertNotContains(page, "smtp auth")

    def test_post_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("salon:booking"), {"customer_name": "Jane Wanjiku"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Booking.objects.count(), 0)


class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.service = Service.objects.create(
            name="Basic Pedicure",
            slug="basic-pedicure",
            category=ServiceCategory.NAILS,
            description="A soak and polish.",
            price_ksh=1000,
            duration_minutes=45,
        )
        cls.booking = Booking.objects.create(
            reference="GG-20261030-TEST",
            customer_name="Jane Wanjiku",
            customer_phone="+254712345678",
            customer_email="jane@example.com",
            service=cls.service,
            quoted_price_ksh=1000,
            appointment_date=timezone.localdate() + timedelta(days=3),
            appointment_time=time(10, 0),
            notes="Window seat if possible",
            status="pending",
        )
        cls.owner = User.objects.create_superuser("owner", "owner@example.com", "test-pass-12345")
        cls.guest = User.objects.create_user("guest", password="test-pass-12345")

    def test_anonymous_and_non_staff_cannot_open_booking_records(self):
        url = reverse("admin:salon_booking_changelist")
        anonymous = self.client.get(url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/admin/login/", anonymous["Location"])
        login_page = self.client.get(anonymous["Location"])
        self.assertNotContains(login_page, "Jane Wanjiku")
        self.assertNotContains(login_page, "GG-20261030-TEST")

        self.assertTrue(self.client.login(username="guest", password="test-pass-12345"))
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 302)
        self.assertIn("/admin/login/", denied["Location"])
        self.client.logout()

    def test_owner_can_review_and_confirm_a_request(self):
        self.assertTrue(self.client.login(username="owner", password="test-pass-12345"))
        listing = self.client.get(reverse("admin:salon_booking_changelist"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "GG-20261030-TEST")
        self.assertContains(listing, "Jane Wanjiku")
        self.assertContains(listing, "+254712345678")

        change = reverse("admin:salon_booking_change", args=[self.booking.pk])
        detail = self.client.get(change)
        self.assertEqual(detail.status_code, 200)
        posted = self.client.post(
            change,
            {
                "status": "confirmed",
                "service": str(self.service.pk),
                "customer_name": self.booking.customer_name,
                "customer_phone": self.booking.customer_phone,
                "customer_email": self.booking.customer_email,
                "appointment_date": self.booking.appointment_date.isoformat(),
                "appointment_time": "10:00:00",
                "notes": self.booking.notes,
            },
        )
        self.assertEqual(posted.status_code, 302, posted.content[:1500] if posted.status_code != 302 else "")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")
        self.assertEqual(self.booking.quoted_price_ksh, 1000)

    def test_owner_can_open_the_service_catalogue(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin:salon_service_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Basic Pedicure")
        self.assertContains(response, "1000")

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from salon.models import Service, ServiceCategory


SAMPLE_SERVICES = [
    {
        "name": "Wash and Blow-Dry",
        "slug": "wash-and-blow-dry",
        "category": ServiceCategory.HAIR,
        "description": "A cleanse, condition and blow-dry for a smooth everyday finish.",
        "price_ksh": 800,
        "duration_minutes": 45,
    },
    {
        "name": "Haircut and Styling",
        "slug": "haircut-and-styling",
        "category": ServiceCategory.HAIR,
        "description": "A cut and finish shaped to your hair, with a short consultation before the stylist starts.",
        "price_ksh": 1200,
        "duration_minutes": 60,
    },
    {
        "name": "Knotless Braids",
        "slug": "knotless-braids",
        "category": ServiceCategory.HAIR,
        "description": "Medium knotless braids. Length and parting are agreed with your stylist.",
        "price_ksh": 750,
        "duration_minutes": 180,
    },
    {
        "name": "Coco Twists",
        "slug": "coco-twists",
        "category": ServiceCategory.HAIR,
        "description": "Short, defined twists on natural hair, finished with a light hold. Twist size is agreed with the studio.",
        "price_ksh": 650,
        "duration_minutes": 90,
    },
    {
        "name": "Hair Treatment",
        "slug": "hair-treatment",
        "category": ServiceCategory.HAIR,
        "description": "A conditioning treatment for dry or dull hair, finished with a blow-dry.",
        "price_ksh": 850,
        "duration_minutes": 60,
    },
    {
        "name": "Relaxation Massage",
        "slug": "relaxation-massage",
        "category": ServiceCategory.SPA,
        "description": "A full-body massage aimed at easing tired muscles. Pressure is agreed at the start.",
        "price_ksh": 2500,
        "duration_minutes": 60,
    },
    {
        "name": "Express Facial",
        "slug": "express-facial",
        "category": ServiceCategory.SPA,
        "description": "A short cleanse, exfoliation and moisturiser when you want a fresher look without a long visit.",
        "price_ksh": 1200,
        "duration_minutes": 45,
    },
    {
        "name": "Deep Cleansing Facial",
        "slug": "deep-cleansing-facial",
        "category": ServiceCategory.SPA,
        "description": "A longer facial with a deeper cleanse, a face massage and a mask.",
        "price_ksh": 1500,
        "duration_minutes": 60,
    },
    {
        "name": "Body Scrub",
        "slug": "body-scrub",
        "category": ServiceCategory.SPA,
        "description": "A full-body exfoliation followed by a light moisturiser.",
        "price_ksh": 1000,
        "duration_minutes": 45,
    },
    {
        "name": "Basic Manicure",
        "slug": "basic-manicure",
        "category": ServiceCategory.NAILS,
        "description": "Shaping, cuticle care and regular polish on natural nails.",
        "price_ksh": 700,
        "duration_minutes": 30,
    },
    {
        "name": "Basic Pedicure",
        "slug": "basic-pedicure",
        "category": ServiceCategory.NAILS,
        "description": "A soak, shaping, cuticle care and regular polish.",
        "price_ksh": 1000,
        "duration_minutes": 45,
    },
    {
        "name": "Gel Manicure",
        "slug": "gel-manicure",
        "category": ServiceCategory.NAILS,
        "description": "A manicure finished with gel colour and a lamp cure.",
        "price_ksh": 1000,
        "duration_minutes": 60,
    },
    {
        "name": "Acrylic Nail Extensions",
        "slug": "acrylic-nail-extensions",
        "category": ServiceCategory.NAILS,
        "description": "A full set of acrylic extensions with shaping and colour.",
        "price_ksh": 2500,
        "duration_minutes": 90,
    },
    {
        "name": "Nail Art Add-on",
        "slug": "nail-art-add-on",
        "category": ServiceCategory.NAILS,
        "description": "Simple nail art requested as its own appointment. Ask the studio if you want it added to another nail service.",
        "price_ksh": 300,
        "duration_minutes": 15,
    },
]


class Command(BaseCommand):
    help = (
        "Create the fictional Glow & Grace sample services. "
        "Safe to run more than once: existing slugs are left unchanged."
    )

    def handle(self, *args, **options):
        created = 0
        for item in SAMPLE_SERVICES:
            service, was_created = Service.objects.get_or_create(
                slug=item["slug"],
                defaults=item,
            )
            if was_created:
                created += 1
            photo = settings.BASE_DIR / "static" / "images" / "photos" / f"{service.slug}.jpg"
            if photo.is_file() and not service.image:
                with photo.open("rb") as handle:
                    service.image.save(photo.name, File(handle), save=True)
        unchanged = len(SAMPLE_SERVICES) - created
        self.stdout.write(
            self.style.SUCCESS(
                f"Sample catalogue ready. {created} added, {unchanged} already present."
            )
        )

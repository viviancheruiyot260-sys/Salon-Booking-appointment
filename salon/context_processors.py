from django.conf import settings

from salon.notifications import general_whatsapp_url, owner_whatsapp_digits, whatsapp_is_placeholder
from salon.scheduling import format_phone


def site_context(request):
    digits = owner_whatsapp_digits()
    instagram = settings.SOCIAL_INSTAGRAM_URL
    if not (instagram.startswith("https://") or instagram.startswith("http://")):
        instagram = ""
    return {
        "salon": settings.SALON,
        "owner_phone_display": format_phone(digits) if digits else "",
        "owner_phone_tel": f"+{digits}" if digits else "",
        "general_whatsapp_url": general_whatsapp_url(),
        "whatsapp_is_placeholder": whatsapp_is_placeholder() if digits else False,
        "public_email": settings.PUBLIC_CONTACT_EMAIL,
        "instagram_url": instagram,
    }

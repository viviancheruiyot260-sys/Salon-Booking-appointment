"""Email backends used only by tests."""

from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.locmem import EmailBackend as MemoryBackend


class BrokenEmailBackend(BaseEmailBackend):
    """Records nothing and always fails."""

    def send_messages(self, email_messages):
        raise OSError("smtp auth failed for secret-user")


class InboxEmailBackend(MemoryBackend):
    """Stores mail in django.core.mail.outbox but is treated like a real mail server."""

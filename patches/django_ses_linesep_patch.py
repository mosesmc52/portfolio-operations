from __future__ import annotations


def apply_django_ses_linesep_patch() -> None:
    """
    django-ses calls Message.as_bytes(linesep="\\r\\n") which raises TypeError
    on some Python 3.12 message objects.

    We patch email.message.Message.as_bytes to accept an optional `linesep`
    kwarg and ignore it, delegating to the original implementation.
    """
    import email.message

    orig_as_bytes = email.message.Message.as_bytes

    # Prevent double-patching
    if getattr(email.message.Message.as_bytes, "_linesep_patched", False):
        return

    def as_bytes_with_linesep(self, *args, **kwargs):
        # Drop unsupported kwarg used by django-ses
        kwargs.pop("linesep", None)
        return orig_as_bytes(self, *args, **kwargs)

    as_bytes_with_linesep._linesep_patched = True  # type: ignore[attr-defined]
    email.message.Message.as_bytes = as_bytes_with_linesep  # type: ignore[assignment]

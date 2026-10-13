from rest_framework.exceptions import ValidationError


class IdempotencyConflict(ValidationError):
    """The idempotency key was already used for another request."""

    status_code = 409
    default_code = "idempotency_conflict"

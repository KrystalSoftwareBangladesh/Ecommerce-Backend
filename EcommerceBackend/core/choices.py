# EcommerceBackend/core/choices.py
from django.db import models


class ModerationStatus(models.IntegerChoices):
    PENDING = 1, 'Pending'
    APPROVED = 2, 'Approved'
    REJECTED = 3, 'Rejected'

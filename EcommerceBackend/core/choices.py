# EcommerceBackend/core/choices.py
from django.db import models


class ModerationStatus(models.IntegerChoices):
    PENDING = 1, 'Pending'
    APPROVED = 2, 'Approved'
    REJECTED = 3, 'Rejected'


class CartStatus(models.IntegerChoices):
    ACTIVE = 1, "Active"
    CHECKED_OUT = 2, "Checked Out"
    ABANDONED = 3, "Abandoned"

# customer_api/models/customer_address.py
from django.db import models

from EcommerceBackend.core.models import (
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
)
from .customer import CustomerProfile


class CustomerAddress(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    class AddressType(models.TextChoices):
        BILLING = "BILLING", "Billing"
        SHIPPING = "SHIPPING", "Shipping"

    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    address_type = models.CharField(
        max_length=20,
        choices=AddressType.choices,
        db_index=True,
    )
    first_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    last_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    company = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    address_1 = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )
    address_2 = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )
    city = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    state = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    postcode = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )
    country = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["address_type", "-created_at"]
        indexes = [
            models.Index(fields=["customer", "address_type"]),
            models.Index(fields=["customer", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "address_type"],
                condition=models.Q(is_active=True),
                name="unique_active_customer_address_type",
            ),
        ]
        verbose_name = "Customer Address"
        verbose_name_plural = "Customer Addresses"

    def __str__(self):
        return (
            f"{self.customer.user.full_name or 'No name'} - "
            f"{self.get_address_type_display()}"
        )

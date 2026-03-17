
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomerProfile(models.Model):
    CUSTOMER_TYPE_CHOICES = [
        ("POS", "POS"),
        ("FACEBOOK", "Facebook"),
        ("WEBSITE", "Website")
    ]
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=30, blank=True, null=True)
    facebook_profile_url = models.URLField(blank=True, null=True)
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default="POS",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["phone"]),
                   models.Index(fields=["created_at"])]
        ordering = ["-created_at"]
        verbose_name = 'Customer Profile'
        verbose_name_plural = 'Customer Profiles'

    def __str__(self):
        return f"{self.user.full_name or 'No name'} ({self.customer_type})"

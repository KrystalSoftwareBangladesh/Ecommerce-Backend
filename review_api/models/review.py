# review_api/models/review.py
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.core.validators import MinValueValidator, MaxValueValidator

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel, ModerationModel,
    ModerationStatus,
)


class Review(TimeStampedModel, UserStampedModel, SoftDeleteModel, ModerationModel):   # noqa
    product = models.ForeignKey(
        'product_api.Product',
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name="Product"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Rating (1-5)"
    )
    title = models.CharField(max_length=255, verbose_name="Review Title")
    body = models.TextField(verbose_name="Review Content")
    is_verified_purchase = models.BooleanField(
        default=False,
        verbose_name="Verified Purchase",
        help_text="True if the user actually bought this product."
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Product Review"
        verbose_name_plural = "Product Reviews"

        constraints = [
            UniqueConstraint(
                fields=['product', 'created_by'],
                # condition=Q(is_active=True),
                condition=~Q(status=ModerationStatus.REJECTED),
                name='unique_active_review_per_product_user'
            )
        ]

        indexes = [
            # Fast fetching of approved reviews for a product
            models.Index(fields=['product', 'status']),
            # Fast aggregation for average rating
            models.Index(fields=['rating']),
        ]

    def __str__(self):
        return f"Review by {self.created_by} for {self.product} ({self.rating}/5)"  # noqa

# review_api/services/review.py
from django.core.exceptions import ValidationError
from django.db import transaction

from EcommerceBackend.core.choices import ModerationStatus
from review_api.models import Review


def create_review(
    *,
    product,
    user,
    rating,
    title,
    body,
    is_verified_purchase=False,
):
    """
    Create a new product review.

    Business Rules
    --------------
    - One active review per user per product.
    - Newly created reviews are always Pending.
    """

    if product is None:
        raise ValidationError("Product is required.")

    # existing_review = Review.objects.filter(
    #     product=product,
    #     created_by=user,
    #     is_active=True,
    # ).exists()
    existing_review = Review.objects.filter(
        product=product,
        created_by=user,
    ).exclude(
        status=ModerationStatus.REJECTED,
    ).exists()

    if existing_review:
        raise ValidationError(
            "You have already reviewed this product."
        )

    with transaction.atomic():
        review = Review.objects.create(
            product=product,
            rating=rating,
            title=title,
            body=body,
            is_verified_purchase=is_verified_purchase,
            created_by=user,
            updated_by=user,
            status=ModerationStatus.PENDING,
        )

    return review


def update_review(
    *,
    review,
    user,
    **validated_data,
):
    """
    Update a review.

    Business Rules
    --------------
    - Only owner can update.
    - Any edit sends the review back to Pending.
    """

    if review.created_by_id != user.id:
        raise ValidationError(
            "You do not have permission to edit this review."
        )

    with transaction.atomic():
        for field, value in validated_data.items():
            setattr(review, field, value)

        review.updated_by = user

        review.reset_to_pending()

        review.save()

    return review


def delete_review(
    *,
    review,
    user,
):
    """
    Soft delete a review.
    """

    if review.created_by_id != user.id:
        raise ValidationError(
            "You do not have permission to delete this review."
        )

    review.updated_by = user
    review.save(update_fields=["updated_by", "updated_at"])

    review.soft_delete()

    return review


def approve_review(
    *,
    review,
    user,
):
    """
    Approve a review.
    """

    review.approve(user)

    return review


def reject_review(
    *,
    review,
):
    """
    Reject a review.
    """

    review.reject()

    return review

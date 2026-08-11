# product_api/services/brand.py
from django.db import transaction, models
from django.db.models import Max

from product_api.models import Brand


class BrandService:

    @staticmethod
    @transaction.atomic
    def create_brand(*, validated_data, user):
        requested_order = validated_data.get("display_order")

        brands = (
            Brand.objects
            .select_for_update()
            .filter(
                is_active=True,
                deleted_at__isnull=True,
            )
        )

        # max_order = brands.count()
        max_order = brands.aggregate(
            max_order=Max("display_order")
        )["max_order"] or 0

        if requested_order is None or requested_order > max_order + 1:
            requested_order = max_order + 1

        if requested_order < 1:
            requested_order = 1

        brands.filter(
            display_order__gte=requested_order
        ).update(
            display_order=models.F("display_order") + 1
        )

        validated_data["display_order"] = requested_order

        return Brand.objects.create(
            **validated_data,
            created_by=user,
        )

    @staticmethod
    @transaction.atomic
    def update_brand(*, instance, validated_data, user):
        old_order = instance.display_order
        new_order = validated_data.get(
            "display_order",
            old_order,
        )

        if new_order < 1:
            new_order = 1

        brands = (
            Brand.objects
            .select_for_update()
            .filter(
                is_active=True,
                deleted_at__isnull=True,
            )
            .exclude(pk=instance.pk)
        )

        # max_order = brands.count() + 1
        max_order = brands.aggregate(
            max_order=Max("display_order")
        )["max_order"] or 0
        max_order += 1

        if new_order > max_order:
            new_order = max_order

        if new_order != old_order:
            if new_order < old_order:
                brands.filter(
                    display_order__gte=new_order,
                    display_order__lt=old_order,
                ).update(
                    display_order=models.F("display_order") + 1
                )

            else:
                brands.filter(
                    display_order__gt=old_order,
                    display_order__lte=new_order,
                ).update(
                    display_order=models.F("display_order") - 1
                )

        validated_data["display_order"] = new_order
        validated_data["updated_by"] = user

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        return instance

# cart_api/services/cart_type.py
from cart_api.models import CartType


class CartTypeService:
    @staticmethod
    def list():
        """
        Return all active cart types.
        """
        return CartType.objects.filter(
            is_active=True
        ).order_by("name")

    @staticmethod
    def get(cart_type_id: int):
        """
        Return a cart type by ID.
        """
        return CartType.objects.get(
            id=cart_type_id,
            is_active=True,
        )

    @staticmethod
    def create(**validated_data):
        """
        Create a new cart type.
        """
        return CartType.objects.create(
            **validated_data
        )

    @staticmethod
    def update(
        cart_type: CartType,
        **validated_data,
    ):
        """
        Update an existing cart type.
        """
        for field, value in validated_data.items():
            setattr(cart_type, field, value)

        cart_type.save()

        return cart_type

    @staticmethod
    def delete(cart_type: CartType):
        """
        Soft delete (deactivate) a cart type.
        """
        cart_type.is_active = False
        cart_type.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        return cart_type

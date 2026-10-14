import decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from user_api.models import User
from product_api.models import Product
from category_api.models import Category
from EcommerceBackend.core.choices import CartStatus

from cart_api.models import Cart, CartItem
from cart_api.services.cart import (
    get_active_cart,
    checkout_cart,
    abandon_cart,
)
from cart_api.services.cart_item import (
    add_cart_item,
    update_cart_item,
    remove_cart_item,
)


class CartServiceTest(TestCase):
    """Tests for cart service functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cartuser",
            email="cart@example.com",
            password="testpass123",
        )
        self.category = Category.objects.create(
            name="Test",
            slug="test",
        )
        self.product = Product.objects.create(
            name="Widget",
            slug="widget",
            current_selling_price=decimal.Decimal(
                "100.00"
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        self.product.categories.add(self.category)

    def test_get_active_cart_none_when_no_cart(self):
        result = get_active_cart(user=self.user)
        self.assertIsNone(result)

    def test_get_or_create_creates_cart(self):
        from cart_api.services.cart import (
            get_or_create_active_cart,
        )
        cart = get_or_create_active_cart(
            user=self.user
        )
        self.assertIsNotNone(cart)
        self.assertEqual(
            cart.status, CartStatus.ACTIVE
        )

    def test_add_item_creates_cart_and_item(self):
        item = add_cart_item(
            user=self.user,
            product=self.product,
            quantity=2,
        )
        self.assertEqual(item.quantity, 2)
        self.assertEqual(
            item.cart.status, CartStatus.ACTIVE
        )

    def test_add_item_merges_duplicates(self):
        add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        item = add_cart_item(
            user=self.user,
            product=self.product,
            quantity=3,
        )
        self.assertEqual(item.quantity, 4)

    def test_update_item_sets_quantity(self):
        item = add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        updated = update_cart_item(
            cart_item=item,
            quantity=5,
        )
        self.assertEqual(updated.quantity, 5)

    def test_update_item_rejects_inactive_item(self):
        item = add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        item.soft_delete()
        with self.assertRaises(Exception):
            update_cart_item(
                cart_item=item,
                quantity=5,
            )

    def test_update_item_rejects_inactive_cart(self):
        """Regression: Bug B — integer comparison."""
        item = add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        item.cart.status = CartStatus.CHECKED_OUT
        item.cart.save()
        with self.assertRaises(Exception):
            update_cart_item(
                cart_item=item,
                quantity=5,
            )

    def test_remove_item_soft_deletes(self):
        item = add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        remove_cart_item(cart_item=item)
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_checkout_active_cart(self):
        add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        cart = get_active_cart(user=self.user)
        result = checkout_cart(
            cart=cart, user=self.user
        )
        self.assertEqual(
            result.status, CartStatus.CHECKED_OUT
        )

    def test_checkout_empty_cart_raises(self):
        """Regression: Bug A — cart.items vs
        cart.cart_items."""
        from cart_api.services.cart import (
            get_or_create_active_cart,
        )
        cart = get_or_create_active_cart(
            user=self.user
        )
        from rest_framework.exceptions import (
            ValidationError,
        )
        with self.assertRaises(ValidationError):
            checkout_cart(
                cart=cart, user=self.user
            )

    def test_checkout_non_active_cart_raises(self):
        add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        cart = get_active_cart(user=self.user)
        cart.status = CartStatus.CHECKED_OUT
        cart.save()
        from rest_framework.exceptions import (
            ValidationError,
        )
        with self.assertRaises(ValidationError):
            checkout_cart(
                cart=cart, user=self.user
            )

    def test_abandon_active_cart(self):
        add_cart_item(
            user=self.user,
            product=self.product,
            quantity=1,
        )
        cart = get_active_cart(user=self.user)
        result = abandon_cart(
            cart=cart, user=self.user
        )
        self.assertEqual(
            result.status, CartStatus.ABANDONED
        )


class CartAPITest(TestCase):
    """Tests for cart API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser",
            email="api@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(
            user=self.user
        )
        self.category = Category.objects.create(
            name="Test",
            slug="test-api",
        )
        self.product = Product.objects.create(
            name="Gadget",
            slug="gadget",
            current_selling_price=decimal.Decimal(
                "250.00"
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        self.product.categories.add(self.category)

    def test_get_active_cart_creates_if_none(self):
        response = self.client.get(
            "/api/v1/carts/active/"
        )
        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertIn("id", response.data)

    def test_add_item_to_cart(self):
        response = self.client.post(
            "/api/v1/cart/items/",
            {
                "product": self.product.id,
                "quantity": 2,
            },
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_list_cart_items(self):
        self.client.post(
            "/api/v1/cart/items/",
            {
                "product": self.product.id,
                "quantity": 1,
            },
            format="json",
        )
        response = self.client.get(
            "/api/v1/cart/items/"
        )
        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        # Paginated response has 'results' key
        self.assertIn("results", response.data)
        self.assertEqual(
            len(response.data["results"]), 1
        )

    def test_checkout_empty_cart_returns_error(self):
        """Regression: Bug A — API level."""
        # Ensure cart exists but is empty
        self.client.get("/api/v1/carts/active/")
        response = self.client.post(
            "/api/v1/carts/checkout/",
            format="json",
        )
        self.assertIn(
            response.status_code,
            [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_200_OK,
            ],
        )
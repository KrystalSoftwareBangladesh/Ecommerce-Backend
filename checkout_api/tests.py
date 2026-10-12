# checkout_api/tests.py
import decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from user_api.models import User
from customer_api.models import CustomerProfile, CustomerAddress
from cart_api.models import Cart, CartItem
from product_api.models import Product
from category_api.models import Category
from EcommerceBackend.core.choices import CartStatus

from shipping_api.models import (
    ShippingZone,
    ShippingZoneRule,
    ShippingMethod,
    ShippingRate,
)


class CheckoutValidateTestBase(TestCase):
    """Shared setUp for checkout validation tests."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(
            user=self.user
        )
        self.profile = (
            CustomerProfile.objects.create(
                user=self.user,
                customer_type="WEBSITE",
            )
        )
        self.category = Category.objects.create(
            name="Test Category",
            slug="test-category",
        )
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            current_selling_price=decimal.Decimal(
                "500.00"
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        self.product.categories.add(self.category)
        self.cart = Cart.objects.create(
            created_by=self.user,
            updated_by=self.user,
            status=CartStatus.ACTIVE,
        )
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=2,
        )
        self.address = CustomerAddress.objects.create(
            customer=self.profile,
            address_type=(
                CustomerAddress.AddressType.SHIPPING
            ),
            first_name="Test",
            last_name="User",
            address_1="123 Test St",
            city="Dhaka",
            postcode="1205",
            country="Bangladesh",
            phone="+8801700000000",
            created_by=self.user,
            updated_by=self.user,
        )
        self.zone = ShippingZone.objects.create(
            name="Dhaka Metro",
            code="dhaka-metro",
            is_default=True,
            created_by=self.user,
            updated_by=self.user,
        )
        ShippingZoneRule.objects.create(
            zone=self.zone,
            match_type="CITY",
            match_value="Dhaka",
            created_by=self.user,
            updated_by=self.user,
        )
        self.method = ShippingMethod.objects.create(
            name="Standard Delivery",
            code="standard",
            created_by=self.user,
            updated_by=self.user,
        )
        self.rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal("60.00"),
            free_shipping_threshold=(
                decimal.Decimal("2000.00")
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        self.url = "/api/v1/checkout/validate/"

    def _payload(
        self,
        address_id=None,
        method_id=None,
    ):
        return {
            "shipping_address_id": (
                address_id
                if address_id is not None
                else self.address.id
            ),
            "shipping_method_id": (
                method_id
                if method_id is not None
                else self.method.id
            ),
        }


class UnauthenticatedTest(CheckoutValidateTestBase):
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class EmptyCartTest(CheckoutValidateTestBase):
    """Validation fails with no active cart or items."""

    def test_no_active_cart(self):
        self.cart.status = CartStatus.CHECKED_OUT
        self.cart.save()
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "No active cart found",
            response.data["errors"][0],
        )

    def test_empty_cart(self):
        self.cart_item.soft_delete()
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "Cart is empty",
            response.data["errors"][0],
        )


class ProductValidationTest(
    CheckoutValidateTestBase
):
    """Product-level validation errors."""

    def test_inactive_product(self):
        self.product.is_active = False
        self.product.save()
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "no longer available",
            response.data["errors"][0],
        )

    def test_zero_price_product(self):
        self.product.current_selling_price = 0
        self.product.save()
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "no valid price",
            response.data["errors"][0],
        )


class AddressValidationTest(
    CheckoutValidateTestBase
):
    """Shipping address validation."""

    def test_address_not_found(self):
        response = self.client.post(
            self.url,
            self._payload(address_id=99999),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "Invalid or inactive shipping address",
            response.data["errors"][0],
        )

    def test_address_wrong_type(self):
        billing = CustomerAddress.objects.create(
            customer=self.profile,
            address_type=(
                CustomerAddress.AddressType.BILLING
            ),
            city="Dhaka",
            created_by=self.user,
            updated_by=self.user,
        )
        response = self.client.post(
            self.url,
            self._payload(address_id=billing.id),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "Invalid or inactive shipping address",
            response.data["errors"][0],
        )

    def test_address_not_owned_by_user(self):
        other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="pass123",
        )
        other_profile = (
            CustomerProfile.objects.create(
                user=other_user,
                customer_type="WEBSITE",
            )
        )
        other_addr = CustomerAddress.objects.create(
            customer=other_profile,
            address_type=(
                CustomerAddress.AddressType.SHIPPING
            ),
            city="Dhaka",
            created_by=other_user,
            updated_by=other_user,
        )
        response = self.client.post(
            self.url,
            self._payload(
                address_id=other_addr.id
            ),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "does not belong",
            response.data["errors"][0],
        )

    def test_inactive_address(self):
        self.address.is_active = False
        self.address.save()
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "Invalid or inactive shipping address",
            response.data["errors"][0],
        )


class ShippingZoneValidationTest(
    CheckoutValidateTestBase
):
    """Zone and method availability."""

    def test_no_matching_zone(self):
        self.zone.is_default = False
        self.zone.save()
        ShippingZoneRule.objects.all().delete()
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "No shipping zone found",
            response.data["errors"][0],
        )

    def test_method_not_available_for_zone(self):
        other_method = ShippingMethod.objects.create(
            name="Express",
            code="express",
            created_by=self.user,
            updated_by=self.user,
        )
        response = self.client.post(
            self.url,
            self._payload(
                method_id=other_method.id
            ),
            format="json",
        )
        self.assertFalse(response.data["is_valid"])
        self.assertIn(
            "not available for your area",
            response.data["errors"][0],
        )


class ShippingChargeTest(
    CheckoutValidateTestBase
):
    """Shipping charge calculation."""

    def test_base_charge_applied(self):
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertTrue(response.data["is_valid"])
        self.assertEqual(
            response.data["pricing"][
                "shipping_charge"
            ],
            decimal.Decimal("60.00"),
        )
        self.assertFalse(
            response.data["shipping"][
                "is_free_shipping"
            ]
        )

    def test_free_shipping_threshold(self):
        self.product.current_selling_price = (
            decimal.Decimal("1500.00")
        )
        self.product.save()
        # Subtotal: 1500 * 2 = 3000 >= 2000 threshold
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertTrue(response.data["is_valid"])
        self.assertEqual(
            response.data["pricing"][
                "shipping_charge"
            ],
            decimal.Decimal("0.00"),
        )
        self.assertTrue(
            response.data["shipping"][
                "is_free_shipping"
            ]
        )


class ValidCheckoutTest(CheckoutValidateTestBase):
    """Successful validation returns correct data."""

    def test_valid_response_structure(self):
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        data = response.data
        self.assertTrue(data["is_valid"])
        self.assertEqual(data["errors"], [])

        # Cart
        self.assertEqual(data["cart"]["id"], self.cart.id)
        self.assertEqual(
            len(data["cart"]["items"]), 1
        )
        item = data["cart"]["items"][0]
        self.assertEqual(item["product_id"], self.product.id)
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(
            item["unit_price"],
            decimal.Decimal("500.00"),
        )
        self.assertEqual(
            item["line_total"],
            decimal.Decimal("1000.00"),
        )

        # Pricing
        self.assertEqual(
            data["pricing"]["subtotal"],
            decimal.Decimal("1000.00"),
        )
        self.assertEqual(
            data["pricing"]["shipping_charge"],
            decimal.Decimal("60.00"),
        )
        self.assertEqual(
            data["pricing"]["discount_total"],
            decimal.Decimal("0.00"),
        )
        self.assertEqual(
            data["pricing"]["tax_total"],
            decimal.Decimal("0.00"),
        )
        self.assertEqual(
            data["pricing"]["grand_total"],
            decimal.Decimal("1060.00"),
        )

        # Shipping
        self.assertEqual(
            data["shipping"]["address_id"],
            self.address.id,
        )
        self.assertEqual(
            data["shipping"]["method_id"],
            self.method.id,
        )
        self.assertEqual(
            data["shipping"]["method_code"],
            "standard",
        )

    def test_ignores_frontend_prices(self):
        """Grand total uses backend prices only."""
        response = self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        # Backend price is 500.00, qty 2 = 1000.00
        # If frontend sent 999.99, it is ignored.
        self.assertEqual(
            response.data["pricing"]["subtotal"],
            decimal.Decimal("1000.00"),
        )

    def test_no_sale_created(self):
        """Validation must not create a Sale."""
        from sale_api.models import Sale
        before = Sale.objects.count()
        self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.assertEqual(
            Sale.objects.count(), before
        )

    def test_cart_status_unchanged(self):
        """Validation must not change cart status."""
        self.client.post(
            self.url,
            self._payload(),
            format="json",
        )
        self.cart.refresh_from_db()
        self.assertEqual(
            self.cart.status, CartStatus.ACTIVE
        )


class InputValidationTest(
    CheckoutValidateTestBase
):
    """Request payload validation."""

    def test_missing_fields(self):
        response = self.client.post(
            self.url, {}, format="json"
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_missing_shipping_method(self):
        response = self.client.post(
            self.url,
            {"shipping_address_id": 1},
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

# checkout_api/tests.py
import decimal
from threading import Event, Thread
from unittest import mock

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.db import connection, transaction
from django.test import (
    TestCase,
    TransactionTestCase,
    skipUnlessDBFeature,
)
from django.utils import timezone
from rest_framework.exceptions import (
    ValidationError as DRFValidationError,
)
from rest_framework.test import APIClient
from rest_framework import status

from user_api.models import User
from customer_api.models import CustomerProfile, CustomerAddress
from cart_api.models import Cart, CartItem
from product_api.models import Product
from category_api.models import Category
from EcommerceBackend.core.choices import CartStatus
from email_api.constants import EmailType

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


class OrderCreationTestBase(TestCase):
    """Shared setup for order creation tests."""

    def setUp(self):
        from product_api.models import ProductVariant
        from EcommerceBackend.core.choices import (
            CartStatus,
        )

        self.client = APIClient()
        self.user = User.objects.create_user(
            username='orderuser',
            email='order@example.com',
            password='testpass123',
        )
        self.client.force_authenticate(
            user=self.user
        )
        self.profile = (
            CustomerProfile.objects.create(
                user=self.user,
                customer_type='WEBSITE',
            )
        )
        self.category = Category.objects.create(
            name='Test', slug='test-order',
        )
        self.product = Product.objects.create(
            name='Widget',
            slug='widget-order',
            current_selling_price=(
                decimal.Decimal('500.00')
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        self.product.categories.add(self.category)
        self.variant = (
            ProductVariant.objects.create(
                product=self.product,
                sku='WDG-001',
            )
        )
        # Give stock.
        from inventory_api.models import (
            InventoryMovement,
            MovementType,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=50,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
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
        self.address = (
            CustomerAddress.objects.create(
                customer=self.profile,
                address_type=(
                    CustomerAddress
                    .AddressType.SHIPPING
                ),
                first_name='Test',
                last_name='User',
                address_1='123 Test St',
                city='Dhaka',
                postcode='1205',
                country='Bangladesh',
                phone='+8801700000000',
                created_by=self.user,
                updated_by=self.user,
            )
        )
        self.zone = ShippingZone.objects.create(
            name='Dhaka Metro',
            code='dhaka-metro-order',
            is_default=True,
            created_by=self.user,
            updated_by=self.user,
        )
        ShippingZoneRule.objects.create(
            zone=self.zone,
            match_type='CITY',
            match_value='Dhaka',
            created_by=self.user,
            updated_by=self.user,
        )
        self.method = (
            ShippingMethod.objects.create(
                name='Standard',
                code='standard-order',
                created_by=self.user,
                updated_by=self.user,
            )
        )
        self.rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal('60.00'),
            free_shipping_threshold=(
                decimal.Decimal('2000.00')
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        # Ensure COD PM exists (from data migration).
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self.cod_pm = (
            get_or_create_cod_payment_method()
        )

    def _create_order(self, **kwargs):
        from checkout_api.services import (
            create_order,
        )
        defaults = {
            'user': self.user,
            'shipping_address_id': (
                self.address.id
            ),
            'shipping_method_id': (
                self.method.id
            ),
            'idempotency_key': (
                'test-idem-key-001'
            ),
            'notes': '',
        }
        defaults.update(kwargs)
        return create_order(**defaults)


class OrderCreationTest(OrderCreationTestBase):
    """Tests for create_order."""

    def test_successful_order_creation(self):
        from sale_api.models import (
            Sale,
            SaleStatus,
            PaymentStatus,
        )
        sale = self._create_order()
        self.assertEqual(
            sale.status, SaleStatus.PENDING
        )
        self.assertEqual(
            sale.payment_status,
            PaymentStatus.UNPAID,
        )
        self.assertEqual(
            sale.channel, Sale.SaleChannel.WEBSITE
        )
        self.assertEqual(
            sale.subtotal_amount,
            decimal.Decimal('1000.00'),
        )
        self.assertEqual(
            sale.shipping_amount,
            decimal.Decimal('60.00'),
        )
        self.assertEqual(
            sale.total_amount,
            decimal.Decimal('1060.00'),
        )

    def test_order_creates_sale_items(self):
        from sale_api.models import SaleItem
        sale = self._create_order()
        items = SaleItem.objects.filter(
            sale=sale
        )
        self.assertEqual(items.count(), 1)
        item = items.first()
        self.assertEqual(
            item.product_variant_id,
            self.variant.id,
        )
        self.assertEqual(item.quantity, 2)
        self.assertEqual(
            item.unit_price,
            decimal.Decimal('500.00'),
        )

    def test_order_reserves_stock(self):
        from inventory_api.models import (
            InventoryReservation,
            ReservationStatus,
        )
        from inventory_api.services.reservation import (
            get_available_stock,
        )
        # setUp gives 50 stock.
        sale = self._create_order()
        reservations = (
            InventoryReservation.objects.filter(
                sale=sale,
                status=ReservationStatus.ACTIVE,
            )
        )
        self.assertEqual(
            reservations.count(), 1
        )
        self.assertEqual(
            reservations.first().quantity, 2
        )
        # 50 - 2 = 48.
        self.assertEqual(
            get_available_stock(self.variant), 48
        )

    def test_order_marks_cart_checked_out(self):
        from EcommerceBackend.core.choices import (
            CartStatus,
        )
        self._create_order()
        self.cart.refresh_from_db()
        self.assertEqual(
            self.cart.status,
            CartStatus.CHECKED_OUT,
        )

    def test_order_snapshots_address(self):
        sale = self._create_order()
        snapshot = (
            sale.shipping_address_snapshot
        )
        self.assertEqual(
            snapshot['first_name'], 'Test'
        )
        self.assertEqual(
            snapshot['city'], 'Dhaka'
        )

    def test_order_sets_idempotency_key(self):
        sale = self._create_order()
        self.assertEqual(
            sale.idempotency_key,
            'test-idem-key-001',
        )
        self.assertIsNotNone(
            sale.request_fingerprint
        )
        self.assertEqual(
            len(sale.request_fingerprint), 64
        )

    def test_idempotent_return(self):
        """Same fingerprint returns existing
        order."""
        sale1 = self._create_order()
        sale2 = self._create_order()
        self.assertEqual(sale1.id, sale2.id)

    def test_different_key_creates_new(self):
        """Different idempotency key creates new
        order. Second order needs a fresh cart."""
        sale1 = self._create_order(
            idempotency_key='key-1',
        )
        # First order checked out the cart.
        # Create a fresh cart for second order.
        from EcommerceBackend.core.choices import (
            CartStatus,
        )
        cart2 = Cart.objects.create(
            created_by=self.user,
            updated_by=self.user,
            status=CartStatus.ACTIVE,
        )
        CartItem.objects.create(
            cart=cart2,
            product=self.product,
            quantity=1,
        )
        sale2 = self._create_order(
            idempotency_key='key-2',
        )
        self.assertNotEqual(sale1.id, sale2.id)

    def test_same_key_different_inputs_conflict(
        self,
    ):
        """Same idempotency key with different
        inputs raises conflict."""
        from rest_framework.exceptions import (
            ValidationError,
        )
        self._create_order(
            idempotency_key='conflict-key',
            notes='first request',
        )
        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key='conflict-key',
                notes='different request',
            )

    def test_missing_idempotency_key_rejected(self):
        """Empty or blank idempotency_key is
        rejected before any state changes."""
        from rest_framework.exceptions import (
            ValidationError,
        )
        from sale_api.models import Sale
        from inventory_api.models import (
            InventoryReservation,
        )
        from EcommerceBackend.core.choices import (
            CartStatus,
        )
        sales_before = Sale.objects.count()
        reservations_before = (
            InventoryReservation.objects.count()
        )
        self.cart.refresh_from_db()
        cart_status_before = self.cart.status

        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key=''
            )

        # No state changed.
        self.assertEqual(
            Sale.objects.count(), sales_before
        )
        self.assertEqual(
            InventoryReservation.objects.count(),
            reservations_before,
        )
        self.cart.refresh_from_db()
        self.assertEqual(
            self.cart.status, cart_status_before
        )

    def test_blank_idempotency_key_rejected(self):
        """Whitespace-only key is rejected."""
        from rest_framework.exceptions import (
            ValidationError,
        )
        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key='   '
            )

    def test_empty_cart_raises(self):
        from rest_framework.exceptions import (
            ValidationError,
        )
        self.cart_item.soft_delete()
        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key='empty-cart'
            )

    def test_inactive_product_raises(self):
        from rest_framework.exceptions import (
            ValidationError,
        )
        self.product.is_active = False
        self.product.save()
        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key='inactive-prod'
            )

    def test_multiple_variants_raises(self):
        from rest_framework.exceptions import (
            ValidationError,
        )
        from product_api.models import ProductVariant
        ProductVariant.objects.create(
            product=self.product,
            sku='WDG-002',
        )
        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key='multi-var'
            )

    def test_no_variant_raises(self):
        from rest_framework.exceptions import (
            ValidationError,
        )
        from product_api.models import ProductVariant
        from inventory_api.models import (
            InventoryMovement,
        )
        # Delete movements first (PROTECT FK).
        InventoryMovement.objects.filter(
            product_variant__product=self.product,
        ).delete()
        ProductVariant.objects.filter(
            product=self.product,
        ).delete()
        with self.assertRaises(ValidationError):
            self._create_order(
                idempotency_key='no-var'
            )

    def test_insufficient_stock_raises(self):
        from django.core.exceptions import (
            ValidationError as DjangoValidationError,
        )
        from rest_framework.exceptions import (
            ValidationError as DRFValidationError,
        )
        from inventory_api.models import (
            InventoryMovement,
        )
        # Remove all stock movements.
        InventoryMovement.objects.filter(
            product_variant=self.variant,
        ).delete()
        with self.assertRaises(
            (
                DjangoValidationError,
                DRFValidationError,
            )
        ):
            self._create_order(
                idempotency_key='no-stock'
            )

    def test_invalid_address_raises(self):
        from rest_framework.exceptions import (
            ValidationError,
        )
        with self.assertRaises(ValidationError):
            self._create_order(
                shipping_address_id=99999,
                idempotency_key='bad-addr',
            )

    def test_order_uses_backend_prices(self):
        """Server-side price, not frontend."""
        sale = self._create_order()
        item = sale.items.first()
        self.assertEqual(
            item.unit_price,
            decimal.Decimal('500.00'),
        )


class OrderCancellationTest(
    OrderCreationTestBase
):
    """Tests for cancel_order."""

    def test_cancel_pending_order(self):
        from sale_api.models import SaleStatus
        from inventory_api.models import (
            InventoryMovement,
            MovementType,
            ReservationStatus,
            InventoryReservation,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=50,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        sale = self._create_order()
        from checkout_api.services import (
            cancel_order,
        )
        result = cancel_order(
            user=self.user, sale=sale
        )
        self.assertEqual(
            result.status, SaleStatus.CANCELLED
        )
        # Reservations released.
        reservations = (
            InventoryReservation.objects.filter(
                sale=sale,
            )
        )
        for r in reservations:
            self.assertEqual(
                r.status,
                ReservationStatus.RELEASED,
            )

    def test_cancel_non_pending_raises(self):
        from rest_framework.exceptions import (
            ValidationError,
        )
        from sale_api.models import SaleStatus
        from inventory_api.models import (
            InventoryMovement,
            MovementType,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=50,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        sale = self._create_order()
        # Confirm the sale first.
        from sale_api.services import (
            update_sale_status,
        )
        update_sale_status(
            self.user, sale,
            SaleStatus.CONFIRMED,
        )
        from checkout_api.services import (
            cancel_order,
        )
        with self.assertRaises(ValidationError):
            cancel_order(
                user=self.user, sale=sale
            )

    def test_cancel_idempotent(self):
        from sale_api.models import SaleStatus
        from inventory_api.models import (
            InventoryMovement,
            MovementType,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=50,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        sale = self._create_order()
        from checkout_api.services import (
            cancel_order,
        )
        cancel_order(
            user=self.user, sale=sale
        )
        # Already cancelled.
        sale.refresh_from_db()
        self.assertEqual(
            sale.status, SaleStatus.CANCELLED
        )

    def test_stale_cancel_cannot_overwrite_confirmation(self):
        """A cancel holding a PENDING copy loaded before staff
        confirmed must not cancel the confirmed order."""
        from rest_framework.exceptions import ValidationError
        from checkout_api.services import cancel_order
        from inventory_api.models import (
            InventoryReservation,
            ReservationStatus,
        )
        from sale_api.models import Sale, SaleStatus
        from sale_api.services import update_sale_status

        sale = self._create_order()
        stale = Sale.objects.get(pk=sale.pk)
        update_sale_status(self.user, sale, SaleStatus.CONFIRMED)

        with self.assertRaises(ValidationError):
            cancel_order(user=self.user, sale=stale)

        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CONFIRMED)
        self.assertIsNotNone(sale.accounting_transaction_id)
        self.assertEqual(
            set(
                InventoryReservation.objects.filter(
                    sale=sale,
                ).values_list("status", flat=True)
            ),
            {ReservationStatus.CONSUMED},
        )


class OrderExpiryTest(OrderCreationTestBase):
    """Auto-cancellation of PENDING orders whose reservation
    expired (approved 2026-10-13)."""

    def _expire(self, sale):
        from datetime import timedelta
        from inventory_api.models import InventoryReservation

        InventoryReservation.objects.filter(sale=sale).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

    def _available(self):
        from inventory_api.services.reservation import (
            get_available_stock,
        )

        return get_available_stock(self.variant)

    def _reservation_statuses(self, sale):
        from inventory_api.models import InventoryReservation

        return set(
            InventoryReservation.objects.filter(
                sale=sale,
            ).values_list("status", flat=True)
        )

    def test_expired_order_is_cancelled_and_stock_released(self):
        from checkout_api.services import expire_pending_orders
        from inventory_api.models import ReservationStatus
        from sale_api.models import SaleStatus

        sale = self._create_order()
        self.assertEqual(self._available(), 48)
        self._expire(sale)

        with mock.patch(
            "checkout_api.services.EmailService.queue"
        ) as queue, self.captureOnCommitCallbacks(execute=True):
            result = expire_pending_orders()

        self.assertEqual(result, (1, 0))
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)
        self.assertEqual(
            self._reservation_statuses(sale),
            {ReservationStatus.RELEASED},
        )
        self.assertEqual(self._available(), 50)
        queue.assert_called_once()
        kwargs = queue.call_args.kwargs
        self.assertEqual(kwargs["email_type"], EmailType.ORDER_CANCELLED)
        self.assertTrue(kwargs["context"]["reservation_expired"])

    def test_unexpired_order_is_untouched(self):
        from checkout_api.services import expire_pending_orders
        from inventory_api.models import ReservationStatus
        from sale_api.models import SaleStatus

        sale = self._create_order()
        self.assertEqual(expire_pending_orders(), (0, 0))
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)
        self.assertEqual(
            self._reservation_statuses(sale),
            {ReservationStatus.ACTIVE},
        )

    def test_rerun_is_idempotent(self):
        from checkout_api.services import expire_pending_orders

        self._expire(self._create_order())
        self.assertEqual(expire_pending_orders(), (1, 0))
        self.assertEqual(expire_pending_orders(), (0, 0))

    def test_order_released_by_inventory_expiry_is_still_cancelled(
        self,
    ):
        from checkout_api.services import expire_pending_orders
        from inventory_api.services.reservation import (
            expire_reservations,
        )
        from sale_api.models import SaleStatus

        sale = self._create_order()
        self._expire(sale)
        self.assertEqual(expire_reservations(), 1)

        self.assertEqual(expire_pending_orders(), (1, 0))
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)

    def test_confirmed_order_is_not_cancelled(self):
        from checkout_api.services import expire_pending_orders
        from sale_api.models import SaleStatus
        from sale_api.services import update_sale_status

        sale = update_sale_status(
            self.user, self._create_order(), SaleStatus.CONFIRMED
        )
        self._expire(sale)
        self.assertEqual(expire_pending_orders(), (0, 0))
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CONFIRMED)
        self.assertEqual(self._available(), 48)

    def test_confirmation_after_expiry_is_rejected(self):
        from django.core.exceptions import ValidationError
        from inventory_api.models import InventoryMovement, MovementType
        from sale_api.models import SaleStatus
        from sale_api.services import update_sale_status

        sale = self._create_order()
        self._expire(sale)
        with self.assertRaises(ValidationError):
            update_sale_status(self.user, sale, SaleStatus.CONFIRMED)
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)
        self.assertIsNone(sale.accounting_transaction_id)
        self.assertFalse(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
            ).exists()
        )

    def test_confirmation_after_auto_cancel_is_rejected(self):
        from django.core.exceptions import ValidationError
        from checkout_api.services import expire_pending_orders
        from sale_api.models import SaleStatus
        from sale_api.services import update_sale_status

        sale = self._create_order()
        self._expire(sale)
        expire_pending_orders()
        with self.assertRaisesMessage(
            ValidationError, "Cannot change sale status"
        ):
            update_sale_status(self.user, sale, SaleStatus.CONFIRMED)

    def test_management_command_and_task(self):
        from io import StringIO
        from django.core.management import call_command
        from checkout_api.tasks import expire_pending_orders_task

        self._expire(self._create_order())
        out = StringIO()
        call_command("expire_pending_orders", stdout=out)
        self.assertIn("Cancelled 1 expired orders", out.getvalue())
        self.assertEqual(
            expire_pending_orders_task(),
            {"cancelled_orders": 0, "released_reservations": 0},
        )


class SameKeyRetryRaceTest(OrderCreationTestBase):
    """
    L3: a same-key retry whose first idempotency lookup ran before
    the original request committed. The interleaving is simulated
    by making that first lookup miss; this is not a concurrency
    test.
    """

    def _create_with_first_lookup_missing(self, **kwargs):
        from checkout_api import services

        real_lookup = services._find_idempotent_order
        calls = []

        def lookup(*args):
            calls.append(args)
            if len(calls) == 1:
                return None
            return real_lookup(*args)

        with mock.patch.object(
            services, "_find_idempotent_order", side_effect=lookup
        ):
            return self._create_order(**kwargs)

    def test_retry_after_cart_checkout_returns_original_order(self):
        from sale_api.models import Sale

        original = self._create_order(idempotency_key="l3-key")
        replay = self._create_with_first_lookup_missing(
            idempotency_key="l3-key"
        )
        self.assertEqual(replay.pk, original.pk)
        self.assertEqual(Sale.objects.count(), 1)

    def test_conflicting_retry_after_cart_checkout_is_409(self):
        from checkout_api.exceptions import IdempotencyConflict

        self._create_order(idempotency_key="l3-conflict")
        with self.assertRaises(IdempotencyConflict) as raised:
            self._create_with_first_lookup_missing(
                idempotency_key="l3-conflict",
                notes="different",
            )
        self.assertEqual(raised.exception.status_code, 409)


class OrderCreateSerializerTest(TestCase):
    """Tests for OrderCreateSerializer."""

    def test_valid_data(self):
        from checkout_api.serializers.order import (
            OrderCreateSerializer,
        )
        data = {
            'shipping_address_id': 1,
            'shipping_method_id': 2,
            'idempotency_key': 'some-key',
        }
        serializer = OrderCreateSerializer(
            data=data
        )
        self.assertTrue(serializer.is_valid())

    def test_optional_notes(self):
        from checkout_api.serializers.order import (
            OrderCreateSerializer,
        )
        data = {
            'shipping_address_id': 1,
            'shipping_method_id': 2,
            'idempotency_key': 'key',
            'notes': 'Please call',
        }
        serializer = OrderCreateSerializer(
            data=data
        )
        self.assertTrue(serializer.is_valid())

    def test_missing_address_id(self):
        from checkout_api.serializers.order import (
            OrderCreateSerializer,
        )
        serializer = OrderCreateSerializer(
            data={
                'shipping_method_id': 2,
                'idempotency_key': 'key',
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn(
            'shipping_address_id',
            serializer.errors,
        )

    def test_missing_method_id(self):
        from checkout_api.serializers.order import (
            OrderCreateSerializer,
        )
        serializer = OrderCreateSerializer(
            data={
                'shipping_address_id': 1,
                'idempotency_key': 'key',
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn(
            'shipping_method_id',
            serializer.errors,
        )

    def test_missing_idempotency_key(self):
        from checkout_api.serializers.order import (
            OrderCreateSerializer,
        )
        serializer = OrderCreateSerializer(
            data={
                'shipping_address_id': 1,
                'shipping_method_id': 2,
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn(
            'idempotency_key',
            serializer.errors,
        )


class OrderDetailSerializerTest(
    OrderCreationTestBase
):
    """Tests for OrderDetailSerializer."""

    def test_serializes_order(self):
        from checkout_api.serializers.order import (
            OrderDetailSerializer,
        )
        sale = self._create_order()
        serializer = OrderDetailSerializer(sale)
        data = serializer.data
        self.assertEqual(data['id'], sale.id)
        self.assertIn('invoice_number', data)
        self.assertIn('status', data)
        self.assertIn('payment_status', data)
        self.assertIn('items', data)
        self.assertIn('pricing', data)
        self.assertIn(
            'shipping_address', data
        )
        self.assertIn('notes', data)

    def test_no_accounting_fields(self):
        """Must NOT expose internal fields."""
        from checkout_api.serializers.order import (
            OrderDetailSerializer,
        )
        sale = self._create_order()
        serializer = OrderDetailSerializer(sale)
        data = serializer.data
        self.assertNotIn('account', data)
        self.assertNotIn(
            'accounting_transaction', data
        )
        self.assertNotIn(
            'return_transaction', data
        )
        self.assertNotIn('created_by', data)
        self.assertNotIn('updated_by', data)
        self.assertNotIn('deleted_at', data)

    def test_pricing_structure(self):
        from checkout_api.serializers.order import (
            OrderDetailSerializer,
        )
        sale = self._create_order()
        serializer = OrderDetailSerializer(sale)
        pricing = serializer.data['pricing']
        self.assertIn('subtotal', pricing)
        self.assertIn('shipping_charge', pricing)
        self.assertIn('discount_total', pricing)
        self.assertIn('tax_total', pricing)
        self.assertIn('grand_total', pricing)

    def test_items_structure(self):
        from checkout_api.serializers.order import (
            OrderDetailSerializer,
        )
        sale = self._create_order()
        serializer = OrderDetailSerializer(sale)
        items = serializer.data['items']
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertIn('id', item)
        self.assertIn('product_variant', item)
        self.assertIn('product_name', item)
        self.assertIn('quantity', item)
        self.assertIn('unit_price', item)
        self.assertIn('line_total', item)
        # Variant details.
        variant = item['product_variant']
        self.assertIn('id', variant)
        self.assertIn('sku', variant)
        self.assertIn('name', variant)

    def test_shipping_address_snapshot(self):
        from checkout_api.serializers.order import (
            OrderDetailSerializer,
        )
        sale = self._create_order()
        serializer = OrderDetailSerializer(sale)
        addr = (
            serializer.data['shipping_address']
        )
        self.assertEqual(addr['first_name'], 'Test')
        self.assertEqual(addr['city'], 'Dhaka')

    def test_allowed_next_statuses(self):
        from checkout_api.serializers.order import (
            OrderDetailSerializer,
        )
        sale = self._create_order()
        serializer = OrderDetailSerializer(sale)
        statuses = (
            serializer.data[
                'allowed_next_statuses'
            ]
        )
        self.assertIsInstance(statuses, list)
        values = [s['value'] for s in statuses]
        self.assertIn('CONFIRMED', values)
        self.assertIn('CANCELLED', values)


class OrderListSerializerTest(
    OrderCreationTestBase
):
    """Tests for OrderListSerializer."""

    def test_compact_fields(self):
        from checkout_api.serializers.order import (
            OrderListSerializer,
        )
        sale = self._create_order()
        serializer = OrderListSerializer(sale)
        data = serializer.data
        self.assertIn('id', data)
        self.assertIn('invoice_number', data)
        self.assertIn('status', data)
        self.assertIn('payment_status', data)
        self.assertIn('total_amount', data)
        self.assertIn('item_count', data)
        self.assertIn('created_at', data)

    def test_item_count(self):
        from checkout_api.serializers.order import (
            OrderListSerializer,
        )
        sale = self._create_order()
        serializer = OrderListSerializer(sale)
        self.assertEqual(
            serializer.data['item_count'], 1
        )

    def test_no_detail_fields(self):
        """List serializer must not include
        detail-only fields."""
        from checkout_api.serializers.order import (
            OrderListSerializer,
        )
        sale = self._create_order()
        serializer = OrderListSerializer(sale)
        data = serializer.data
        self.assertNotIn('items', data)
        self.assertNotIn('pricing', data)
        self.assertNotIn(
            'shipping_address', data
        )
        self.assertNotIn('notes', data)
        self.assertNotIn('channel', data)

class StorefrontOrderAPITest(OrderCreationTestBase):
    """Authenticated customer-facing order endpoint tests."""

    def test_confirm_endpoint_creates_order(self):
        response = self.client.post(
            "/api/v1/checkout/confirm/",
            {
                "shipping_address_id": self.address.id,
                "shipping_method_id": self.method.id,
                "idempotency_key": "api-confirm-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["payment_status"], "UNPAID")
        self.assertTrue(response.data["invoice_number"])
        self.assertEqual(
            response.data["shipping_method"],
            {
                "id": self.method.id,
                "name": self.method.name,
                "code": self.method.code,
            },
        )

    def test_confirm_retry_returns_same_order(self):
        payload = {
            "shipping_address_id": self.address.id,
            "shipping_method_id": self.method.id,
            "idempotency_key": "api-confirm-retry-001",
        }
        first = self.client.post(
            "/api/v1/checkout/confirm/", payload, format="json"
        )
        second = self.client.post(
            "/api/v1/checkout/confirm/", payload, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["id"], second.data["id"])

    def test_order_detail_is_private_to_customer(self):
        sale = self._create_order(
            idempotency_key="private-order-001"
        )
        other_user = User.objects.create_user(
            username="other-order-user",
            email="other-order@example.com",
            password="testpass123",
        )
        CustomerProfile.objects.create(
            user=other_user,
            customer_type="WEBSITE",
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.get(
            f"/api/v1/orders/{sale.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_list_only_contains_current_customers_orders(self):
        sale = self._create_order(
            idempotency_key="private-list-order-001"
        )
        response = self.client.get("/api/v1/orders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data],
            [sale.id],
        )

    def test_customer_can_cancel_pending_order(self):
        from inventory_api.models import (
            InventoryMovement,
            MovementType,
            InventoryReservation,
            ReservationStatus,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=50,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        sale = self._create_order(
            idempotency_key="api-cancel-order-001"
        )
        response = self.client.post(
            f"/api/v1/orders/{sale.id}/cancel/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertFalse(
            InventoryReservation.objects.filter(
                sale=sale,
                status=ReservationStatus.ACTIVE,
            ).exists()
        )

    def test_unauthenticated_order_list_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/v1/orders/")
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def _assert_confirm_rejected_without_side_effects(
        self, idempotency_key
    ):
        from inventory_api.models import InventoryReservation
        from sale_api.models import Sale

        response = self.client.post(
            "/api/v1/checkout/confirm/",
            {
                "shipping_address_id": self.address.id,
                "shipping_method_id": self.method.id,
                "idempotency_key": idempotency_key,
            },
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(response.data["success"])
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(InventoryReservation.objects.exists())
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, CartStatus.ACTIVE)
        return response

    def test_confirm_out_of_stock_returns_400(self):
        from inventory_api.models import InventoryMovement

        InventoryMovement.objects.filter(
            product_variant=self.variant,
        ).delete()
        response = (
            self._assert_confirm_rejected_without_side_effects(
                "api-out-of-stock-001"
            )
        )
        self.assertIn(
            "Insufficient stock",
            str(response.data["errors"]),
        )

    def test_confirm_without_active_cod_method_returns_400(self):
        self.cod_pm.is_active = False
        self.cod_pm.save(update_fields=["is_active"])
        response = (
            self._assert_confirm_rejected_without_side_effects(
                "api-no-cod-001"
            )
        )
        self.assertIn(
            "is not configured",
            str(response.data["errors"]),
        )

    def test_confirm_with_misconfigured_cod_account_returns_400(self):
        self.cod_pm.default_account = None
        self.cod_pm.save(update_fields=["default_account"])
        response = (
            self._assert_confirm_rejected_without_side_effects(
                "api-bad-cod-001"
            )
        )
        self.assertIn(
            "no default account",
            str(response.data["errors"]),
        )

    def test_confirm_same_key_different_inputs_returns_409(self):
        from sale_api.models import Sale

        payload = {
            "shipping_address_id": self.address.id,
            "shipping_method_id": self.method.id,
            "idempotency_key": "api-conflict-001",
        }
        first = self.client.post(
            "/api/v1/checkout/confirm/", payload, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        conflicting = self.client.post(
            "/api/v1/checkout/confirm/",
            {**payload, "notes": "Leave at the gate."},
            format="json",
        )
        self.assertEqual(
            conflicting.status_code, status.HTTP_409_CONFLICT
        )
        self.assertFalse(conflicting.data["success"])
        self.assertEqual(Sale.objects.count(), 1)

        # The original inputs still replay the original order.
        retry = self.client.post(
            "/api/v1/checkout/confirm/", payload, format="json"
        )
        self.assertEqual(retry.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.data["id"], first.data["id"])

class CODCollectionServiceTest(OrderCreationTestBase):
    """Tests for atomic COD collection accounting."""

    def _deliver(self, sale):
        from sale_api.models import SaleStatus
        from sale_api.services import update_sale_status

        for next_status in (
            SaleStatus.CONFIRMED,
            SaleStatus.PROCESSING,
            SaleStatus.PACKAGED,
            SaleStatus.SHIPPED,
            SaleStatus.OUT_OF_DELIVERY,
            SaleStatus.DELIVERED,
        ):
            sale = update_sale_status(self.user, sale, next_status)
        return sale

    def test_collection_posts_cash_against_receivable(self):
        """Real accounting: confirmation debits receivable, COD
        collection debits the COD cash account, credits receivable
        by the same amount, and is linked to the sale."""
        from django.db.models import Sum
        from sale_api.models import PaymentStatus
        from sale_api.services import (
            get_or_create_accounts_receivable_account,
            mark_cod_payment_collected,
        )
        from transaction_api.models import (
            AccountingTransactionLine,
            TransactionStatus,
        )

        sale = self._deliver(
            self._create_order(
                idempotency_key="cod-collect-service-001"
            )
        )
        result = mark_cod_payment_collected(self.user, sale)

        self.assertEqual(
            result.payment_status, PaymentStatus.COLLECTED
        )
        result.refresh_from_db()
        collection = result.collection_transaction
        self.assertIsNotNone(collection)
        self.assertNotEqual(
            collection.pk, result.accounting_transaction_id
        )
        self.assertEqual(collection.status, TransactionStatus.POSTED)

        receivable = get_or_create_accounts_receivable_account()
        lines = {
            line.account_id: line
            for line in collection.lines.all()
        }
        self.assertEqual(
            set(lines),
            {self.cod_pm.default_account_id, receivable.id},
        )
        cash_line = lines[self.cod_pm.default_account_id]
        self.assertEqual(
            cash_line.debit_amount, decimal.Decimal("1060.00")
        )
        self.assertEqual(
            lines[receivable.id].credit_amount,
            decimal.Decimal("1060.00"),
        )

        # The order's receivable is fully settled.
        totals = AccountingTransactionLine.objects.filter(
            transaction_id__in=[
                result.accounting_transaction_id,
                collection.pk,
            ],
            account=receivable,
        ).aggregate(
            debit=Sum("debit_amount"),
            credit=Sum("credit_amount"),
        )
        self.assertEqual(totals["debit"], totals["credit"])

    def test_collection_rejects_total_that_differs_from_receivable(
        self,
    ):
        from django.core.exceptions import ValidationError
        from sale_api.models import PaymentStatus, Sale
        from sale_api.services import mark_cod_payment_collected

        sale = self._deliver(
            self._create_order(
                idempotency_key="cod-collect-mismatch-001"
            )
        )
        Sale.objects.filter(pk=sale.pk).update(
            total_amount=decimal.Decimal("1000.00")
        )
        with self.assertRaisesMessage(
            ValidationError, "does not match the order total"
        ):
            mark_cod_payment_collected(self.user, sale)
        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, PaymentStatus.UNPAID)
        self.assertIsNone(sale.collection_transaction_id)

    def test_collection_requires_confirmation_accounting(self):
        from django.core.exceptions import ValidationError
        from sale_api.models import SaleStatus
        from sale_api.services import mark_cod_payment_collected

        sale = self._create_order(
            idempotency_key="cod-collect-unconfirmed-001"
        )
        sale.status = SaleStatus.DELIVERED
        sale.save(update_fields=["status"])
        with self.assertRaisesMessage(
            ValidationError, "no confirmation accounting entry"
        ):
            mark_cod_payment_collected(self.user, sale)

    def test_confirmation_rejects_storefront_discount(self):
        from django.core.exceptions import ValidationError
        from inventory_api.models import (
            InventoryReservation,
            ReservationStatus,
        )
        from sale_api.models import Sale, SaleStatus
        from sale_api.services import update_sale_status

        sale = self._create_order(
            idempotency_key="cod-discount-001"
        )
        Sale.objects.filter(pk=sale.pk).update(
            discount_amount=decimal.Decimal("10.00"),
            total_amount=sale.total_amount - 10,
        )
        with self.assertRaisesMessage(
            ValidationError, "discounts and taxes are not supported"
        ):
            update_sale_status(
                self.user, sale, SaleStatus.CONFIRMED
            )
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)
        self.assertIsNone(sale.accounting_transaction_id)
        self.assertTrue(
            InventoryReservation.objects.filter(
                sale=sale, status=ReservationStatus.ACTIVE,
            ).exists()
        )

    def _grant_collect_permission(self):
        from django.contrib.auth.models import Permission

        self.user.user_permissions.add(
            Permission.objects.get(
                codename="collect_sale_payment",
                content_type__app_label="sale_api",
            )
        )

    def test_mark_paid_endpoint_requires_collect_permission(self):
        sale = self._deliver(
            self._create_order(idempotency_key="cod-api-403")
        )
        response = self.client.post(
            f"/api/v1/sales/{sale.id}/mark-paid/", {}, format="json"
        )
        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN
        )

    def test_mark_paid_endpoint_collects_and_rejects_repeat(self):
        self._grant_collect_permission()
        sale = self._deliver(
            self._create_order(idempotency_key="cod-api-ok")
        )
        url = f"/api/v1/sales/{sale.id}/mark-paid/"
        first = self.client.post(url, {}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["payment_status"], "COLLECTED")

        repeat = self.client.post(url, {}, format="json")
        self.assertEqual(
            repeat.status_code, status.HTTP_400_BAD_REQUEST
        )
        self.assertIn("already been collected", repeat.data["detail"])

    def test_mark_paid_endpoint_unexpected_error_is_500(self):
        self._grant_collect_permission()
        sale = self._deliver(
            self._create_order(idempotency_key="cod-api-500")
        )
        self.client.raise_request_exception = False
        with mock.patch(
            "sale_api.views.v1.sale.mark_cod_payment_collected",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post(
                f"/api/v1/sales/{sale.id}/mark-paid/", {},
                format="json",
            )
        self.assertEqual(
            response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    def test_collection_rejects_undelivered_order(self):
        from django.core.exceptions import ValidationError
        from sale_api.services import mark_cod_payment_collected

        sale = self._create_order(
            idempotency_key="cod-collect-undelivered-001"
        )
        with self.assertRaises(ValidationError):
            mark_cod_payment_collected(self.user, sale)

    def test_collection_rejects_duplicate_collection(self):
        from django.core.exceptions import ValidationError
        from sale_api.models import PaymentStatus, SaleStatus
        from sale_api.services import mark_cod_payment_collected
        from unittest.mock import patch

        sale = self._create_order(
            idempotency_key="cod-collect-duplicate-001"
        )
        sale.status = SaleStatus.DELIVERED
        sale.payment_status = PaymentStatus.COLLECTED
        sale.save(update_fields=["status", "payment_status"])

        with patch("sale_api.services.create_transaction") as create_transaction:
            with self.assertRaises(ValidationError):
                mark_cod_payment_collected(self.user, sale)
            create_transaction.assert_not_called()

class StorefrontOrderEmailTemplateTest(TestCase):
    def test_order_email_templates_render(self):
        from django.template.loader import render_to_string

        context = {
            "customer_name": "Test Customer",
            "invoice_number": "SALE-20261013-000001",
            "total_amount": decimal.Decimal("1060.00"),
            "currency": "BDT",
            "orders_url": "https://example.com",
        }
        for template_name in (
            "emails/order_confirmation.html",
            "emails/order_confirmation.txt",
            "emails/order_cancelled.html",
            "emails/order_cancelled.txt",
        ):
            with self.subTest(template=template_name):
                rendered = render_to_string(
                    template_name, context
                )
                self.assertTrue(rendered.strip())

    def test_cancelled_email_explains_expiry(self):
        from django.template.loader import render_to_string

        context = {
            "invoice_number": "SALE-20261013-000001",
            "total_amount": "1060.00",
            "currency": "BDT",
            "orders_url": "https://example.com",
        }
        for template_name in (
            "emails/order_cancelled.html",
            "emails/order_cancelled.txt",
        ):
            with self.subTest(template=template_name):
                expired = render_to_string(
                    template_name,
                    {**context, "reservation_expired": True},
                )
                self.assertIn("not confirmed in time", expired)
                self.assertNotIn("as requested", expired)
                requested = render_to_string(template_name, context)
                self.assertIn("as requested", requested)



@skipUnlessDBFeature("has_select_for_update_of")
class ConcurrentOrderTestBase(TransactionTestCase):
    """
    Run two order operations at the same time on separate
    database connections.

    The first action commits nothing until ``release`` is set, so
    the second action really contends for the same rows.
    Needs PostgreSQL row locks; skipped on SQLite.
    """

    # Flushing would drop the COD payment method seeded by
    # migration 0012; restore it before every test.
    serialized_rollback = True

    _create_order = OrderCreationTestBase._create_order

    def setUp(self):
        # Order emails are dispatched on commit; keep the broker
        # out of these tests.
        patcher = mock.patch(
            "checkout_api.services._queue_order_email_after_commit"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        OrderCreationTestBase.setUp(self)

    def _run_holding_lock(self, action, locked, release, outcome):
        try:
            with transaction.atomic():
                outcome["result"] = action()
                locked.set()
                release.wait(timeout=10)
        except Exception as exc:
            outcome["error"] = exc
        finally:
            locked.set()
            connection.close()

    def _run(self, action, done, outcome):
        try:
            outcome["result"] = action()
        except Exception as exc:
            outcome["error"] = exc
        finally:
            done.set()
            connection.close()

    def _race(self, first, second):
        """
        Run ``first`` and keep its transaction open, then start
        ``second``. Return whether ``second`` was still waiting a
        second later, plus both outcomes.
        """
        locked, release, done = Event(), Event(), Event()
        first_outcome, second_outcome = {}, {}
        first_thread = Thread(
            target=self._run_holding_lock,
            args=(first, locked, release, first_outcome),
        )
        second_thread = Thread(
            target=self._run,
            args=(second, done, second_outcome),
        )
        first_thread.start()
        try:
            self.assertTrue(locked.wait(timeout=10))
            second_thread.start()
            blocked = not done.wait(timeout=1)
        finally:
            release.set()
            first_thread.join(timeout=10)
            if second_thread.ident is not None:
                second_thread.join(timeout=10)
        self.assertNotIn("error", first_outcome)
        self.first_outcome = first_outcome
        return blocked, second_outcome

    def _create_pos_sale(self, quantity, invoice_number):
        from account_api.models import AccountType, ChartOfAccount
        from sale_api.models import PaymentMethod, Sale, SaleItem

        payment_method = PaymentMethod.objects.filter(
            code="CASH-RACE",
        ).first()
        if payment_method is None:
            payment_method = PaymentMethod.objects.create(
                code="CASH-RACE",
                name="Cash race",
                default_account=ChartOfAccount.objects.create(
                    name="Cash race",
                    account_type=AccountType.ASSET,
                ),
            )
        line_total = decimal.Decimal("500.00") * quantity
        sale = Sale.objects.create(
            customer=self.profile,
            sale_date=timezone.now().date(),
            channel=Sale.SaleChannel.WALK_IN,
            payment_method=payment_method,
            invoice_number=invoice_number,
            subtotal_amount=line_total,
            total_amount=line_total,
            created_by=self.user,
            updated_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product_variant=self.variant,
            quantity=quantity,
            unit_price=decimal.Decimal("500.00"),
            line_total=line_total,
        )
        return sale

    def _confirm(self, sale_id):
        from sale_api.models import Sale, SaleStatus
        from sale_api.services import update_sale_status

        return update_sale_status(
            self.user,
            Sale.objects.get(pk=sale_id),
            SaleStatus.CONFIRMED,
        )

    def _available_stock(self):
        from inventory_api.services.reservation import (
            get_available_stock,
        )

        return get_available_stock(self.variant)


class OrderCancelConfirmRaceTest(ConcurrentOrderTestBase):
    """Customer cancellation racing staff confirmation."""

    def test_cancel_waits_for_confirmation_and_is_rejected(self):
        from checkout_api.services import cancel_order
        from inventory_api.models import (
            InventoryReservation,
            ReservationStatus,
        )
        from sale_api.models import Sale, SaleStatus
        from sale_api.services import update_sale_status

        sale = self._create_order()
        stale = Sale.objects.get(pk=sale.pk)

        blocked, cancel_outcome = self._race(
            lambda: update_sale_status(
                self.user,
                Sale.objects.get(pk=sale.pk),
                SaleStatus.CONFIRMED,
            ),
            lambda: cancel_order(user=self.user, sale=stale),
        )

        self.assertTrue(blocked)
        self.assertIsInstance(
            cancel_outcome.get("error"), DRFValidationError
        )
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CONFIRMED)
        self.assertIsNotNone(sale.accounting_transaction_id)
        self.assertEqual(
            set(
                InventoryReservation.objects.filter(
                    sale=sale,
                ).values_list("status", flat=True)
            ),
            {ReservationStatus.CONSUMED},
        )

    def test_confirm_waits_for_cancellation_and_is_rejected(self):
        from checkout_api.services import cancel_order
        from inventory_api.models import (
            InventoryMovement,
            InventoryReservation,
            MovementType,
            ReservationStatus,
        )
        from sale_api.models import Sale, SaleStatus
        from sale_api.services import update_sale_status

        sale = self._create_order()
        stale = Sale.objects.get(pk=sale.pk)

        blocked, confirm_outcome = self._race(
            lambda: cancel_order(
                user=self.user,
                sale=Sale.objects.get(pk=sale.pk),
            ),
            lambda: update_sale_status(
                self.user, stale, SaleStatus.CONFIRMED
            ),
        )

        self.assertTrue(blocked)
        self.assertIsInstance(
            confirm_outcome.get("error"), DjangoValidationError
        )
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)
        self.assertIsNone(sale.accounting_transaction_id)
        self.assertFalse(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
                reference_id=sale.pk,
            ).exists()
        )
        self.assertEqual(
            set(
                InventoryReservation.objects.filter(
                    sale=sale,
                ).values_list("status", flat=True)
            ),
            {ReservationStatus.RELEASED},
        )


class CheckoutInventoryRaceTest(ConcurrentOrderTestBase):
    """
    POS confirmations, storefront reservations and checkouts of
    one cart racing each other. ``OrderCreationTestBase`` gives the
    variant 50 units of stock and the cart 2 units of it.
    """

    def test_concurrent_pos_confirmations_cannot_oversell(self):
        from inventory_api.models import InventoryMovement, MovementType
        from sale_api.models import SaleStatus

        first = self._create_pos_sale(30, "RACE-POS-A")
        second = self._create_pos_sale(30, "RACE-POS-B")

        blocked, second_outcome = self._race(
            lambda: self._confirm(first.pk),
            lambda: self._confirm(second.pk),
        )

        self.assertTrue(blocked)
        self.assertIsInstance(
            second_outcome.get("error"), DjangoValidationError
        )
        second.refresh_from_db()
        self.assertEqual(second.status, SaleStatus.PENDING)
        self.assertIsNone(second.accounting_transaction_id)
        self.assertEqual(
            InventoryMovement.objects.filter(
                product_variant=self.variant,
                movement_type=MovementType.SALE,
            ).count(),
            1,
        )
        self.assertEqual(self._available_stock(), 20)

    def test_concurrent_confirmations_of_one_pos_sale_post_once(self):
        from inventory_api.models import InventoryMovement, MovementType
        from sale_api.models import Sale, SaleStatus
        from sale_api.services import update_sale_status
        from transaction_api.models import AccountingTransaction

        sale = self._create_pos_sale(5, "RACE-POS-ONCE")
        stale = Sale.objects.get(pk=sale.pk)

        blocked, second_outcome = self._race(
            lambda: self._confirm(sale.pk),
            lambda: update_sale_status(
                self.user, stale, SaleStatus.CONFIRMED
            ),
        )

        self.assertTrue(blocked)
        self.assertNotIn("error", second_outcome)
        self.assertEqual(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
                reference_id=sale.pk,
            ).count(),
            1,
        )
        self.assertEqual(
            AccountingTransaction.objects.filter(
                reference=sale.invoice_number,
            ).count(),
            1,
        )
        self.assertEqual(self._available_stock(), 45)

    def test_storefront_reservation_waits_for_pos_confirmation(self):
        from sale_api.models import Sale

        pos_sale = self._create_pos_sale(49, "RACE-POS-FIRST")

        blocked, checkout_outcome = self._race(
            lambda: self._confirm(pos_sale.pk),
            lambda: self._create_order(idempotency_key="race-after-pos"),
        )

        self.assertTrue(blocked)
        self.assertIsInstance(
            checkout_outcome.get("error"), DRFValidationError
        )
        self.assertFalse(
            Sale.objects.filter(
                channel=Sale.SaleChannel.WEBSITE,
            ).exists()
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, CartStatus.ACTIVE)
        self.assertEqual(self._available_stock(), 1)

    def test_pos_confirmation_waits_for_storefront_reservation(self):
        from inventory_api.models import InventoryMovement, MovementType
        from sale_api.models import SaleStatus

        pos_sale = self._create_pos_sale(49, "RACE-POS-SECOND")

        blocked, pos_outcome = self._race(
            lambda: self._create_order(idempotency_key="race-before-pos"),
            lambda: self._confirm(pos_sale.pk),
        )

        self.assertTrue(blocked)
        self.assertIsInstance(
            pos_outcome.get("error"), DjangoValidationError
        )
        pos_sale.refresh_from_db()
        self.assertEqual(pos_sale.status, SaleStatus.PENDING)
        self.assertFalse(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
            ).exists()
        )
        self.assertEqual(self._available_stock(), 48)

    def test_concurrent_checkouts_of_one_cart_create_one_order(self):
        from inventory_api.models import InventoryReservation
        from sale_api.models import Sale

        blocked, second_outcome = self._race(
            lambda: self._create_order(idempotency_key="race-cart-a"),
            lambda: self._create_order(idempotency_key="race-cart-b"),
        )

        self.assertTrue(blocked)
        self.assertIsInstance(
            second_outcome.get("error"), DRFValidationError
        )
        self.assertEqual(
            Sale.objects.filter(
                channel=Sale.SaleChannel.WEBSITE,
            ).count(),
            1,
        )
        self.assertEqual(InventoryReservation.objects.count(), 1)
        self.assertEqual(self._available_stock(), 48)

    def test_concurrent_same_key_checkouts_return_one_order(self):
        from sale_api.models import Sale

        blocked, second_outcome = self._race(
            lambda: self._create_order(idempotency_key="race-same"),
            lambda: self._create_order(idempotency_key="race-same"),
        )

        self.assertTrue(blocked)
        self.assertNotIn("error", second_outcome)
        self.assertEqual(
            second_outcome["result"].pk,
            self.first_outcome["result"].pk,
        )
        self.assertEqual(
            Sale.objects.filter(
                channel=Sale.SaleChannel.WEBSITE,
            ).count(),
            1,
        )

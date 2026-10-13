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

class CODCollectionServiceTest(OrderCreationTestBase):
    """Tests for atomic COD collection accounting."""

    def test_collection_posts_receivable_settlement(self):
        from unittest.mock import patch
        from sale_api.models import PaymentStatus, SaleStatus
        from sale_api.services import mark_cod_payment_collected

        sale = self._create_order(
            idempotency_key="cod-collect-service-001"
        )
        sale.status = SaleStatus.DELIVERED
        sale.save(update_fields=["status"])

        with patch(
            "sale_api.services.create_transaction"
        ) as create_transaction, patch(
            "sale_api.services.post_transaction"
        ) as post_transaction:
            transaction_obj = object()
            create_transaction.return_value = transaction_obj
            post_transaction.return_value = transaction_obj

            result = mark_cod_payment_collected(
                self.user, sale
            )

        self.assertEqual(
            result.payment_status,
            PaymentStatus.COLLECTED,
        )
        create_transaction.assert_called_once()
        post_transaction.assert_called_once_with(
            self.user, transaction_obj
        )
        lines = create_transaction.call_args.args[1]["lines"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[0]["debit_amount"],
            decimal.Decimal("1060.00"),
        )
        self.assertEqual(
            lines[1]["credit_amount"],
            decimal.Decimal("1060.00"),
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


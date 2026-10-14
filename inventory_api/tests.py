# inventory_api/tests.py
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from user_api.models import User
from product_api.models import Product, ProductVariant
from category_api.models import Category
from sale_api.models import Sale, SaleStatus
from customer_api.models import CustomerProfile
from EcommerceBackend.core.choices import CartStatus

from inventory_api.models import (
    InventoryMovement,
    InventoryReservation,
    MovementType,
    ReservationStatus,
)
from inventory_api.services.reservation import (
    get_available_stock,
    reserve_stock,
    consume_reservations,
    release_reservations,
    expire_reservations,
)


class ReservationTestBase(TestCase):
    """Shared setup for reservation tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='invuser',
            email='inv@example.com',
            password='testpass123',
        )
        self.category = Category.objects.create(
            name='Test', slug='test-inv',
        )
        self.product = Product.objects.create(
            name='Widget',
            slug='widget-inv',
            current_selling_price=Decimal('100.00'),
            created_by=self.user,
            updated_by=self.user,
        )
        self.product.categories.add(self.category)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='WGT-001',
            name='Default',
        )
        self.variant2 = ProductVariant.objects.create(
            product=self.product,
            sku='WGT-002',
            name='Variant 2',
        )
        # Give 50 units of stock.
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=50,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant2,
            quantity=30,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        self.customer = (
            CustomerProfile.objects.create(
                user=self.user,
                customer_type='WEBSITE',
            )
        )
        self.sale = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now().date(),
            status=SaleStatus.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        self.future = (
            timezone.now() + timedelta(minutes=30)
        )


class AvailableStockTest(ReservationTestBase):
    """Tests for get_available_stock."""

    def test_stock_with_movements_only(self):
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_stock_excludes_inactive_movements(
        self,
    ):
        movement = (
            InventoryMovement.objects.create(
                product_variant=self.variant,
                quantity=-20,
                movement_type=MovementType.SALE,
                created_by=self.user,
                updated_by=self.user,
            )
        )
        self.assertEqual(
            get_available_stock(self.variant), 30
        )
        movement.is_active = False
        movement.save(update_fields=['is_active'])
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_stock_subtracts_active_reservations(
        self,
    ):
        InventoryReservation.objects.create(
            product_variant=self.variant,
            sale=self.sale,
            quantity=10,
            status=ReservationStatus.ACTIVE,
            expires_at=self.future,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(
            get_available_stock(self.variant), 40
        )

    def test_stock_ignores_expired_reservations(
        self,
    ):
        InventoryReservation.objects.create(
            product_variant=self.variant,
            sale=self.sale,
            quantity=10,
            status=ReservationStatus.ACTIVE,
            expires_at=(
                timezone.now() - timedelta(minutes=1)
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_stock_ignores_consumed_reservations(
        self,
    ):
        InventoryReservation.objects.create(
            product_variant=self.variant,
            sale=self.sale,
            quantity=10,
            status=ReservationStatus.CONSUMED,
            expires_at=self.future,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_stock_ignores_released_reservations(
        self,
    ):
        InventoryReservation.objects.create(
            product_variant=self.variant,
            sale=self.sale,
            quantity=10,
            status=ReservationStatus.RELEASED,
            expires_at=self.future,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_exclude_sale(self):
        """Excluding a sale ignores its own
        reservations."""
        InventoryReservation.objects.create(
            product_variant=self.variant,
            sale=self.sale,
            quantity=10,
            status=ReservationStatus.ACTIVE,
            expires_at=self.future,
            created_by=self.user,
            updated_by=self.user,
        )
        # Without exclude: 50 - 10 = 40
        self.assertEqual(
            get_available_stock(self.variant), 40
        )
        # With exclude: 50 - 0 = 50
        self.assertEqual(
            get_available_stock(
                self.variant,
                exclude_sale=self.sale,
            ),
            50,
        )

    def test_zero_movements(self):
        """Variant with no movements returns 0."""
        new_variant = (
            ProductVariant.objects.create(
                product=self.product,
                sku='EMPTY-001',
            )
        )
        self.assertEqual(
            get_available_stock(new_variant), 0
        )


class ReserveStockTest(ReservationTestBase):
    """Tests for reserve_stock."""

    def test_successful_reservation(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 5,
            }
        ]
        reservations = reserve_stock(
            self.sale, items, user=self.user
        )
        self.assertEqual(len(reservations), 1)
        self.assertEqual(
            reservations[0].quantity, 5
        )
        self.assertEqual(
            reservations[0].status,
            ReservationStatus.ACTIVE,
        )
        self.assertEqual(
            reservations[0].sale_id, self.sale.pk
        )

    def test_multiple_variants(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 5,
            },
            {
                'product_variant': self.variant2,
                'quantity': 3,
            },
        ]
        reservations = reserve_stock(
            self.sale, items, user=self.user
        )
        self.assertEqual(len(reservations), 2)

    def test_insufficient_stock(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 100,
            }
        ]
        with self.assertRaises(Exception):
            reserve_stock(
                self.sale, items, user=self.user
            )

    def test_zero_quantity_rejected(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 0,
            }
        ]
        with self.assertRaises(Exception):
            reserve_stock(
                self.sale, items, user=self.user
            )

    def test_reservation_reduces_available(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 20,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        self.assertEqual(
            get_available_stock(self.variant), 30
        )

    def test_multiple_reservations_accumulate(
        self,
    ):
        sale2 = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now().date(),
            status=SaleStatus.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        items1 = [
            {
                'product_variant': self.variant,
                'quantity': 20,
            }
        ]
        items2 = [
            {
                'product_variant': self.variant,
                'quantity': 15,
            }
        ]
        reserve_stock(
            self.sale, items1, user=self.user
        )
        reserve_stock(
            sale2, items2, user=self.user
        )
        # 50 - 20 - 15 = 15
        self.assertEqual(
            get_available_stock(self.variant), 15
        )

    def test_reservation_blocked_by_other_sale(
        self,
    ):
        """Two sales compete for same stock."""
        sale2 = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now().date(),
            status=SaleStatus.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        items1 = [
            {
                'product_variant': self.variant,
                'quantity': 40,
            }
        ]
        items2 = [
            {
                'product_variant': self.variant,
                'quantity': 20,
            }
        ]
        reserve_stock(
            self.sale, items1, user=self.user
        )
        # 50 - 40 = 10 available, need 20.
        with self.assertRaises(Exception):
            reserve_stock(
                sale2, items2, user=self.user
            )


class ConsumeReservationsTest(
    ReservationTestBase
):
    """Tests for consume_reservations."""

    def test_consume_creates_movements(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        consumed = consume_reservations(
            self.sale, user=self.user
        )
        self.assertEqual(len(consumed), 1)
        self.assertEqual(
            consumed[0].status,
            ReservationStatus.CONSUMED,
        )
        # Movement created.
        movement = (
            InventoryMovement.objects.filter(
                product_variant=self.variant,
                movement_type=MovementType.SALE,
                reference_id=self.sale.pk,
            ).first()
        )
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, -10)

    def test_consume_reduces_stock(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        consume_reservations(
            self.sale, user=self.user
        )
        # Stock: 50 movements - 10 consumed = 40
        self.assertEqual(
            get_available_stock(self.variant), 40
        )

    def test_consume_rejects_no_reservations(self):
        with self.assertRaises(Exception):
            consume_reservations(
                self.sale, user=self.user
            )

    def test_consume_rejects_already_consumed(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        consume_reservations(
            self.sale, user=self.user
        )
        with self.assertRaises(Exception):
            consume_reservations(
                self.sale, user=self.user
            )

    def test_consume_rejects_expired(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reservations = reserve_stock(
            self.sale, items, user=self.user
        )
        # Expire the reservation.
        reservations[0].expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        reservations[0].save(
            update_fields=['expires_at']
        )
        with self.assertRaises(Exception):
            consume_reservations(
                self.sale, user=self.user
            )

    def test_consume_excludes_own_reservations_in_stock_check(
        self,
    ):
        """During confirmation, the stock check
        excludes the current order's reservations."""
        items = [
            {
                'product_variant': self.variant,
                'quantity': 45,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        # Available without exclude: 50 - 45 = 5
        # Available with exclude: 50
        # So consuming 45 should succeed.
        consumed = consume_reservations(
            self.sale, user=self.user
        )
        self.assertEqual(len(consumed), 1)


class ReleaseReservationsTest(
    ReservationTestBase
):
    """Tests for release_reservations."""

    def test_release(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        count = release_reservations(
            self.sale, user=self.user
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_release_idempotent(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        release_reservations(
            self.sale, user=self.user
        )
        count = release_reservations(
            self.sale, user=self.user
        )
        self.assertEqual(count, 0)

    def test_release_no_reservations(self):
        count = release_reservations(
            self.sale, user=self.user
        )
        self.assertEqual(count, 0)


class ExpireReservationsTest(
    ReservationTestBase
):
    """Tests for expire_reservations."""

    def test_expire_stale(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reservations = reserve_stock(
            self.sale, items, user=self.user
        )
        reservations[0].expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        reservations[0].save(
            update_fields=['expires_at']
        )
        total = expire_reservations()
        self.assertEqual(total, 1)
        reservations[0].refresh_from_db()
        self.assertEqual(
            reservations[0].status,
            ReservationStatus.RELEASED,
        )
        self.assertEqual(
            get_available_stock(self.variant), 50
        )

    def test_expire_ignores_active(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reserve_stock(
            self.sale, items, user=self.user
        )
        total = expire_reservations()
        self.assertEqual(total, 0)

    def test_expire_idempotent(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reservations = reserve_stock(
            self.sale, items, user=self.user
        )
        reservations[0].expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        reservations[0].save(
            update_fields=['expires_at']
        )
        expire_reservations()
        total = expire_reservations()
        self.assertEqual(total, 0)

    def test_expire_ignores_consumed(self):
        items = [
            {
                'product_variant': self.variant,
                'quantity': 10,
            }
        ]
        reservations = reserve_stock(
            self.sale, items, user=self.user
        )
        reservations[0].status = (
            ReservationStatus.CONSUMED
        )
        reservations[0].save(
            update_fields=['status']
        )
        total = expire_reservations()
        self.assertEqual(total, 0)

    def test_expire_batched(self):
        """Expire processes in batches."""
        sale2 = Sale.objects.create(
            customer=self.customer,
            sale_date=timezone.now().date(),
            status=SaleStatus.PENDING,
            created_by=self.user,
            updated_by=self.user,
        )
        items = [
            {
                'product_variant': self.variant,
                'quantity': 1,
            }
        ]
        r1 = reserve_stock(
            self.sale, items, user=self.user
        )
        r2 = reserve_stock(
            sale2, items, user=self.user
        )
        # Expire both.
        past = (
            timezone.now() - timedelta(minutes=1)
        )
        r1[0].expires_at = past
        r1[0].save(update_fields=['expires_at'])
        r2[0].expires_at = past
        r2[0].save(update_fields=['expires_at'])

        total = expire_reservations(batch_size=1)
        self.assertEqual(total, 2)
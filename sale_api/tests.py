from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from account_api.models import AccountType, ChartOfAccount
from customer_api.models import CustomerProfile
from product_api.models import Product, ProductVariant
from inventory_api.models import InventoryMovement, MovementType, ReferenceType
from sale_api.models import PaymentMethod, Sale, SaleItem, SaleStatus
from sale_api.services import create_sale, update_sale_status
from transaction_api.models import TransactionStatus, TransactionType
from user_api.models import User


class SaleInvoiceGenerationTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff-1',
            email='staff1@example.com',
            password='test-pass-123',
            role='STAFF'
        )
        self.customer_user = User.objects.create_user(
            username='customer-1',
            email='customer1@example.com',
            password='test-pass-123',
            role='CUSTOMER'
        )
        self.customer = CustomerProfile.objects.create(user=self.customer_user)
        self.product = Product.objects.create(
            name='Demo Product',
            current_selling_price=Decimal('655.00')
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='SKU-001'
        )
        self.cash_account = ChartOfAccount.objects.create(
            name='Cash',
            account_type=AccountType.ASSET,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )

    def _payload(self, invoice_number=None, account=None):
        return {
            'customer': self.customer,
            'account': account or self.cash_account,
            'sale_date': date(2026, 3, 6),
            'invoice_number': invoice_number,
            'discount_amount': Decimal('0.00'),
            'tax_amount': Decimal('32.75'),
            'notes': None,
            'items': [
                {
                    'product_variant': self.variant,
                    'quantity': 1,
                    'unit_price': Decimal('655.00'),
                    'line_total': Decimal('655.00'),
                }
            ]
        }

    def test_create_sale_generates_invoice_number_when_missing(self):
        sale = create_sale(self.staff_user, self._payload(invoice_number=None))

        self.assertIsNotNone(sale.invoice_number)
        self.assertTrue(sale.invoice_number.startswith('SALE-20260306-'))
        self.assertEqual(sale.channel, Sale.SaleChannel.WALK_IN)

    def test_create_sale_generates_invoice_number_when_blank(self):
        sale = create_sale(self.staff_user, self._payload(invoice_number='  '))

        self.assertIsNotNone(sale.invoice_number)
        self.assertTrue(sale.invoice_number.startswith('SALE-20260306-'))

    def test_create_sale_keeps_provided_invoice_number(self):
        sale = create_sale(
            self.staff_user,
            self._payload(invoice_number='MANUAL-INV-1001')
        )

        self.assertEqual(sale.invoice_number, 'MANUAL-INV-1001')

    def test_create_sale_keeps_provided_channel(self):
        payload = self._payload(invoice_number=None)
        payload['channel'] = Sale.SaleChannel.FACEBOOK

        sale = create_sale(self.staff_user, payload)

        self.assertEqual(sale.channel, Sale.SaleChannel.FACEBOOK)
        self.assertEqual(sale.status, SaleStatus.PENDING)

    def test_sale_channel_choices_contract(self):
        self.assertEqual(
            [value for value, _ in Sale.SaleChannel.choices],
            ['Walk-in', 'Facebook', 'Phone', 'Website', 'Instagram', 'WhatsApp']
        )

    def test_sale_status_choices_contract(self):
        self.assertEqual(
            [value for value, _ in SaleStatus.choices],
            [
                'PENDING',
                'CONFIRMED',
                'PROCESSING',
                'PACKAGED',
                'SHIPPED',
                'OUT_OF_DELIVERY',
                'DELIVERED',
                'RETURNED',
                'CANCELLED',
            ]
        )


class SaleStatusTransitionTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff-2',
            email='staff2@example.com',
            password='test-pass-123',
            role='STAFF'
        )
        self.customer_user = User.objects.create_user(
            username='customer-2',
            email='customer2@example.com',
            password='test-pass-123',
            role='CUSTOMER'
        )
        self.customer = CustomerProfile.objects.create(user=self.customer_user)
        self.product = Product.objects.create(
            name='Transition Product',
            current_selling_price=Decimal('500.00')
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='SKU-STATUS-001'
        )
        self.cash_account = ChartOfAccount.objects.create(
            name='Cash Status',
            account_type=AccountType.ASSET,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=10,
            movement_type=MovementType.OPENING,
            reference_type=ReferenceType.MANUAL,
            created_by=self.staff_user
        )
        self.sale = create_sale(self.staff_user, {
            'customer': self.customer,
            'account': self.cash_account,
            'sale_date': date(2026, 3, 6),
            'invoice_number': None,
            'discount_amount': Decimal('0.00'),
            'tax_amount': Decimal('0.00'),
            'notes': None,
            'items': [
                {
                    'product_variant': self.variant,
                    'quantity': 2,
                    'unit_price': Decimal('500.00'),
                    'line_total': Decimal('1000.00'),
                }
            ]
        })

    def test_confirm_and_return_adjust_inventory(self):
        sale = update_sale_status(
            self.staff_user,
            self.sale,
            SaleStatus.CONFIRMED
        )
        self.assertEqual(sale.status, SaleStatus.CONFIRMED)
        self.assertIsNotNone(sale.accounting_transaction)
        self.assertEqual(
            sale.accounting_transaction.transaction_type,
            TransactionType.SALE,
        )
        self.assertEqual(
            sale.accounting_transaction.status,
            TransactionStatus.POSTED,
        )

        stock_after_confirm = InventoryMovement.objects.filter(
            product_variant=self.variant
        ).values_list('quantity', flat=True)
        self.assertEqual(sum(stock_after_confirm), 8)

        for next_status in [
            SaleStatus.PROCESSING,
            SaleStatus.PACKAGED,
            SaleStatus.SHIPPED,
            SaleStatus.OUT_OF_DELIVERY,
            SaleStatus.DELIVERED,
            SaleStatus.RETURNED,
        ]:
            sale = update_sale_status(self.staff_user, sale, next_status)

        self.assertEqual(sale.status, SaleStatus.RETURNED)
        self.assertIsNotNone(sale.return_transaction)
        self.assertEqual(
            sale.return_transaction.transaction_type,
            TransactionType.ADJUSTMENT,
        )
        final_stock = InventoryMovement.objects.filter(
            product_variant=self.variant
        ).values_list('quantity', flat=True)
        self.assertEqual(sum(final_stock), 10)

    def test_confirm_requires_account(self):
        sale_without_account = create_sale(self.staff_user, {
            'customer': self.customer,
            'sale_date': date(2026, 3, 6),
            'invoice_number': None,
            'discount_amount': Decimal('0.00'),
            'tax_amount': Decimal('0.00'),
            'notes': None,
            'items': [
                {
                    'product_variant': self.variant,
                    'quantity': 1,
                    'unit_price': Decimal('500.00'),
                    'line_total': Decimal('500.00'),
                }
            ]
        })

        with self.assertRaisesMessage(
            Exception,
            'An account must be selected before confirmation.'
        ):
            update_sale_status(
                self.staff_user,
                sale_without_account,
                SaleStatus.CONFIRMED
            )

    def test_rejects_skipping_statuses(self):
        with self.assertRaisesMessage(
            Exception,
            'Cannot change sale status from PENDING to SHIPPED.'
        ):
            update_sale_status(
                self.staff_user,
                self.sale,
                SaleStatus.SHIPPED
            )


class SaleStatusApiTests(APITestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff-3',
            email='staff3@example.com',
            password='test-pass-123',
            role='STAFF'
        )
        self.customer_user = User.objects.create_user(
            username='customer-3',
            email='customer3@example.com',
            password='test-pass-123',
            role='CUSTOMER'
        )
        self.customer = CustomerProfile.objects.create(user=self.customer_user)
        self.product = Product.objects.create(
            name='API Product',
            current_selling_price=Decimal('450.00')
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='SKU-API-001'
        )
        self.cash_account = ChartOfAccount.objects.create(
            name='Cash API',
            account_type=AccountType.ASSET,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        self.bank_account = ChartOfAccount.objects.create(
            name='Bank API',
            account_type=AccountType.ASSET,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        self.cash_payment_method = PaymentMethod.objects.create(
            code='CASH',
            name='Cash',
            default_account=self.cash_account,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=5,
            movement_type=MovementType.OPENING,
            reference_type=ReferenceType.MANUAL,
            created_by=self.staff_user
        )
        self.sale = create_sale(self.staff_user, {
            'customer': self.customer,
            'account': self.cash_account,
            'sale_date': date(2026, 3, 6),
            'invoice_number': None,
            'discount_amount': Decimal('0.00'),
            'tax_amount': Decimal('0.00'),
            'notes': None,
            'items': [
                {
                    'product_variant': self.variant,
                    'quantity': 1,
                    'unit_price': Decimal('450.00'),
                    'line_total': Decimal('450.00'),
                }
            ]
        })
        self.client.force_authenticate(user=self.staff_user)

    def test_statuses_endpoint_returns_frontend_contract(self):
        response = self.client.get('/api/v1/sales/statuses/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['default'], SaleStatus.PENDING)
        self.assertEqual(
            response.data['transitions']['PENDING'],
            [SaleStatus.CONFIRMED, SaleStatus.CANCELLED]
        )

    def test_update_status_endpoint_updates_sale(self):
        response = self.client.post(
            f'/api/v1/sales/{self.sale.id}/update-status/',
            {'status': SaleStatus.CONFIRMED},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], SaleStatus.CONFIRMED)
        self.assertEqual(response.data['account']['id'], self.cash_account.id)
        self.assertIsNotNone(response.data['accounting_transaction'])
        self.assertIsNone(response.data['payment_method'])
        self.assertEqual(
            response.data['allowed_next_statuses'],
            [
                {'value': SaleStatus.PROCESSING, 'label': 'Processing'},
            ]
        )

    def test_patch_sale_can_update_status_without_invoice_number(self):
        response = self.client.patch(
            f'/api/v1/sales/{self.sale.id}/',
            {'status': SaleStatus.CONFIRMED},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], SaleStatus.CONFIRMED)

    def test_update_status_endpoint_accepts_account_for_confirm(self):
        sale_without_account = create_sale(self.staff_user, {
            'customer': self.customer,
            'sale_date': date(2026, 3, 6),
            'invoice_number': None,
            'discount_amount': Decimal('0.00'),
            'tax_amount': Decimal('0.00'),
            'notes': None,
            'items': [
                {
                    'product_variant': self.variant,
                    'quantity': 1,
                    'unit_price': Decimal('450.00'),
                    'line_total': Decimal('450.00'),
                }
            ]
        })

        response = self.client.post(
            f'/api/v1/sales/{sale_without_account.id}/update-status/',
            {'status': SaleStatus.CONFIRMED, 'account_id': self.cash_account.id},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], SaleStatus.CONFIRMED)
        self.assertEqual(response.data['account']['id'], self.cash_account.id)
        self.assertIsNotNone(response.data['accounting_transaction'])

    def test_create_sale_resolves_account_from_payment_method(self):
        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.id,
                'payment_method_id': self.cash_payment_method.id,
                'sale_date': '2026-03-06',
                'discount_amount': '0.00',
                'tax_amount': '0.00',
                'notes': None,
                'items': [
                    {
                        'product_variant_id': self.variant.id,
                        'quantity': 1,
                        'unit_price': '450.00',
                    }
                ],
            },
            format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['payment_method']['id'],
            self.cash_payment_method.id,
        )
        self.assertEqual(response.data['account']['id'], self.cash_account.id)

    def test_create_sale_rejects_account_override_when_not_allowed(self):
        response = self.client.post(
            '/api/v1/sales/',
            {
                'customer': self.customer.id,
                'payment_method_id': self.cash_payment_method.id,
                'account_id': self.bank_account.id,
                'sale_date': '2026-03-06',
                'discount_amount': '0.00',
                'tax_amount': '0.00',
                'notes': None,
                'items': [
                    {
                        'product_variant_id': self.variant.id,
                        'quantity': 1,
                        'unit_price': '450.00',
                    }
                ],
            },
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            'selected payment method',
            response.data['detail'],
        )

    def test_patch_sale_rejects_invoice_number_updates(self):
        response = self.client.patch(
            f'/api/v1/sales/{self.sale.id}/',
            {'invoice_number': 'NEW-INV-001'},
            format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['invoice_number'],
            ['This field is not allowed.']
        )

    def test_payment_method_list_endpoint_returns_default_account_mapping(self):
        response = self.client.get('/api/v1/payment-methods/')

        self.assertEqual(response.status_code, 200)
        result = next(
            item
            for item in response.data['results']
            if item['id'] == self.cash_payment_method.id
        )
        self.assertEqual(result['code'], 'CASH')
        self.assertEqual(result['default_account_id'], self.cash_account.id)
        self.assertEqual(result['default_account']['id'], self.cash_account.id)

    def test_update_status_validation_error_still_returns_400(self):
        response = self.client.post(
            f'/api/v1/sales/{self.sale.id}/update-status/',
            {'status': SaleStatus.SHIPPED},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Cannot change sale status', response.data['detail'])

    def test_unexpected_errors_are_not_reported_as_400(self):
        from unittest.mock import patch

        self.client.raise_request_exception = False
        cases = [
            (
                'sale_api.views.v1.sale.update_sale_status',
                'post',
                f'/api/v1/sales/{self.sale.id}/update-status/',
                {'status': SaleStatus.CONFIRMED},
            ),
            (
                'sale_api.views.v1.sale.update_sale',
                'patch',
                f'/api/v1/sales/{self.sale.id}/',
                {'notes': 'changed'},
            ),
            (
                'sale_api.views.v1.sale.create_sale',
                'post',
                '/api/v1/sales/',
                {
                    'customer': self.customer.id,
                    'sale_date': '2026-03-06',
                    'items': [{
                        'product_variant_id': self.variant.id,
                        'quantity': 1,
                        'unit_price': '450.00',
                    }],
                },
            ),
        ]
        for target, method, url, payload in cases:
            with self.subTest(target=target), patch(
                target, side_effect=RuntimeError('boom')
            ):
                response = getattr(self.client, method)(
                    url, payload, format='json'
                )
                self.assertEqual(response.status_code, 500)


class AccountProvisioningTests(TestCase):
    """Tests for account provisioning functions."""

    def test_shipping_revenue_account_created(self):
        from sale_api.services import (
            get_or_create_shipping_revenue_account,
        )
        account = (
            get_or_create_shipping_revenue_account()
        )
        self.assertEqual(
            account.name, 'Shipping Revenue'
        )
        self.assertEqual(
            account.account_type, AccountType.REVENUE
        )
        self.assertTrue(account.is_active)

    def test_shipping_revenue_reuses_existing(self):
        from sale_api.services import (
            get_or_create_shipping_revenue_account,
        )
        first = (
            get_or_create_shipping_revenue_account()
        )
        second = (
            get_or_create_shipping_revenue_account()
        )
        self.assertEqual(first.id, second.id)

    def test_shipping_revenue_inactive_raises(self):
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_shipping_revenue_account,
        )
        account = (
            get_or_create_shipping_revenue_account()
        )
        account.is_active = False
        account.save(update_fields=['is_active'])
        with self.assertRaises(ValidationError):
            get_or_create_shipping_revenue_account()

    def test_accounts_receivable_created(self):
        from sale_api.services import (
            get_or_create_accounts_receivable_account,
        )
        account = (
            get_or_create_accounts_receivable_account()
        )
        self.assertEqual(
            account.name, 'Accounts Receivable'
        )
        self.assertEqual(
            account.account_type, AccountType.ASSET
        )
        self.assertTrue(account.is_active)

    def test_accounts_receivable_reuses_existing(
        self,
    ):
        from sale_api.services import (
            get_or_create_accounts_receivable_account,
        )
        first = (
            get_or_create_accounts_receivable_account()
        )
        second = (
            get_or_create_accounts_receivable_account()
        )
        self.assertEqual(first.id, second.id)

    def test_sales_revenue_still_works(self):
        from sale_api.services import (
            get_or_create_sales_revenue_account,
        )
        account = (
            get_or_create_sales_revenue_account()
        )
        self.assertEqual(
            account.name, 'Sales Revenue'
        )
        self.assertEqual(
            account.account_type, AccountType.REVENUE
        )

    def _delete_cod_pm(self):
        """Remove the COD PM created by the data
        migration so tests can set up their own."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sale_api_paymentmethod "
                "WHERE code = 'COD'"
            )

    def test_cod_payment_method_valid(self):
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        cash = ChartOfAccount.objects.create(
            name='Cash - COD Test',
            account_type=AccountType.ASSET,
        )
        pm = PaymentMethod.objects.create(
            code='COD',
            name='Cash on Delivery',
            default_account=cash,
            allow_account_override=False,
        )
        result = get_or_create_cod_payment_method()
        self.assertEqual(result.id, pm.id)
        self.assertEqual(
            result.default_account.id, cash.id
        )
        self.assertFalse(
            result.allow_account_override
        )

    def test_cod_payment_method_missing(self):
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        with self.assertRaises(ValidationError):
            get_or_create_cod_payment_method()

    def test_cod_payment_method_no_account(self):
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        PaymentMethod.objects.create(
            code='COD',
            name='Cash on Delivery',
            default_account=None,
        )
        with self.assertRaises(ValidationError):
            get_or_create_cod_payment_method()

    def test_cod_payment_method_inactive_account(
        self,
    ):
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        cash = ChartOfAccount.objects.create(
            name='Cash Inactive',
            account_type=AccountType.ASSET,
            is_active=False,
        )
        PaymentMethod.objects.create(
            code='COD',
            name='Cash on Delivery',
            default_account=cash,
        )
        with self.assertRaises(ValidationError):
            get_or_create_cod_payment_method()

    def test_cod_payment_method_wrong_type(self):
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        rev = ChartOfAccount.objects.create(
            name='Not Cash',
            account_type=AccountType.REVENUE,
        )
        PaymentMethod.objects.create(
            code='COD',
            name='Cash on Delivery',
            default_account=rev,
        )
        with self.assertRaises(ValidationError):
            get_or_create_cod_payment_method()

    def test_pos_payment_method_unchanged(self):
        """Existing POS CASH method must not be
        affected by COD provisioning."""
        pos_cash = ChartOfAccount.objects.create(
            name='Cash',
            account_type=AccountType.ASSET,
        )
        pos_pm = PaymentMethod.objects.create(
            code='CASH',
            name='Cash',
            default_account=pos_cash,
        )
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        # COD PM already exists from data migration
        cod = get_or_create_cod_payment_method()
        pos_pm.refresh_from_db()
        self.assertNotEqual(cod.id, pos_pm.id)
        self.assertEqual(
            pos_pm.default_account.id, pos_cash.id
        )

    def test_cod_different_account_preserved(self):
        """If COD PM references a different active
        ASSET account, the runtime function must
        accept it without overwriting."""
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        alt_cash = ChartOfAccount.objects.create(
            name='Cash - Alternate',
            account_type=AccountType.ASSET,
        )
        pm = PaymentMethod.objects.create(
            code='COD',
            name='Cash on Delivery',
            default_account=alt_cash,
            allow_account_override=False,
        )
        result = get_or_create_cod_payment_method()
        self.assertEqual(result.id, pm.id)
        self.assertEqual(
            result.default_account.id, alt_cash.id
        )

    def test_cod_deleted_account_raises(self):
        """If COD PM references a soft-deleted
        account, the runtime function must raise."""
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_cod_payment_method,
        )
        self._delete_cod_pm()
        cash = ChartOfAccount.objects.create(
            name='Cash Deleted',
            account_type=AccountType.ASSET,
        )
        cash.soft_delete()
        PaymentMethod.objects.create(
            code='COD',
            name='Cash on Delivery',
            default_account=cash,
        )
        with self.assertRaises(ValidationError):
            get_or_create_cod_payment_method()

    def test_accounts_receivable_inactive_raises(
        self,
    ):
        from django.core.exceptions import (
            ValidationError,
        )
        from sale_api.services import (
            get_or_create_accounts_receivable_account,
        )
        account = (
            get_or_create_accounts_receivable_account()
        )
        account.is_active = False
        account.save(update_fields=['is_active'])
        with self.assertRaises(ValidationError):
            get_or_create_accounts_receivable_account()


class StorefrontConfirmationTest(TestCase):
    """Tests for storefront (WEBSITE channel)
    order confirmation with reservations."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from inventory_api.models import (
            InventoryReservation,
            ReservationStatus,
        )
        from sale_api.models import Sale
        from customer_api.models import CustomerProfile

        self.user = User.objects.create_user(
            username='web-staff',
            email='web@example.com',
            password='testpass123',
            role='STAFF',
        )
        self.customer = (
            CustomerProfile.objects.create(
                user=self.user,
                customer_type='WEBSITE',
            )
        )
        self.variant = (
            ProductVariant.objects.first()
        )
        if self.variant is None:
            product = Product.objects.create(
                name='Test P',
                slug='test-p-sf',
                current_selling_price=Decimal(
                    '100.00'
                ),
            )
            self.variant = (
                ProductVariant.objects.create(
                    product=product,
                    sku='SF-001',
                )
            )
        self.sale = Sale.objects.create(
            customer=self.customer,
            sale_date=date.today(),
            status=SaleStatus.PENDING,
            channel=Sale.SaleChannel.WEBSITE,
            subtotal_amount=Decimal('200.00'),
            shipping_amount=Decimal('50.00'),
            total_amount=Decimal('250.00'),
            created_by=self.user,
            updated_by=self.user,
        )
        SaleItem.objects.create(
            sale=self.sale,
            product_variant=self.variant,
            quantity=2,
            unit_price=Decimal('100.00'),
            line_total=Decimal('200.00'),
        )
        # Give stock.
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=100,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        self.reservation = (
            InventoryReservation.objects.create(
                product_variant=self.variant,
                sale=self.sale,
                quantity=2,
                status=ReservationStatus.ACTIVE,
                expires_at=(
                    timezone.now()
                    + timedelta(minutes=30)
                ),
                created_by=self.user,
                updated_by=self.user,
            )
        )
        self.InventoryReservation = (
            InventoryReservation
        )
        self.ReservationStatus = ReservationStatus

    def test_storefront_confirmation_consumes_reservations(
        self,
    ):
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        self.sale.refresh_from_db()
        self.assertEqual(
            self.sale.status, SaleStatus.CONFIRMED
        )
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status,
            self.ReservationStatus.CONSUMED,
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
        self.assertEqual(movement.quantity, -2)

    def test_storefront_confirmation_creates_receivable_accounting(
        self,
    ):
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        self.sale.refresh_from_db()
        self.assertIsNotNone(
            self.sale.accounting_transaction
        )
        self.assertIsNotNone(self.sale.account)
        self.assertEqual(
            self.sale.account.name,
            'Accounts Receivable',
        )

    def test_storefront_confirmation_rejects_expired_reservations(
        self,
    ):
        from datetime import timedelta
        from django.utils import timezone
        self.reservation.expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.reservation.save(
            update_fields=['expires_at']
        )
        with self.assertRaises(Exception):
            update_sale_status(
                self.user,
                self.sale,
                SaleStatus.CONFIRMED,
            )

    def _unreserved_sale(self, quantity=3):
        """A storefront sale placed without a reservation."""
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=date.today(),
            status=SaleStatus.PENDING,
            channel=Sale.SaleChannel.WEBSITE,
            subtotal_amount=Decimal('100.00') * quantity,
            shipping_amount=Decimal('50.00'),
            total_amount=(
                Decimal('100.00') * quantity + Decimal('50.00')
            ),
            created_by=self.user,
            updated_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product_variant=self.variant,
            quantity=quantity,
            unit_price=Decimal('100.00'),
            line_total=Decimal('100.00') * quantity,
        )
        return sale

    def test_storefront_confirmation_untracked_item_records_nothing(
        self,
    ):
        # The variant never had stock recorded: the order was
        # placed untracked and confirms without touching stock.
        self.reservation.delete()
        self.sale.delete()
        InventoryMovement.objects.filter(
            product_variant=self.variant,
        ).delete()
        sale = self._unreserved_sale()

        update_sale_status(
            self.user, sale, SaleStatus.CONFIRMED,
        )

        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CONFIRMED)
        self.assertIsNotNone(sale.accounting_transaction_id)
        self.assertFalse(
            InventoryMovement.objects.filter(
                product_variant=self.variant,
            ).exists()
        )

    def test_storefront_confirmation_deducts_item_tracked_after_order(
        self,
    ):
        # Opening stock (100 in setUp) was recorded after the
        # order was placed without a reservation: confirmation
        # deducts it like a POS sale.
        sale = self._unreserved_sale(quantity=3)

        update_sale_status(
            self.user, sale, SaleStatus.CONFIRMED,
        )

        movement = InventoryMovement.objects.get(
            product_variant=self.variant,
            movement_type=MovementType.SALE,
            reference_id=sale.id,
        )
        self.assertEqual(movement.quantity, -3)
        self.assertEqual(
            movement.reference_type, ReferenceType.ORDER
        )

    def test_storefront_confirmation_unreserved_item_checks_stock(
        self,
    ):
        from django.core.exceptions import ValidationError
        # Only the setUp reservation (2) is outstanding, so 98
        # units are available; 99 must be refused.
        sale = self._unreserved_sale(quantity=99)

        with self.assertRaises(ValidationError):
            update_sale_status(
                self.user, sale, SaleStatus.CONFIRMED,
            )
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.PENDING)

    def test_storefront_return_rejected(self):
        # Must confirm first.
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        with self.assertRaises(Exception):
            update_sale_status(
                self.user,
                self.sale,
                SaleStatus.RETURNED,
            )

    def test_storefront_cancellation_releases_reservations(
        self,
    ):
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CANCELLED,
        )
        self.sale.refresh_from_db()
        self.assertEqual(
            self.sale.status, SaleStatus.CANCELLED
        )
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status,
            self.ReservationStatus.RELEASED,
        )

    def test_duplicate_confirmation_idempotent(self):
        """Second confirmation is idempotent."""
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        result = update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        self.assertEqual(
            result.status, SaleStatus.CONFIRMED
        )

    def test_duplicate_cancellation_idempotent(
        self,
    ):
        """Second cancellation must succeed
        (idempotent)."""
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CANCELLED,
        )
        # Status is already CANCELLED.
        result = update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CANCELLED,
        )
        self.assertEqual(
            result.status, SaleStatus.CANCELLED
        )

    def test_confirmed_storefront_cancellation_rejected(
        self,
    ):
        """CONFIRMED→CANCELLED is not allowed for
        storefront orders. The transition check
        rejects it before the WEBSITE branch runs."""
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        with self.assertRaises(Exception):
            update_sale_status(
                self.user,
                self.sale,
                SaleStatus.CANCELLED,
            )
        self.sale.refresh_from_db()
        self.assertEqual(
            self.sale.status, SaleStatus.CONFIRMED
        )

    def test_stale_cancel_after_confirmation_rejected(self):
        """A PENDING copy loaded before confirmation must not
        cancel the confirmed order."""
        from django.core.exceptions import ValidationError

        stale = Sale.objects.get(pk=self.sale.pk)
        update_sale_status(
            self.user, self.sale, SaleStatus.CONFIRMED
        )
        with self.assertRaises(ValidationError):
            update_sale_status(
                self.user, stale, SaleStatus.CANCELLED
            )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, SaleStatus.CONFIRMED)
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status,
            self.ReservationStatus.CONSUMED,
        )

    def test_stale_confirmation_after_cancel_rejected(self):
        """A PENDING copy loaded before cancellation must not
        confirm, consume stock or post accounting."""
        from django.core.exceptions import ValidationError

        stale = Sale.objects.get(pk=self.sale.pk)
        update_sale_status(
            self.user, self.sale, SaleStatus.CANCELLED
        )
        with self.assertRaises(ValidationError):
            update_sale_status(
                self.user, stale, SaleStatus.CONFIRMED
            )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, SaleStatus.CANCELLED)
        self.assertIsNone(self.sale.accounting_transaction_id)
        self.assertFalse(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
                reference_id=self.sale.pk,
            ).exists()
        )
        self.reservation.refresh_from_db()
        self.assertEqual(
            self.reservation.status,
            self.ReservationStatus.RELEASED,
        )


class POSRegressionTest(TestCase):
    """Verify existing POS behavior is unchanged."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='pos-staff',
            email='pos@example.com',
            password='testpass123',
            role='STAFF',
        )
        self.customer = (
            CustomerProfile.objects.create(
                user=self.user,
                customer_type='POS',
            )
        )
        self.variant = (
            ProductVariant.objects.first()
        )
        if self.variant is None:
            product = Product.objects.create(
                name='Test P POS',
                slug='test-p-pos',
                current_selling_price=Decimal(
                    '50.00'
                ),
            )
            self.variant = (
                ProductVariant.objects.create(
                    product=product,
                    sku='POS-001',
                )
            )
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=100,
            movement_type=MovementType.OPENING,
            created_by=self.user,
            updated_by=self.user,
        )
        asset = ChartOfAccount.objects.create(
            name='Cash POS Test',
            account_type=AccountType.ASSET,
        )
        self.pm = PaymentMethod.objects.create(
            code='CASH-POS',
            name='Cash POS',
            default_account=asset,
        )
        self.sale = Sale.objects.create(
            customer=self.customer,
            sale_date=date.today(),
            status=SaleStatus.PENDING,
            channel=Sale.SaleChannel.WALK_IN,
            payment_method=self.pm,
            subtotal_amount=Decimal('100.00'),
            total_amount=Decimal('100.00'),
            created_by=self.user,
            updated_by=self.user,
        )
        SaleItem.objects.create(
            sale=self.sale,
            product_variant=self.variant,
            quantity=2,
            unit_price=Decimal('50.00'),
            line_total=Decimal('100.00'),
        )

    def test_pos_confirmation_uses_deduct_sale_stock(
        self,
    ):
        """POS confirmation uses the original
        _deduct_sale_stock, not reservations."""
        update_sale_status(
            self.user,
            self.sale,
            SaleStatus.CONFIRMED,
        )
        self.sale.refresh_from_db()
        self.assertEqual(
            self.sale.status, SaleStatus.CONFIRMED
        )
        movement = (
            InventoryMovement.objects.filter(
                product_variant=self.variant,
                movement_type=MovementType.SALE,
                reference_id=self.sale.pk,
            ).first()
        )
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, -2)

    def _reserve_for_storefront(self, quantity, expires_in_minutes=30):
        from datetime import timedelta
        from django.utils import timezone
        from inventory_api.models import (
            InventoryReservation,
            ReservationStatus,
        )

        web_sale = Sale.objects.create(
            customer=self.customer,
            sale_date=date.today(),
            channel=Sale.SaleChannel.WEBSITE,
            subtotal_amount=Decimal('0.00'),
            total_amount=Decimal('0.00'),
            created_by=self.user,
            updated_by=self.user,
        )
        return InventoryReservation.objects.create(
            product_variant=self.variant,
            sale=web_sale,
            quantity=quantity,
            status=ReservationStatus.ACTIVE,
            expires_at=(
                timezone.now()
                + timedelta(minutes=expires_in_minutes)
            ),
            created_by=self.user,
            updated_by=self.user,
        )

    def _assert_pos_confirmation_rejected(self):
        from django.core.exceptions import ValidationError

        with self.assertRaisesMessage(
            ValidationError, 'Insufficient stock'
        ):
            update_sale_status(
                self.user, self.sale, SaleStatus.CONFIRMED
            )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, SaleStatus.PENDING)
        self.assertIsNone(self.sale.accounting_transaction_id)
        self.assertFalse(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
                reference_id=self.sale.pk,
            ).exists()
        )

    def test_pos_confirmation_cannot_take_reserved_stock(self):
        from inventory_api.services.reservation import (
            get_available_stock,
        )

        # Leave one unit unreserved; the POS sale needs two.
        self._reserve_for_storefront(
            get_available_stock(self.variant) - 1
        )
        self._assert_pos_confirmation_rejected()

    def test_expired_reservation_does_not_block_pos(self):
        from inventory_api.services.reservation import (
            get_available_stock,
        )

        self._reserve_for_storefront(
            get_available_stock(self.variant),
            expires_in_minutes=-1,
        )
        sale = update_sale_status(
            self.user, self.sale, SaleStatus.CONFIRMED
        )
        self.assertEqual(sale.status, SaleStatus.CONFIRMED)

    def test_inactive_movements_do_not_count_as_stock(self):
        InventoryMovement.objects.filter(
            product_variant=self.variant,
        ).update(is_active=False)
        self._assert_pos_confirmation_rejected()

    def test_stale_second_confirmation_does_not_repost(self):
        """Confirming again with a PENDING copy loaded before the
        first confirmation must not deduct stock or post twice."""
        stale = Sale.objects.get(pk=self.sale.pk)
        first = update_sale_status(
            self.user, self.sale, SaleStatus.CONFIRMED
        )
        second = update_sale_status(
            self.user, stale, SaleStatus.CONFIRMED
        )
        self.assertEqual(second.status, SaleStatus.CONFIRMED)
        self.assertEqual(
            second.accounting_transaction_id,
            first.accounting_transaction_id,
        )
        self.assertEqual(
            InventoryMovement.objects.filter(
                movement_type=MovementType.SALE,
                reference_id=self.sale.pk,
            ).count(),
            1,
        )

    def test_pos_return_still_works(self):
        """POS return path is unchanged.
        Must follow full lifecycle:
        CONFIRMED→PROCESSING→PACKAGED→SHIPPED
        →OUT_OF_DELIVERY→DELIVERED→RETURNED."""
        statuses = [
            SaleStatus.CONFIRMED,
            SaleStatus.PROCESSING,
            SaleStatus.PACKAGED,
            SaleStatus.SHIPPED,
            SaleStatus.OUT_OF_DELIVERY,
            SaleStatus.DELIVERED,
            SaleStatus.RETURNED,
        ]
        for status in statuses:
            update_sale_status(
                self.user, self.sale, status,
            )
        self.sale.refresh_from_db()
        self.assertEqual(
            self.sale.status, SaleStatus.RETURNED
        )
        self.assertIsNotNone(
            self.sale.return_transaction
        )


class SaleSummaryApiTests(APITestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff-summary',
            email='staff-summary@example.com',
            password='test-pass-123',
            role='STAFF'
        )
        self.customer_user = User.objects.create_user(
            username='customer-summary',
            email='customer-summary@example.com',
            password='test-pass-123',
            role='CUSTOMER'
        )
        self.customer = CustomerProfile.objects.create(
            user=self.customer_user
        )
        self._create_sale(
            SaleStatus.PENDING, Decimal('45000.00'))
        self._create_sale(
            SaleStatus.PENDING, Decimal('1000.00'))
        self._create_sale(
            SaleStatus.DELIVERED, Decimal('2500.50'))
        self.client.force_authenticate(user=self.staff_user)

    def _create_sale(self, sale_status, total_amount):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=date(2026, 11, 1),
            status=sale_status,
            subtotal_amount=total_amount,
            total_amount=total_amount,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        return sale

    def test_summary_returns_counts_by_status(self):
        response = self.client.get('/api/v1/sales/summary/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        expected = {value: 0 for value, _ in SaleStatus.choices}
        expected.update({
            SaleStatus.PENDING: 2,
            SaleStatus.DELIVERED: 1,
        })
        self.assertEqual(response.data['data'], expected)

    def test_amount_summary_returns_decimal_strings(self):
        response = self.client.get(
            '/api/v1/sales/amount-summary/'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        expected = {
            value: '0.00' for value, _ in SaleStatus.choices
        }
        expected.update({
            SaleStatus.PENDING: '46000.00',
            SaleStatus.DELIVERED: '2500.50',
        })
        self.assertEqual(response.data['data'], expected)

    def test_summary_ignores_ordering_param(self):
        response = self.client.get(
            '/api/v1/sales/summary/?ordering=total_amount'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['data'][SaleStatus.PENDING], 2
        )

    def test_summary_respects_list_filters(self):
        response = self.client.get(
            '/api/v1/sales/summary/?status=' + SaleStatus.PENDING
        )

        self.assertEqual(response.status_code, 200)
        expected = {value: 0 for value, _ in SaleStatus.choices}
        expected[SaleStatus.PENDING] = 2
        self.assertEqual(response.data['data'], expected)

    def test_summary_zero_defaults_when_no_sales_match(self):
        expected_counts = {
            value: 0 for value, _ in SaleStatus.choices
        }
        expected_amounts = {
            value: '0.00' for value, _ in SaleStatus.choices
        }

        summary = self.client.get(
            '/api/v1/sales/summary/?channel=Instagram'
        )
        amount_summary = self.client.get(
            '/api/v1/sales/amount-summary/?channel=Instagram'
        )

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data['data'], expected_counts)
        self.assertEqual(amount_summary.status_code, 200)
        self.assertEqual(
            amount_summary.data['data'], expected_amounts
        )


class SalePerformanceReportApiTests(APITestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff-perf',
            email='staff-perf@example.com',
            password='test-pass-123',
            role='STAFF'
        )
        self.customer_user = User.objects.create_user(
            username='customer-perf',
            email='customer-perf@example.com',
            password='test-pass-123',
            role='CUSTOMER'
        )
        self.customer = CustomerProfile.objects.create(
            user=self.customer_user
        )
        self.today = timezone.now().date()
        self.client.force_authenticate(user=self.staff_user)

    def _create_sale(
        self, sale_date, total_amount=Decimal('100.00'),
        channel=Sale.SaleChannel.WALK_IN, sale_status=SaleStatus.PENDING,
        is_active=True,
    ):
        sale = Sale.objects.create(
            customer=self.customer,
            sale_date=sale_date,
            status=sale_status,
            channel=channel,
            subtotal_amount=total_amount,
            total_amount=total_amount,
            is_active=is_active,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        return sale

    def test_default_days_returns_90_day_window_with_zero_fill(self):
        self._create_sale(self.today, Decimal('100.00'))
        start_date = self.today - timedelta(days=89)
        self._create_sale(start_date, Decimal('50.00'))

        response = self.client.get('/api/v1/sales/reports/performance/')

        self.assertEqual(response.status_code, 200)
        data = response.data['data']
        self.assertEqual(data['period']['days'], 90)
        self.assertEqual(str(data['period']['start_date']), str(start_date))
        self.assertEqual(str(data['period']['end_date']), str(self.today))
        self.assertEqual(len(data['daily_trend']), 90)
        self.assertEqual(data['overview']['total_orders'], 2)
        self.assertEqual(data['overview']['total_revenue'], '150.00')
        self.assertEqual(
            data['overview']['average_order_value'], '75.00'
        )
        zero_days = [
            row for row in data['daily_trend']
            if row['order_count'] == 0
        ]
        self.assertEqual(len(zero_days), 88)
        for row in zero_days:
            self.assertEqual(row['revenue'], '0.00')

    def test_sale_just_outside_window_lands_in_previous_period(self):
        start_date = self.today - timedelta(days=9)
        previous_sale_date = start_date - timedelta(days=1)
        self._create_sale(previous_sale_date, Decimal('200.00'))
        self._create_sale(start_date, Decimal('100.00'))

        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=10'
        )

        self.assertEqual(response.status_code, 200)
        data = response.data['data']
        self.assertEqual(data['overview']['total_orders'], 1)
        self.assertEqual(data['overview']['total_revenue'], '100.00')
        self.assertEqual(data['comparison']['previous_period_orders'], 1)
        self.assertEqual(
            data['comparison']['previous_period_revenue'], '200.00'
        )
        self.assertEqual(
            data['comparison']['order_growth_percentage'], 0.0
        )
        self.assertEqual(
            data['comparison']['revenue_growth_percentage'], -50.0
        )

    def test_sale_before_previous_window_is_excluded(self):
        start_date = self.today - timedelta(days=9)
        previous_start_date = start_date - timedelta(days=10)
        too_old = previous_start_date - timedelta(days=1)
        self._create_sale(too_old, Decimal('999.00'))

        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=10'
        )

        data = response.data['data']
        self.assertEqual(data['comparison']['previous_period_orders'], 0)
        self.assertEqual(
            data['comparison']['previous_period_revenue'], '0.00'
        )
        self.assertIsNone(
            data['comparison']['order_growth_percentage']
        )
        self.assertIsNone(
            data['comparison']['revenue_growth_percentage']
        )

    def test_growth_percentage_null_when_previous_period_empty(self):
        self._create_sale(self.today, Decimal('100.00'))

        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=10'
        )

        data = response.data['data']
        self.assertIsNone(
            data['comparison']['order_growth_percentage']
        )
        self.assertIsNone(
            data['comparison']['revenue_growth_percentage']
        )

    def test_soft_deleted_sales_are_excluded(self):
        self._create_sale(self.today, Decimal('500.00'), is_active=False)

        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=10'
        )

        data = response.data['data']
        self.assertEqual(data['overview']['total_orders'], 0)
        self.assertEqual(data['overview']['total_revenue'], '0.00')
        self.assertEqual(data['overview']['average_order_value'], '0.00')

    def test_channel_filter_applies_to_both_periods(self):
        start_date = self.today - timedelta(days=9)
        previous_sale_date = start_date - timedelta(days=1)
        self._create_sale(
            self.today, Decimal('100.00'), channel=Sale.SaleChannel.WEBSITE
        )
        self._create_sale(
            previous_sale_date, Decimal('200.00'),
            channel=Sale.SaleChannel.WEBSITE,
        )
        self._create_sale(
            self.today, Decimal('300.00'), channel=Sale.SaleChannel.PHONE
        )

        response = self.client.get(
            '/api/v1/sales/reports/performance/'
            '?days=10&channel=Website'
        )

        data = response.data['data']
        self.assertEqual(data['overview']['total_orders'], 1)
        self.assertEqual(data['overview']['total_revenue'], '100.00')
        self.assertEqual(data['comparison']['previous_period_orders'], 1)
        self.assertEqual(
            data['comparison']['previous_period_revenue'], '200.00'
        )

    def test_days_rejects_zero(self):
        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=0'
        )

        self.assertEqual(response.status_code, 400)

    def test_days_rejects_over_365(self):
        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=366'
        )

        self.assertEqual(response.status_code, 400)

    def test_days_rejects_non_integer(self):
        response = self.client.get(
            '/api/v1/sales/reports/performance/?days=abc'
        )

        self.assertEqual(response.status_code, 400)

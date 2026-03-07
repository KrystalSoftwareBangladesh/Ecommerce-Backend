from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from customer_api.models import CustomerProfile
from product_api.models import Product, ProductVariant
from inventory_api.models import InventoryMovement, MovementType, ReferenceType
from sale_api.models import Sale, SaleStatus
from sale_api.services import create_sale, update_sale_status
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

    def _payload(self, invoice_number=None):
        return {
            'customer': self.customer,
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
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=10,
            movement_type=MovementType.OPENING,
            reference_type=ReferenceType.MANUAL,
            created_by=self.staff_user
        )
        self.sale = create_sale(self.staff_user, {
            'customer': self.customer,
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
        final_stock = InventoryMovement.objects.filter(
            product_variant=self.variant
        ).values_list('quantity', flat=True)
        self.assertEqual(sum(final_stock), 10)

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
        InventoryMovement.objects.create(
            product_variant=self.variant,
            quantity=5,
            movement_type=MovementType.OPENING,
            reference_type=ReferenceType.MANUAL,
            created_by=self.staff_user
        )
        self.sale = create_sale(self.staff_user, {
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
        self.client.force_authenticate(user=self.staff_user)

    def test_statuses_endpoint_returns_frontend_contract(self):
        response = self.client.get('/api/v1/sales/statuses/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['default'], SaleStatus.PENDING)
        self.assertEqual(
            response.data['transitions']['PENDING'],
            [SaleStatus.CONFIRMED]
        )

    def test_update_status_endpoint_updates_sale(self):
        response = self.client.post(
            f'/api/v1/sales/{self.sale.id}/update-status/',
            {'status': SaleStatus.CONFIRMED},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], SaleStatus.CONFIRMED)
        self.assertEqual(
            response.data['allowed_next_statuses'],
            [{'value': SaleStatus.PROCESSING, 'label': 'Processing'}]
        )

    def test_patch_sale_can_update_status_without_invoice_number(self):
        response = self.client.patch(
            f'/api/v1/sales/{self.sale.id}/',
            {'status': SaleStatus.CONFIRMED},
            format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], SaleStatus.CONFIRMED)

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

from datetime import date
from decimal import Decimal

from django.test import TestCase

from customer_api.models import CustomerProfile
from product_api.models import Product, ProductVariant
from sale_api.models import Sale
from sale_api.services import create_sale
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

    def test_sale_channel_choices_contract(self):
        self.assertEqual(
            [value for value, _ in Sale.SaleChannel.choices],
            ['Walk-in', 'Facebook', 'Phone', 'Website', 'Instagram', 'WhatsApp']
        )

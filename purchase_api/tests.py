from decimal import Decimal

from rest_framework.test import APITestCase

from account_api.models import AccountType, ChartOfAccount
from inventory_api.models import InventoryMovement, MovementType, ReferenceType
from product_api.models import Product, ProductVariant
from purchase_api.models import Purchase, PurchaseStatus
from supplier_api.models import PaymentType, Supplier
from transaction_api.models import TransactionStatus, TransactionType
from user_api.models import User


class PurchaseAccountingApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='purchase-staff',
            email='purchase-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.client.force_authenticate(user=self.user)

        self.supplier = Supplier.objects.create(
            name='Demo Supplier',
            payment_type=PaymentType.CREDIT,
            credit_days=30,
            created_by=self.user,
            updated_by=self.user,
        )
        self.product = Product.objects.create(
            name='Demo Product',
            current_selling_price=Decimal('500.00'),
            created_by=self.user,
            updated_by=self.user,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='PUR-001',
        )
        self.payable_account = ChartOfAccount.objects.create(
            name='Accounts Payable',
            account_type=AccountType.LIABILITY,
            created_by=self.user,
            updated_by=self.user,
        )
        self.cash_account = ChartOfAccount.objects.create(
            name='Cash in Hand',
            account_type=AccountType.ASSET,
            created_by=self.user,
            updated_by=self.user,
        )
        self.expense_account = ChartOfAccount.objects.create(
            name='Purchase Expense',
            account_type=AccountType.EXPENSE,
            created_by=self.user,
            updated_by=self.user,
        )

    def _purchase_payload(self, **overrides):
        payload = {
            'supplier': self.supplier.id,
            'account_id': self.payable_account.id,
            'purchase_date': '2026-03-20',
            'invoice_number': 'BILL-1001',
            'discount_amount': '10.00',
            'tax_amount': '20.00',
            'notes': 'Warehouse replenishment',
            'items': [
                {
                    'product_variant_id': self.variant.id,
                    'quantity': 2,
                    'unit_cost': '100.00',
                }
            ],
        }
        payload.update(overrides)
        return payload

    def test_create_purchase_persists_selected_account(self):
        response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        purchase = Purchase.objects.get(pk=response.data['id'])
        self.assertEqual(purchase.account, self.payable_account)
        self.assertEqual(response.data['account']['id'], self.payable_account.id)
        self.assertIsNone(response.data['accounting_transaction'])

    def test_create_purchase_generates_invoice_number_when_missing(self):
        response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(invoice_number=None),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        purchase = Purchase.objects.get(pk=response.data['id'])
        self.assertIsNotNone(purchase.invoice_number)
        self.assertTrue(purchase.invoice_number.startswith('PUR-20260320-'))
        self.assertEqual(response.data['invoice_number'], purchase.invoice_number)

    def test_create_purchase_generates_invoice_number_when_blank(self):
        response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(invoice_number='   '),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        purchase = Purchase.objects.get(pk=response.data['id'])
        self.assertTrue(purchase.invoice_number.startswith('PUR-20260320-'))

    def test_create_purchase_keeps_manual_invoice_number(self):
        response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(invoice_number='BILL-1001'),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        purchase = Purchase.objects.get(pk=response.data['id'])
        self.assertEqual(purchase.invoice_number, 'BILL-1001')

    def test_confirm_purchase_creates_posted_accounting_transaction(self):
        create_response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(),
            format='json',
        )
        purchase_id = create_response.data['id']

        response = self.client.post(
            f'/api/v1/purchases/{purchase_id}/confirm/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        purchase = Purchase.objects.get(pk=purchase_id)
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)
        self.assertIsNotNone(purchase.accounting_transaction)
        self.assertEqual(
            purchase.accounting_transaction.transaction_type,
            TransactionType.PURCHASE,
        )
        self.assertEqual(
            purchase.accounting_transaction.status,
            TransactionStatus.POSTED,
        )
        self.assertEqual(
            response.data['accounting_transaction']['id'],
            purchase.accounting_transaction.id,
        )

        inventory_movements = InventoryMovement.objects.filter(
            reference_type=ReferenceType.PURCHASE,
            reference_id=purchase.id,
            movement_type=MovementType.PURCHASE,
        )
        self.assertEqual(inventory_movements.count(), 1)
        self.assertEqual(inventory_movements.first().quantity, 2)

        inventory_account = ChartOfAccount.objects.get(name='Inventory Asset')
        lines = purchase.accounting_transaction.lines.all()
        self.assertEqual(lines.count(), 2)
        self.assertTrue(lines.filter(
            account=inventory_account,
            debit_amount=Decimal('210.00'),
            credit_amount=Decimal('0.00'),
        ).exists())
        self.assertTrue(lines.filter(
            account=self.payable_account,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('210.00'),
        ).exists())

    def test_confirm_purchase_requires_valid_account(self):
        create_response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(account_id=None),
            format='json',
        )
        purchase_id = create_response.data['id']

        response = self.client.post(
            f'/api/v1/purchases/{purchase_id}/confirm/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['detail']['account_id'],
            'An account must be selected before confirmation.',
        )

    def test_confirm_purchase_accepts_account_id_in_confirm_request(self):
        create_response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(account_id=None),
            format='json',
        )
        purchase_id = create_response.data['id']

        response = self.client.post(
            f'/api/v1/purchases/{purchase_id}/confirm/',
            {'account_id': self.cash_account.id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        purchase = Purchase.objects.get(pk=purchase_id)
        self.assertEqual(purchase.account, self.cash_account)
        self.assertEqual(purchase.status, PurchaseStatus.CONFIRMED)

    def test_cancel_purchase_creates_reversal_transaction(self):
        create_response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(),
            format='json',
        )
        purchase_id = create_response.data['id']
        self.client.post(
            f'/api/v1/purchases/{purchase_id}/confirm/',
            {},
            format='json',
        )

        response = self.client.post(
            f'/api/v1/purchases/{purchase_id}/cancel/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        purchase = Purchase.objects.get(pk=purchase_id)
        self.assertEqual(purchase.status, PurchaseStatus.CANCELLED)
        self.assertIsNotNone(purchase.cancellation_transaction)
        self.assertEqual(
            purchase.cancellation_transaction.transaction_type,
            TransactionType.ADJUSTMENT,
        )
        self.assertEqual(
            purchase.cancellation_transaction.status,
            TransactionStatus.POSTED,
        )

        inventory_account = ChartOfAccount.objects.get(name='Inventory Asset')
        reversal_lines = purchase.cancellation_transaction.lines.all()
        self.assertTrue(reversal_lines.filter(
            account=self.payable_account,
            debit_amount=Decimal('210.00'),
            credit_amount=Decimal('0.00'),
        ).exists())
        self.assertTrue(reversal_lines.filter(
            account=inventory_account,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('210.00'),
        ).exists())

        movement_quantities = list(
            InventoryMovement.objects.filter(
                reference_type=ReferenceType.PURCHASE,
                reference_id=purchase.id,
            ).values_list('quantity', flat=True)
        )
        self.assertEqual(sorted(movement_quantities), [-2, 2])

    def test_purchase_create_rejects_non_asset_or_liability_account(self):
        response = self.client.post(
            '/api/v1/purchases/',
            self._purchase_payload(account_id=self.expense_account.id),
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['account_id'][0],
            'Purchase account must be an asset or liability account.',
        )

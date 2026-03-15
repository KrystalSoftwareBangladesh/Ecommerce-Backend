from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from account_api.models import AccountType, ChartOfAccount
from transaction_api.models import TransactionStatus, TransactionType
from transaction_api.services import create_transaction
from user_api.models import User


class AccountingTransactionApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='transaction-staff',
            email='transaction-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.client.force_authenticate(user=self.user)
        self.cash_account = ChartOfAccount.objects.create(
            name='Cash',
            account_type=AccountType.ASSET,
            created_by=self.user,
            updated_by=self.user,
        )
        self.sales_account = ChartOfAccount.objects.create(
            name='Sales Income',
            account_type=AccountType.REVENUE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.expense_account = ChartOfAccount.objects.create(
            name='Office Expense',
            account_type=AccountType.EXPENSE,
            created_by=self.user,
            updated_by=self.user,
        )

    def _lines(self, debit_account, credit_account):
        return [
            {
                'account_id': debit_account.id,
                'description': 'Debit line',
                'debit_amount': '100.00',
                'credit_amount': '0.00',
            },
            {
                'account_id': credit_account.id,
                'description': 'Credit line',
                'debit_amount': '0.00',
                'credit_amount': '100.00',
            },
        ]

    def test_create_defaults_transaction_type_to_journal(self):
        response = self.client.post(
            '/api/v1/transactions/',
            {
                'transaction_date': '2026-03-15',
                'reference': 'TXN-DEFAULT',
                'description': 'Default type transaction',
                'lines': self._lines(self.cash_account, self.sales_account),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['transaction_type'],
            TransactionType.JOURNAL,
        )
        self.assertEqual(response.data['status'], TransactionStatus.DRAFT)

    def test_create_accepts_explicit_transaction_type(self):
        response = self.client.post(
            '/api/v1/transactions/',
            {
                'transaction_date': '2026-03-15',
                'transaction_type': TransactionType.PAYMENT,
                'reference': 'TXN-PAYMENT',
                'description': 'Payment transaction',
                'lines': self._lines(self.expense_account, self.cash_account),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['transaction_type'],
            TransactionType.PAYMENT,
        )

    def test_create_accepts_investment_transaction_type(self):
        response = self.client.post(
            '/api/v1/transactions/',
            {
                'transaction_date': '2026-03-15',
                'transaction_type': TransactionType.INVESTMENT,
                'reference': 'TXN-INVESTMENT',
                'description': 'Owner capital introduced',
                'lines': self._lines(self.cash_account, self.sales_account),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['transaction_type'],
            TransactionType.INVESTMENT,
        )

    def test_create_accepts_owner_withdrawal_transaction_type(self):
        response = self.client.post(
            '/api/v1/transactions/',
            {
                'transaction_date': '2026-03-15',
                'transaction_type': TransactionType.OWNER_WITHDRAWAL,
                'reference': 'TXN-OWNER-WITHDRAWAL',
                'description': 'Owner cash withdrawal',
                'lines': self._lines(self.expense_account, self.cash_account),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['transaction_type'],
            TransactionType.OWNER_WITHDRAWAL,
        )

    def test_create_accepts_transaction_datetime(self):
        response = self.client.post(
            '/api/v1/transactions/',
            {
                'transaction_date': '2026-03-15',
                'transaction_datetime': '2026-03-15T14:30:00Z',
                'reference': 'TXN-DATETIME',
                'description': 'Transaction with time',
                'lines': self._lines(self.cash_account, self.sales_account),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['transaction_datetime'],
            '2026-03-15T14:30:00Z',
        )

    def test_partial_update_allows_changing_transaction_type_for_draft(self):
        transaction = create_transaction(
            self.user,
            {
                'transaction_date': date(2026, 3, 15),
                'transaction_type': TransactionType.JOURNAL,
                'reference': 'TXN-UPDATE',
                'description': 'Editable transaction',
                'lines': [
                    {
                        'account': self.cash_account,
                        'debit_amount': Decimal('100.00'),
                        'credit_amount': Decimal('0.00'),
                    },
                    {
                        'account': self.sales_account,
                        'debit_amount': Decimal('0.00'),
                        'credit_amount': Decimal('100.00'),
                    },
                ],
            },
        )

        response = self.client.patch(
            f'/api/v1/transactions/{transaction.id}/',
            {'transaction_type': TransactionType.RECEIPT},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['transaction_type'],
            TransactionType.RECEIPT,
        )

    def test_partial_update_allows_changing_transaction_datetime_for_draft(self):
        transaction = create_transaction(
            self.user,
            {
                'transaction_date': date(2026, 3, 15),
                'reference': 'TXN-DATETIME-UPDATE',
                'description': 'Editable transaction datetime',
                'lines': [
                    {
                        'account': self.cash_account,
                        'debit_amount': Decimal('100.00'),
                        'credit_amount': Decimal('0.00'),
                    },
                    {
                        'account': self.sales_account,
                        'debit_amount': Decimal('0.00'),
                        'credit_amount': Decimal('100.00'),
                    },
                ],
            },
        )

        response = self.client.patch(
            f'/api/v1/transactions/{transaction.id}/',
            {'transaction_datetime': '2026-03-15T16:45:00Z'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['transaction_datetime'],
            '2026-03-15T16:45:00Z',
        )

    def test_list_filters_by_transaction_type(self):
        payment = create_transaction(
            self.user,
            {
                'transaction_date': date(2026, 3, 15),
                'transaction_type': TransactionType.PAYMENT,
                'reference': 'TXN-FILTER-1',
                'description': 'Payment transaction',
                'lines': [
                    {
                        'account': self.expense_account,
                        'debit_amount': Decimal('50.00'),
                        'credit_amount': Decimal('0.00'),
                    },
                    {
                        'account': self.cash_account,
                        'debit_amount': Decimal('0.00'),
                        'credit_amount': Decimal('50.00'),
                    },
                ],
            },
        )
        create_transaction(
            self.user,
            {
                'transaction_date': date(2026, 3, 15),
                'transaction_type': TransactionType.RECEIPT,
                'reference': 'TXN-FILTER-2',
                'description': 'Receipt transaction',
                'lines': [
                    {
                        'account': self.cash_account,
                        'debit_amount': Decimal('75.00'),
                        'credit_amount': Decimal('0.00'),
                    },
                    {
                        'account': self.sales_account,
                        'debit_amount': Decimal('0.00'),
                        'credit_amount': Decimal('75.00'),
                    },
                ],
            },
        )

        response = self.client.get(
            '/api/v1/transactions/',
            {'transaction_type': TransactionType.PAYMENT},
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(returned_ids, {payment.id})

    def test_types_endpoint_returns_frontend_contract(self):
        response = self.client.get('/api/v1/transactions/types/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['default'], TransactionType.JOURNAL)
        self.assertEqual(
            [item['value'] for item in response.data['types']],
            [value for value, _ in TransactionType.choices],
        )

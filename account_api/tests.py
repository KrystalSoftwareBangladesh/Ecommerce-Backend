from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from account_api.models import AccountType, ChartOfAccount
from transaction_api.models import TransactionType
from transaction_api.services import create_transaction, post_transaction
from user_api.models import User


class ChartOfAccountModelTests(TestCase):
    def test_create_first_top_level_account_starts_from_ten(self):
        account = ChartOfAccount.objects.create(
            name='Cash in Hand',
            account_type=AccountType.ASSET,
        )

        self.assertEqual(account.code, 'AST-1-10')

    def test_create_next_top_level_account_increments_by_ten(self):
        first_account = ChartOfAccount.objects.create(
            name='Current Assets',
            account_type=AccountType.ASSET,
        )
        second_account = ChartOfAccount.objects.create(
            name='Fixed Assets',
            account_type=AccountType.ASSET,
        )

        self.assertEqual(first_account.code, 'AST-1-10')
        self.assertEqual(second_account.code, 'AST-1-20')

    def test_top_level_sequences_are_independent_per_account_type(self):
        asset_account = ChartOfAccount.objects.create(
            name='Current Assets',
            account_type=AccountType.ASSET,
        )
        liability_account = ChartOfAccount.objects.create(
            name='Current Liabilities',
            account_type=AccountType.LIABILITY,
        )
        revenue_account = ChartOfAccount.objects.create(
            name='Sales Income',
            account_type=AccountType.REVENUE,
        )

        self.assertEqual(asset_account.code, 'AST-1-10')
        self.assertEqual(liability_account.code, 'LIA-2-10')
        self.assertEqual(revenue_account.code, 'REV-4-10')

    def test_create_child_accounts_increment_by_two_digits(self):
        parent = ChartOfAccount.objects.create(
            name='Current Assets',
            account_type=AccountType.ASSET,
        )
        child = ChartOfAccount.objects.create(
            name='Cash',
            account_type=AccountType.ASSET,
            parent=parent,
        )
        second_child = ChartOfAccount.objects.create(
            name='Bank',
            account_type=AccountType.ASSET,
            parent=parent,
        )

        self.assertEqual(child.code, 'AST-1-10-01')
        self.assertEqual(second_child.code, 'AST-1-10-02')

    def test_create_sub_child_accounts_increment_by_two_digits(self):
        root = ChartOfAccount.objects.create(
            name='Current Assets',
            account_type=AccountType.ASSET,
        )
        child = ChartOfAccount.objects.create(
            name='Bank',
            account_type=AccountType.ASSET,
            parent=root,
        )
        first_sub_child = ChartOfAccount.objects.create(
            name='City Bank',
            account_type=AccountType.ASSET,
            parent=child,
        )
        second_sub_child = ChartOfAccount.objects.create(
            name='BRAC Bank',
            account_type=AccountType.ASSET,
            parent=child,
        )

        self.assertEqual(child.code, 'AST-1-10-01')
        self.assertEqual(first_sub_child.code, 'AST-1-10-01-01')
        self.assertEqual(second_sub_child.code, 'AST-1-10-01-02')

    def test_updating_root_type_rebuilds_subtree_codes(self):
        ChartOfAccount.objects.create(
            name='Operating Expense',
            account_type=AccountType.EXPENSE,
        )
        root = ChartOfAccount.objects.create(
            name='Current Assets',
            account_type=AccountType.ASSET,
        )
        child = ChartOfAccount.objects.create(
            name='Bank',
            account_type=AccountType.ASSET,
            parent=root,
        )
        sub_child = ChartOfAccount.objects.create(
            name='City Bank',
            account_type=AccountType.ASSET,
            parent=child,
        )

        root.account_type = AccountType.EXPENSE
        root.save()

        root.refresh_from_db()
        child.refresh_from_db()
        sub_child.refresh_from_db()

        self.assertEqual(root.code, 'EXP-5-20')
        self.assertEqual(child.account_type, AccountType.EXPENSE)
        self.assertEqual(sub_child.account_type, AccountType.EXPENSE)
        self.assertEqual(child.code, 'EXP-5-20-01')
        self.assertEqual(sub_child.code, 'EXP-5-20-01-01')


class ChartOfAccountApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='account-staff',
            email='account-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.client.force_authenticate(user=self.user)
        self.asset_root = ChartOfAccount.objects.create(
            name='Current Assets',
            account_type=AccountType.ASSET,
            created_by=self.user,
            updated_by=self.user,
        )
        self.expense_root = ChartOfAccount.objects.create(
            name='Operating Expense',
            account_type=AccountType.EXPENSE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.liability_root = ChartOfAccount.objects.create(
            name='Current Liabilities',
            account_type=AccountType.LIABILITY,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_create_generates_account_code_at_backend(self):
        response = self.client.post(
            '/api/v1/chart-of-accounts/',
            {
                'name': 'Accounts Receivable',
                'account_type': AccountType.ASSET,
                'description': 'Receivable from customers',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        account = ChartOfAccount.objects.get(pk=response.data['id'])
        self.assertEqual(response.data['code'], 'AST-1-20')
        self.assertEqual(response.data['code'], account.code)
        self.assertEqual(account.created_by, self.user)
        self.assertEqual(account.updated_by, self.user)

    def test_create_child_generates_code_from_parent(self):
        response = self.client.post(
            '/api/v1/chart-of-accounts/',
            {
                'name': 'Cash Drawer',
                'account_type': AccountType.ASSET,
                'parent': self.asset_root.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['code'], 'AST-1-10-01')

    def test_create_sub_child_generates_code_from_parent(self):
        child = ChartOfAccount.objects.create(
            name='Bank',
            account_type=AccountType.ASSET,
            parent=self.asset_root,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            '/api/v1/chart-of-accounts/',
            {
                'name': 'City Bank',
                'account_type': AccountType.ASSET,
                'parent': child.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['code'], 'AST-1-10-01-01')

    def test_create_rejects_client_supplied_code(self):
        response = self.client.post(
            '/api/v1/chart-of-accounts/',
            {
                'code': 'ASSET-1001',
                'name': 'Bank Account',
                'account_type': AccountType.ASSET,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['code'][0],
            'Account code is generated automatically.',
        )

    def test_update_rejects_client_supplied_code(self):
        account = ChartOfAccount.objects.create(
            name='Office Expense',
            account_type=AccountType.EXPENSE,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.patch(
            f'/api/v1/chart-of-accounts/{account.id}/',
            {
                'code': 'EXP-9999',
                'name': 'Office Expense Updated',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        account.refresh_from_db()
        self.assertEqual(account.name, 'Office Expense')

    def test_create_preserves_parent_account_type_validation(self):
        response = self.client.post(
            '/api/v1/chart-of-accounts/',
            {
                'name': 'Office Rent',
                'account_type': AccountType.EXPENSE,
                'parent': self.asset_root.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['parent'][0],
            'Parent account must have the same account type.',
        )

    def test_list_filters_by_single_account_type(self):
        response = self.client.get(
            '/api/v1/chart-of-accounts/',
            {'account_type': AccountType.ASSET},
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(returned_ids, {self.asset_root.id})

    def test_list_filters_by_multiple_account_types_with_repeated_params(self):
        response = self.client.get(
            '/api/v1/chart-of-accounts/?account_type=ASSET&account_type=EXPENSE'
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(
            returned_ids,
            {self.asset_root.id, self.expense_root.id},
        )

    def test_list_filters_by_multiple_account_types_with_comma_separated_values(self):
        response = self.client.get(
            '/api/v1/chart-of-accounts/',
            {'account_type': 'ASSET,LIABILITY'},
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.data['results']}
        self.assertEqual(
            returned_ids,
            {self.asset_root.id, self.liability_root.id},
        )

    def test_create_account_with_opening_balance_creates_posted_transaction(self):
        response = self.client.post(
            '/api/v1/chart-of-accounts/',
            {
                'name': 'Cash in Hand',
                'account_type': AccountType.ASSET,
                'opening_balance': '1500.00',
                'opening_date': '2026-03-01',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        account = ChartOfAccount.objects.get(pk=response.data['id'])
        opening_transaction = account.opening_transaction

        self.assertIsNotNone(opening_transaction)
        self.assertEqual(account.opening_balance, Decimal('1500.00'))
        self.assertEqual(account.opening_date, date(2026, 3, 1))
        self.assertEqual(
            opening_transaction.transaction_type,
            TransactionType.OPENING_BALANCE,
        )
        self.assertEqual(opening_transaction.status, 'POSTED')

        contra_account = ChartOfAccount.objects.get(
            name='Opening Balance Equity',
            account_type=AccountType.EQUITY,
        )
        self.assertTrue(
            opening_transaction.lines.filter(
                account=contra_account,
                credit_amount=Decimal('1500.00'),
            ).exists()
        )

    def test_set_opening_balance_action_updates_account_metadata(self):
        account = ChartOfAccount.objects.create(
            name='Bank Account',
            account_type=AccountType.ASSET,
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            f'/api/v1/chart-of-accounts/{account.id}/set-opening-balance/',
            {
                'amount': '2200.00',
                'date': '2026-03-05',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(account.opening_balance, Decimal('2200.00'))
        self.assertEqual(account.opening_date, date(2026, 3, 5))
        self.assertIsNotNone(account.opening_transaction)
        self.assertEqual(
            account.opening_transaction.transaction_type,
            TransactionType.OPENING_BALANCE,
        )

    def test_set_opening_balance_action_blocks_accounts_with_posted_business_transactions(self):
        account = ChartOfAccount.objects.create(
            name='Accounts Payable',
            account_type=AccountType.LIABILITY,
            created_by=self.user,
            updated_by=self.user,
        )
        expense_account = ChartOfAccount.objects.create(
            name='Rent Expense',
            account_type=AccountType.EXPENSE,
            created_by=self.user,
            updated_by=self.user,
        )

        transaction = create_transaction(
            self.user,
            {
                'transaction_date': date(2026, 3, 10),
                'transaction_type': TransactionType.JOURNAL,
                'reference': 'BILL-1001',
                'description': 'Supplier bill posted before opening balance',
                'lines': [
                    {
                        'account': expense_account,
                        'debit_amount': Decimal('500.00'),
                        'credit_amount': Decimal('0'),
                    },
                    {
                        'account': account,
                        'debit_amount': Decimal('0'),
                        'credit_amount': Decimal('500.00'),
                    },
                ],
            },
        )
        post_transaction(self.user, transaction)

        response = self.client.post(
            f'/api/v1/chart-of-accounts/{account.id}/set-opening-balance/',
            {
                'amount': '1200.00',
                'date': '2026-03-01',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['detail'],
            (
                'Opening balance cannot be changed because this account already has '
                'posted business transactions.'
            ),
        )

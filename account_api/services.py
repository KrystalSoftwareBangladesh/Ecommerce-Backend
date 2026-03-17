from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from account_api.models import AccountType, ChartOfAccount
from transaction_api.models import TransactionStatus, TransactionType
from transaction_api.services import create_transaction, post_transaction


OPENING_BALANCE_EQUITY_ACCOUNT_NAME = 'Opening Balance Equity'
OPENING_BALANCE_EQUITY_DESCRIPTION = (
    'System-generated contra account used when recording opening balances.'
)
DEBIT_NORMAL_ACCOUNTS = {
    AccountType.ASSET,
    AccountType.EXPENSE,
}


def get_or_create_opening_balance_equity_account(user=None):
    """Return the default contra account used for opening balances."""
    with transaction.atomic():
        account = ChartOfAccount.objects.select_for_update().filter(
            name=OPENING_BALANCE_EQUITY_ACCOUNT_NAME,
            account_type=AccountType.EQUITY,
        ).order_by('id').first()

        if account:
            update_fields = []
            if not account.is_active:
                account.is_active = True
                update_fields.append('is_active')
            if account.deleted_at is not None:
                account.deleted_at = None
                update_fields.append('deleted_at')
            if user and account.updated_by_id != getattr(user, 'id', None):
                account.updated_by = user
                update_fields.append('updated_by')
            if update_fields:
                update_fields.append('updated_at')
                account.save(update_fields=update_fields)
            return account

        return ChartOfAccount.objects.create(
            name=OPENING_BALANCE_EQUITY_ACCOUNT_NAME,
            account_type=AccountType.EQUITY,
            description=OPENING_BALANCE_EQUITY_DESCRIPTION,
            created_by=user,
            updated_by=user,
        )


def _build_opening_balance_lines(account, contra_account, amount):
    if account.account_type in DEBIT_NORMAL_ACCOUNTS:
        account_line = {
            'account': account,
            'description': f'Opening balance for {account.name}',
            'debit_amount': amount,
            'credit_amount': Decimal('0'),
        }
        contra_line = {
            'account': contra_account,
            'description': f'Contra entry for {account.name}',
            'debit_amount': Decimal('0'),
            'credit_amount': amount,
        }
        return [account_line, contra_line]

    account_line = {
        'account': account,
        'description': f'Opening balance for {account.name}',
        'debit_amount': Decimal('0'),
        'credit_amount': amount,
    }
    contra_line = {
        'account': contra_account,
        'description': f'Contra entry for {account.name}',
        'debit_amount': amount,
        'credit_amount': Decimal('0'),
    }
    return [contra_line, account_line]


def _validate_opening_balance_request(account, amount, contra_account):
    if account.deleted_at is not None or not account.is_active:
        raise ValidationError(
            'Opening balance can only be set for an active account.'
        )

    if amount is None or amount <= Decimal('0'):
        raise ValidationError(
            'Opening balance amount must be greater than zero.'
        )

    if contra_account.deleted_at is not None or not contra_account.is_active:
        raise ValidationError(
            'The selected contra account is inactive. Please choose '
            'an active account.'
        )

    if contra_account.pk == account.pk:
        raise ValidationError(
            'The contra account must be different from the '
            'account you are opening.'
        )

    if account.has_posted_non_opening_transactions():
        raise ValidationError(
            'Opening balance cannot be changed because this '
            'account already has posted business transactions.'
        )


def set_opening_balance(
    account,
    amount: Decimal,
    date,
    user,
    contra_account=None,
):
    """
    Create and post an explicit opening-balance transaction for an account.

    Design notes:
    - We never create accounting entries from model save hooks.
    - The opening balance is always recorded as a real posted transaction.
    - If the account already has an opening balance and no posted business
      transactions yet, the previous linked opening transaction is retired and
      replaced so the account keeps a single active opening reference.
    """
    with transaction.atomic():
        locked_account = ChartOfAccount.objects.select_for_update().get(
            pk=account.pk,
        )

        contra_account = (
            ChartOfAccount.objects.select_for_update().get(
                pk=contra_account.pk,
            )
            if contra_account is not None
            else get_or_create_opening_balance_equity_account(user=user)
        )

        _validate_opening_balance_request(
            locked_account,
            amount,
            contra_account,
        )

        duplicate_opening_transaction_exists = (
            locked_account.transaction_lines.filter(
                transaction__deleted_at__isnull=True,
                transaction__status=TransactionStatus.POSTED,
                transaction__transaction_type=TransactionType.OPENING_BALANCE,
            ).exclude(
                transaction_id=locked_account.opening_transaction_id,
            ).exists()
        )
        if duplicate_opening_transaction_exists:
            raise ValidationError(
                'This account already has an opening balance '
                'transaction. Please review it before creating '
                'another one.'
            )

        if locked_account.opening_transaction_id:
            opening_transaction = locked_account.opening_transaction
            opening_transaction.is_active = False
            opening_transaction.deleted_at = timezone.now()
            opening_transaction.updated_by = user
            opening_transaction.save(update_fields=[
                'is_active',
                'deleted_at',
                'updated_by',
                'updated_at',
            ])

        transaction_reference = (
            f'OB-{locked_account.code}'
            if locked_account.code
            else f'OB-{locked_account.pk}'
        )
        opening_transaction = create_transaction(
            user,
            {
                'transaction_date': date,
                'transaction_type': TransactionType.OPENING_BALANCE,
                'reference': transaction_reference[:100],
                'description': (
                    f'Opening balance recorded for {locked_account.name}.'
                ),
                'lines': _build_opening_balance_lines(
                    locked_account,
                    contra_account,
                    amount,
                ),
            },
        )
        opening_transaction = post_transaction(user, opening_transaction)

        locked_account.opening_balance = amount
        locked_account.opening_date = date
        locked_account.opening_transaction = opening_transaction
        locked_account.updated_by = user
        locked_account.save(update_fields=[
            'opening_balance',
            'opening_date',
            'opening_transaction',
            'updated_by',
            'updated_at',
        ])

        return locked_account

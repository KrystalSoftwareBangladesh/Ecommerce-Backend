from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from transaction_api.models import (
    AccountingTransaction,
    AccountingTransactionLine,
    TransactionStatus,
)


def _generate_transaction_no(instance):
    date_part = instance.transaction_date.strftime('%Y%m%d')
    return f'TRX-{date_part}-{instance.id:06d}'


def _validate_lines(lines_data):
    if len(lines_data) < 2:
        raise ValidationError('At least two transaction lines are required.')

    total_debit = Decimal('0')
    total_credit = Decimal('0')

    for line_data in lines_data:
        account = line_data['account']
        debit_amount = line_data.get('debit_amount', Decimal('0'))
        credit_amount = line_data.get('credit_amount', Decimal('0'))

        if not account.is_active or account.deleted_at is not None:
            raise ValidationError(
                f'Inactive account is not allowed: {account}.'
            )

        if debit_amount < 0 or credit_amount < 0:
            raise ValidationError(
                'Debit and credit amounts must be non-negative.'
            )

        if debit_amount == 0 and credit_amount == 0:
            raise ValidationError(
                'Each transaction line must contain a debit or credit amount.'
            )

        if debit_amount > 0 and credit_amount > 0:
            raise ValidationError(
                'A transaction line cannot have both debit and credit amounts.'
            )

        total_debit += debit_amount
        total_credit += credit_amount

    if total_debit <= 0 or total_credit <= 0:
        raise ValidationError(
            'Total debit and total credit must both be greater than zero.'
        )

    if total_debit != total_credit:
        raise ValidationError('Total debit and credit must be equal.')

    return total_debit, total_credit


def _replace_lines(instance, lines_data):
    instance.lines.all().delete()
    line_instances = []

    for line_data in lines_data:
        payload = dict(line_data)
        line_instances.append(
            AccountingTransactionLine(
                transaction=instance,
                **payload,
            )
        )

    AccountingTransactionLine.objects.bulk_create(line_instances)


def create_transaction(user, data):
    with transaction.atomic():
        lines_data = data.pop('lines')
        total_debit, total_credit = _validate_lines(lines_data)

        accounting_transaction = AccountingTransaction.objects.create(
            **data,
            created_by=user,
            updated_by=user,
            status=TransactionStatus.DRAFT,
            total_debit=total_debit,
            total_credit=total_credit,
        )

        _replace_lines(accounting_transaction, lines_data)

        if not accounting_transaction.transaction_no:
            accounting_transaction.transaction_no = _generate_transaction_no(
                accounting_transaction
            )
            accounting_transaction.save(update_fields=['transaction_no'])

        return accounting_transaction


def update_transaction(user, instance, data):
    if instance.status != TransactionStatus.DRAFT:
        raise ValidationError('Only draft transactions can be edited.')

    with transaction.atomic():
        lines_data = data.pop('lines', None)

        for field in [
            'transaction_date',
            'transaction_datetime',
            'transaction_type',
            'reference',
            'description',
        ]:
            if field in data:
                setattr(instance, field, data[field])

        if lines_data is not None:
            total_debit, total_credit = _validate_lines(lines_data)
            _replace_lines(instance, lines_data)
            instance.total_debit = total_debit
            instance.total_credit = total_credit

        if (
            instance.transaction_no
            and 'transaction_date' in data
        ):
            instance.transaction_no = _generate_transaction_no(instance)

        instance.updated_by = user
        instance.save()
        return instance


def post_transaction(user, instance):
    if instance.status != TransactionStatus.DRAFT:
        raise ValidationError('Only draft transactions can be posted.')

    lines_data = []
    for line in instance.lines.select_related('account'):
        lines_data.append({
            'account': line.account,
            'debit_amount': line.debit_amount,
            'credit_amount': line.credit_amount,
        })

    total_debit, total_credit = _validate_lines(lines_data)

    instance.status = TransactionStatus.POSTED
    instance.total_debit = total_debit
    instance.total_credit = total_credit
    instance.updated_by = user
    instance.save(update_fields=[
        'status',
        'total_debit',
        'total_credit',
        'updated_by',
        'updated_at',
    ])
    return instance

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from account_api.models import ChartOfAccount
from transaction_api.models import (
    AccountingTransaction,
    AccountingTransactionLine,
    TransactionType,
)


class TransactionAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChartOfAccount
        fields = ['id', 'code', 'name', 'account_type']


class TransactionAccountSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChartOfAccount
        fields = ['id', 'code', 'name']


class AccountingTransactionLineSerializer(serializers.ModelSerializer):
    account = TransactionAccountSerializer(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='account',
        write_only=True,
    )

    class Meta:
        model = AccountingTransactionLine
        fields = [
            'id',
            'account',
            'account_id',
            'description',
            'debit_amount',
            'credit_amount',
        ]

    def validate(self, attrs):
        debit_amount = attrs.get('debit_amount', Decimal('0'))
        credit_amount = attrs.get('credit_amount', Decimal('0'))

        if debit_amount < 0 or credit_amount < 0:
            raise serializers.ValidationError(
                'Debit and credit amounts must be non-negative.'
            )

        if debit_amount == 0 and credit_amount == 0:
            raise serializers.ValidationError(
                'Either debit amount or credit amount is required.'
            )

        if debit_amount > 0 and credit_amount > 0:
            raise serializers.ValidationError(
                'A line cannot contain both debit and credit amounts.'
            )

        return attrs


class AccountingTransactionCreateSerializer(serializers.ModelSerializer):
    lines = AccountingTransactionLineSerializer(many=True)

    class Meta:
        model = AccountingTransaction
        fields = [
            'id',
            'transaction_date',
            'transaction_datetime',
            'transaction_type',
            'reference',
            'description',
            'lines',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        lines = attrs.get('lines', [])
        if len(lines) < 2:
            raise serializers.ValidationError(
                {'lines': 'At least two transaction lines are required.'}
            )
        return attrs


class AccountingTransactionListSerializer(serializers.ModelSerializer):
    primary_debit_account = serializers.SerializerMethodField()
    primary_credit_account = serializers.SerializerMethodField()
    debit_line_count = serializers.SerializerMethodField()
    credit_line_count = serializers.SerializerMethodField()

    class Meta:
        model = AccountingTransaction
        fields = [
            'id',
            'transaction_no',
            'transaction_date',
            'transaction_datetime',
            'transaction_type',
            'reference',
            'description',
            'status',
            'total_debit',
            'total_credit',
            'primary_debit_account',
            'primary_credit_account',
            'debit_line_count',
            'credit_line_count',
        ]

    def _get_prefetched_lines(self, obj):
        return getattr(obj, 'prefetched_lines', list(obj.lines.all()))

    def _get_line_summary(self, obj):
        cached_summary = getattr(obj, '_transaction_line_summary', None)
        if cached_summary is not None:
            return cached_summary

        debit_lines = []
        credit_lines = []
        for line in self._get_prefetched_lines(obj):
            if line.debit_amount > 0:
                debit_lines.append(line)
            if line.credit_amount > 0:
                credit_lines.append(line)

        summary = {
            'primary_debit_account': (
                debit_lines[0].account if debit_lines else None
            ),
            'primary_credit_account': (
                credit_lines[0].account if credit_lines else None
            ),
            'debit_line_count': len(debit_lines),
            'credit_line_count': len(credit_lines),
        }
        obj._transaction_line_summary = summary
        return summary

    @extend_schema_field(TransactionAccountSummarySerializer(allow_null=True))
    def get_primary_debit_account(self, obj):
        account = self._get_line_summary(obj)['primary_debit_account']
        if account is None:
            return None
        return TransactionAccountSummarySerializer(account).data

    @extend_schema_field(TransactionAccountSummarySerializer(allow_null=True))
    def get_primary_credit_account(self, obj):
        account = self._get_line_summary(obj)['primary_credit_account']
        if account is None:
            return None
        return TransactionAccountSummarySerializer(account).data

    @extend_schema_field(serializers.IntegerField())
    def get_debit_line_count(self, obj):
        return self._get_line_summary(obj)['debit_line_count']

    @extend_schema_field(serializers.IntegerField())
    def get_credit_line_count(self, obj):
        return self._get_line_summary(obj)['credit_line_count']


class AccountingTransactionDetailSerializer(serializers.ModelSerializer):
    lines = AccountingTransactionLineSerializer(many=True, read_only=True)
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()

    class Meta:
        model = AccountingTransaction
        fields = '__all__'
        read_only_fields = [
            'transaction_no',
            'status',
            'total_debit',
            'total_credit',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
            'is_active',
            'deleted_at',
        ]


class TransactionStatusOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class TransactionStatusListSerializer(serializers.Serializer):
    default = serializers.CharField()
    statuses = TransactionStatusOptionSerializer(many=True)


class TransactionTypeListSerializer(serializers.Serializer):
    default = serializers.CharField(default=TransactionType.JOURNAL)
    types = TransactionStatusOptionSerializer(many=True)

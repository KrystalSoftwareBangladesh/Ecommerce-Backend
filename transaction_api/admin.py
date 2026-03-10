from django.contrib import admin

from transaction_api.models import (
    AccountingTransaction,
    AccountingTransactionLine,
)


class AccountingTransactionLineInline(admin.TabularInline):
    model = AccountingTransactionLine
    extra = 0


@admin.register(AccountingTransaction)
class AccountingTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_no',
        'transaction_date',
        'status',
        'total_debit',
        'total_credit',
    )
    search_fields = ('transaction_no', 'reference', 'description')
    list_filter = ('status', 'transaction_date')
    inlines = [AccountingTransactionLineInline]

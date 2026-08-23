---
name: accounting-operation
description: Implement or change anything that moves money or stock in this repository — purchases, sales, returns, cancellations, opening balances, accounting transactions and inventory movements. Use when touching purchase_api, sale_api, transaction_api, account_api or inventory_api service code.
---

# Accounting and inventory operations

The highest-risk domain in this codebase: every stock movement has an
accounting counterpart, and both must be written in the same atomic block.
Replaces the former `inventory-operation` skill.

Business rules: [docs/business-rules.md](../../../docs/business-rules.md).
Entities: [docs/domain-model.md](../../../docs/domain-model.md).

**Ask before changing any rule here.** Do not infer an accounting rule from a
single example — see
[AGENTS.md](../../../AGENTS.md#agent-behaviour-rules).

## The model

```text
ChartOfAccount  (self-nesting, AccountType: asset/liability/equity/income/expense)
      ▲
AccountingTransactionLine  (debit_amount XOR credit_amount, both ≥ 0)
      ▲
AccountingTransaction      (TransactionStatus draft/posted, TransactionType)
      ▲
Purchase.accounting_transaction / .cancellation_transaction
Sale.accounting_transaction     / .return_transaction
ChartOfAccount.opening_transaction

InventoryMovement ──> ProductVariant
    quantity (signed), movement_type, reference_type, reference_id
```

## Invariants — enforced in `transaction_api/services.py::_validate_lines`

1. At least **two** lines per transaction.
2. Each line has a debit **or** a credit, never both, never neither.
3. No negative amounts.
4. Total debit > 0 and total credit > 0.
5. **Total debit == total credit.**
6. No line may reference an inactive or soft-deleted account.

Any new transaction-producing code must go through the same validation. Do
not build `AccountingTransactionLine` rows outside a service.

## Inventory rules

Stock changes **only** through Purchase, Sale, Return or Adjustment. Every
change writes an `InventoryMovement` row — never mutate a stock figure
silently, and never delete a movement.

Current writers (the only four places movements are created):

| Where | `movement_type` | `reference_type` | quantity |
|---|---|---|---|
| `purchase_api/services.py::confirm_purchase` | `PURCHASE` | `PURCHASE` | `+item.quantity` |
| `purchase_api/services.py::cancel_purchase` | `ADJUSTMENT` | `PURCHASE` | `-item.quantity` |
| `sale_api/services.py::_deduct_sale_stock` | `SALE` | `ORDER` | negative |
| `sale_api/services.py::_restock_returned_sale` | `REFUND` | `RETURN` | positive |

`reference_id` always carries the originating `Purchase.id` / `Sale.id`.
`created_by` is always stamped.

## The pattern to follow

`confirm_purchase` is the canonical example. Every state-changing operation
does the same six things, in this order, inside one `@transaction.atomic`:

```python
@transaction.atomic
def confirm_purchase(instance, user):
    # 1. Guard the state machine
    if instance.status != PurchaseStatus.DRAFT:
        raise ValidationError("Only draft purchases can be confirmed.")
    if not instance.items.exists():
        raise ValidationError("Cannot confirm purchase with no items.")

    # 2. Validate accounts and totals
    _validate_purchase_account(instance.account)
    _validate_purchase_totals(instance)

    # 3. Guard against double-posting
    if instance.accounting_transaction_id is not None:
        raise ValidationError({'detail': '...already linked...'})

    # 4. Create the balanced accounting transaction
    accounting_transaction = _create_purchase_transaction(user, instance)

    # 5. Advance status and link, saving narrowly
    instance.status = PurchaseStatus.CONFIRMED
    instance.updated_by = user
    instance.accounting_transaction = accounting_transaction
    instance.save(update_fields=[
        'status', 'accounting_transaction', 'updated_by', 'updated_at',
    ])

    # 6. Write the inventory movements
    for item in instance.items.all():
        InventoryMovement.objects.create(
            product_variant=item.product_variant,
            quantity=item.quantity,
            movement_type=MovementType.PURCHASE,
            reference_type=ReferenceType.PURCHASE,
            reference_id=instance.id,
            created_by=user,
        )

    return instance
```

## Rules for changes

- **Posted financial records are historical.** Do not modify or delete a
  posted transaction. Reverse it with a compensating entry, the way
  `cancel_purchase` creates a separate `cancellation_transaction` and
  `_restock_returned_sale` creates a `return_transaction`.
- **Never post twice.** Always check the existing `*_transaction_id` before
  creating one.
- **Validate stock before completing a sale** —
  `sale_api/services.py::validate_stock`.
- System accounts are fetched, not created ad hoc:
  `get_or_create_sales_revenue_account`,
  `get_or_create_inventory_asset_account`,
  `get_or_create_opening_balance_equity_account`. Reuse these.
- Invoice numbers are generated server-side
  (`_generate_sale_invoice_number`, `_generate_purchase_invoice_number`) and
  must not be settable by a client.
- Amounts are `Decimal`. Never introduce a float into this path.
- Raise `rest_framework.exceptions.ValidationError` with a clear message; the
  global handler shapes the response.

## Verify

```bash
python manage.py test purchase_api sale_api transaction_api account_api \
  --settings=EcommerceBackend.test_settings
flake8
```

These four apps have the repository's most substantial test suites
(419–469 lines each). Run them before and after, and compare — some failures
are pre-existing, see [docs/testing.md](../../../docs/testing.md#known-state-of-the-suite).

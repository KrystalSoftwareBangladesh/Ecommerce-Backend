# Phase 4 — Storefront Order Creation: Revised Implementation Plan

Revised: 2026-10-13.
Audit-only. No code changes, migrations, or implementation.

---

## Approved Decisions

1. Inventory reservation at placement, deduction at confirmation.
2. Accounts Receivable + separate Shipping Revenue accounting.
3. COD collection debits the active asset account on the COD PaymentMethod.
4. Reservation expiry configurable via `CHECKOUT_RESERVATION_MINUTES` (default 30).
5. Customer order endpoints in `checkout_api`, separate from `SaleViewSet`.
6. Idempotency compares a canonical fingerprint of all meaningful request inputs.
7. Customers cancel only their own PENDING orders. Staff cancellation of confirmed orders and refunds are out of scope.
8. COD is the only supported payment method in v1.

---

## 1. Repository Findings — Verified

### 1.1 Sale model (`sale_api/models/sale.py`)

Current fields (lines 39-121): `customer` (FK, PROTECT, non-null), `payment_method` (FK, PROTECT, nullable), `account` (FK, PROTECT, nullable), `accounting_transaction` (FK, SET_NULL, nullable), `return_transaction` (FK, SET_NULL, nullable), `sale_date`, `invoice_number`, `channel` (default Walk-in), `status` (default PENDING), `subtotal_amount`, `discount_amount`, `tax_amount`, `total_amount = subtotal - discount + tax`, `notes`.

No `shipping_amount`, no `payment_status`, no `shipping_address_snapshot`, no `idempotency_key`.

### 1.2 SaleStatus (`sale_api/models/sale.py:12-32`)

Eight statuses, strictly linear: PENDING→CONFIRMED→PROCESSING→PACKAGED→SHIPPED→OUT_OF_DELIVERY→DELIVERED→RETURNED. No CANCELLED. PENDING can only go to CONFIRMED.

### 1.3 Sale services (`sale_api/services.py`)

- `create_sale()` (line 223): trusts caller-supplied `unit_price`. No inventory deduction. No accounting.
- `update_sale_status()` (line 336): CONFIRMED deducts stock + creates accounting (Dr Asset, Cr Sales Revenue). RETURNED restocks + creates reversal (Dr Sales Revenue, Cr Asset).
- `validate_stock()` (line 215): **does NOT filter `is_active=True`** on movements. Soft-deleted movements are included.
- `get_or_create_sales_revenue_account()` (line 26): uses `select_for_update()`. Looks up by name + type.

### 1.4 Sale return accounting (`sale_api/services.py:185-212`)

```python
_create_sale_return_transaction():
    DR  Sales Revenue        = total_amount
    CR  sale.account (Asset)  = total_amount
```

This reverses a single-revenue-line confirmation. With the new storefront flow (two revenue lines: product + shipping), this function would produce an incorrect reversal. **Must not be modified** — it remains correct for existing POS sales. Storefront returns will need a new function.

### 1.5 PaymentMethod (`sale_api/models/payment_method.py`)

`code` (unique), `name`, `default_account` (FK to ChartOfAccount, PROTECT, nullable), `allow_account_override` (default False). For COD, we create a PaymentMethod with code `COD`, a `default_account` pointing to a Cash/Bank asset account, and `allow_account_override=False`.

### 1.6 CartItem (`cart_api/models/cart_item.py`)

FK to `Product` (not ProductVariant), `quantity`, unique constraint on active (cart, product). `related_name="cart_items"`.

### 1.7 ProductVariant (`product_api/models/product.py:104-122`)

FK to Product (`related_name="variants"`), `sku`, `color`, `size`. Inherits `SoftDeleteModel`. No price field — pricing is on Product.

### 1.8 InventoryMovement (`inventory_api/models/inventory.py`)

FK to ProductVariant, signed `quantity`, `movement_type` (PURCHASE/SALE/REFUND/ADJUSTMENT/OPENING), `reference_type` (PURCHASE/ORDER/RETURN/MANUAL), `reference_id`. `ReferenceType.ORDER` exists.

### 1.9 Email system (`email_api/`)

`EmailService.queue()` (line 148): checks `idempotency_key` first, creates log inside `transaction.atomic()`, catches `IntegrityError` for race conditions, uses `transaction.on_commit()` to dispatch `send_email_task.delay()`. `EmailType` includes `ORDER_CONFIRMATION`, `ORDER_CANCELLED`, `ORDER_SHIPPED` but **none are in `EMAIL_TEMPLATE_REGISTRY`**.

### 1.10 Celery (`EcommerceBackend/celery.py`)

`app = Celery("EcommerceBackend")`, `autodiscover_tasks()`. Broker: Redis. `send_email_task` has `max_retries=3`, `countdown=60`.

### 1.11 Permissions (`EcommerceBackend/core/permission.py`)

`CustomPermissionAccessMixin` applies `ModelPermissionAccess` only to actions in `custom_permissions` dict. `ModelPermissionAccess` extends `DjangoModelPermissions` with per-action custom permission codenames.

---

## 2. Critical Requirements — Addressed

### 2.1 Expired reservations

**Rule:** At confirmation, revalidate every reservation. If any reservation has `status != ACTIVE` or `expires_at <= now()`, fail confirmation with a clear error. The staff user must re-attempt after the customer re-places the order (which re-reserves stock).

**Why not auto-reacquire:** Auto-extending or re-reserving during confirmation introduces a window where stock was released and re-taken by another order. The safe approach is to fail and require re-placement.

### 2.2 Accounting reconciliation

**v1 policy:** `discount_amount = 0`, `tax_amount = 0`. These fields exist on the model and are defaulted to 0. No discount or tax logic is implemented. The total formula is:

```
total_amount = subtotal_amount + shipping_amount
```

The confirmation accounting entry:
```
DR  Accounts Receivable   = subtotal_amount  (product revenue)
CR  Product Revenue        = subtotal_amount

DR  Accounts Receivable   = shipping_amount  (shipping revenue)
CR  Shipping Revenue       = shipping_amount
```

The COD collection entry:
```
DR  Cash/Bank (from PaymentMethod.default_account)  = total_amount
CR  Accounts Receivable                              = total_amount
```

**Return accounting for storefront orders:** Must reverse both revenue lines:
```
DR  Product Revenue       = subtotal_amount
DR  Shipping Revenue      = shipping_amount
CR  Accounts Receivable   = total_amount
```

The existing `_create_sale_return_transaction()` is **not modified** — it remains correct for POS sales (which have `shipping_amount=0` and use a single Sales Revenue line). A new `_create_storefront_return_transaction()` handles the two-line reversal.

### 2.3 Idempotency before cart validation

**Rule:** On every request, compute the canonical fingerprint from `shipping_address_id`, `shipping_method_id`, and `notes`. Look up `Sale.objects.filter(customer=customer, idempotency_key=key)`. If found:
- If fingerprint matches: return existing order (200). Do NOT re-validate cart.
- If fingerprint differs: return 409 Conflict.

Only if no existing order is found, proceed with cart validation and order creation.

### 2.4 Customer cancellation scope

**Rule:** Customer endpoint (`POST /api/v1/orders/{id}/cancel/`) allows cancellation only when `status == PENDING`. If status is anything else, return 400. Staff cancellation of confirmed orders and refund processing are out of scope for v1 — they will be addressed in a separate staff workflow.

### 2.5 Payment collection safety

**Rule:** `POST /api/v1/orders/{id}/mark-paid/` is permission-controlled (`collect_sale_payment` custom permission). The service:
1. `select_for_update()` on the Sale row.
2. Validate `status == DELIVERED` and `payment_status == UNPAID`.
3. Create and post accounting transaction (Dr Cash, Cr Receivable).
4. Set `payment_status = COLLECTED`.
5. All inside `transaction.atomic()`.

### 2.6 Inventory calculation correctness

**New function `get_available_stock(variant)`:**
```python
total_movements = InventoryMovement.objects.filter(
    product_variant=variant,
    is_active=True,                    # FIX: exclude soft-deleted
).aggregate(stock=Sum('quantity'))['stock'] or 0

total_reserved = InventoryReservation.objects.filter(
    product_variant=variant,
    status=ReservationStatus.ACTIVE,
    expires_at__gt=timezone.now(),
).aggregate(reserved=Sum('quantity'))['reserved'] or 0

return total_movements - total_reserved
```

The existing `validate_stock()` in `sale_api/services.py:215` is **not modified** — it remains as-is for POS. The new `get_available_stock()` is used by the storefront flow.

### 2.7 Atomic failure handling

The entire `create_order()` function runs inside `transaction.atomic()`. If any step fails (variant resolution, stock reservation, sale creation, cart status change), the entire transaction rolls back. No partial sale, items, reservations, or cart-state changes persist.

### 2.8 Email after commit

Following the established pattern in `EmailService.queue()`:
```python
transaction.on_commit(
    lambda: EmailService.queue(
        email_type=EmailType.ORDER_CONFIRMATION,
        recipient=user.email,
        context={...},
        idempotency_key=f"ORDER_CONFIRM:{sale.id}",
        related_user=user,
    )
)
```

Email failure does not roll back the order. Celery retries up to 3 times.

### 2.9 Existing POS behavior preserved

- `create_sale()` is not modified.
- `update_sale_status()` is not modified.
- `validate_stock()` is not modified.
- `_create_sale_transaction()` is not modified.
- `_create_sale_return_transaction()` is not modified.
- `SaleViewSet` queryset is not modified.
- All existing API contracts remain unchanged.

Storefront-specific logic lives entirely in `checkout_api` (new service functions, new views, new serializers).

---

## 3. Gap Analysis

| Requirement | Gap | Resolution |
|---|---|---|
| CANCELLED status | Not in SaleStatus | Add to model + transitions |
| PaymentStatus | Does not exist | New TextChoices + field on Sale |
| shipping_amount | Not on Sale model | New DecimalField |
| shipping_address_snapshot | Not on Sale model | New JSONField |
| idempotency_key | Not on Sale model | New CharField + unique_together with customer |
| InventoryReservation | Does not exist | New model in inventory_api |
| Product→Variant mapping | No resolution logic | New function in checkout service |
| Shipping Revenue account | Does not exist | New get_or_create function |
| Accounts Receivable account | Does not exist | New get_or_create function |
| COD PaymentMethod | Does not exist | Data migration or seed |
| Customer order ViewSet | Does not exist | New in checkout_api |
| Order confirmation email | Type exists, no template | Template + registry entry |
| Order cancellation email | Type exists, no template | Template + registry entry |
| Storefront return accounting | Existing function is POS-only | New function for two-line reversal |
| Reservation expiry task | Does not exist | Management command |

---

## 4. Proposed Data Model

### 4.1 Sale model changes (`sale_api/models/sale.py`)

```python
class PaymentStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    COLLECTED = 'COLLECTED', 'Collected'

class SaleStatus(models.TextChoices):
    # ... existing 8 values ...
    CANCELLED = 'CANCELLED', 'Cancelled'

SALE_STATUS_TRANSITIONS = {
    SaleStatus.PENDING: [SaleStatus.CONFIRMED, SaleStatus.CANCELLED],
    SaleStatus.CONFIRMED: [SaleStatus.PROCESSING, SaleStatus.CANCELLED],
    SaleStatus.PROCESSING: [SaleStatus.PACKAGED],
    SaleStatus.PACKAGED: [SaleStatus.SHIPPED],
    SaleStatus.SHIPPED: [SaleStatus.OUT_OF_DELIVERY],
    SaleStatus.OUT_OF_DELIVERY: [SaleStatus.DELIVERED],
    SaleStatus.DELIVERED: [SaleStatus.RETURNED],
    SaleStatus.RETURNED: [],
    SaleStatus.CANCELLED: [],
}
```

New fields on Sale:

| Field | Type | Default | Notes |
|---|---|---|---|
| `payment_status` | CharField(20) | `UNPAID` | Choices: UNPAID, COLLECTED |
| `shipping_amount` | DecimalField(12,2) | `Decimal('0.00')` | |
| `shipping_address_snapshot` | JSONField | `{}` | Frozen address at order time |
| `idempotency_key` | CharField(255) | null, blank | |

Updated Meta:
```python
unique_together = (
    ('invoice_number',),
    ('customer', 'idempotency_key'),
)
indexes = [
    Index(fields=['status']),
    Index(fields=['sale_date']),
    Index(fields=['customer', 'status']),
    Index(fields=['customer', 'payment_status']),
]
```

Updated `total_amount` formula (in the storefront service only — POS `create_sale()` is unchanged):
```python
total_amount = subtotal_amount - discount_amount + tax_amount + shipping_amount
```

For existing POS sales, `shipping_amount` defaults to 0, so `total_amount` is unchanged.

### 4.2 InventoryReservation model (new, `inventory_api/models/inventory.py`)

```python
class ReservationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    CONSUMED = 'CONSUMED', 'Consumed'
    RELEASED = 'RELEASED', 'Released'

class InventoryReservation(TimeStampedModel, UserStampedModel):
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    sale = models.ForeignKey(
        'sale_api.Sale',
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.ACTIVE,
    )
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            Index(fields=['product_variant', 'status']),
            Index(fields=['sale', 'status']),
            Index(fields=['expires_at']),
        ]
```

No EXPIRED status — stale reservations are released (set to RELEASED) by the expiry management command. This keeps the lifecycle simple: ACTIVE → CONSUMED (at confirmation) or ACTIVE → RELEASED (at cancellation or expiry).

### 4.3 Migration plan

1. `sale_api/migrations/` — add PaymentStatus, CANCELLED to SaleStatus, new fields on Sale, new indexes, new unique_together.
2. `inventory_api/migrations/` — add ReservationStatus, InventoryReservation model.
3. Data migration — create COD PaymentMethod with default Cash/Bank account, Shipping Revenue account, Accounts Receivable account.

---

## 5. Final API Contracts

### 5.1 Place order

```
POST /api/v1/checkout/confirm/
Authorization: Bearer <token>
```

Request:
```json
{
  "shipping_address_id": 12,
  "shipping_method_id": 5,
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "notes": "Please call before delivery"
}
```

Success (201):
```json
{
  "id": 1001,
  "invoice_number": "SALE-20261013-001001",
  "status": "PENDING",
  "payment_status": "UNPAID",
  "channel": "Website",
  "customer": {"id": 5, "user": {"id": 10, "username": "customer1"}},
  "items": [
    {
      "id": 501,
      "product_variant_id": 7,
      "product_name": "Wireless Mouse",
      "variant_sku": "WM-BLK-001",
      "quantity": 2,
      "unit_price": "500.00",
      "line_total": "1000.00"
    }
  ],
  "shipping_address": {
    "first_name": "John", "last_name": "Doe",
    "address_1": "123 Main St", "city": "Dhaka",
    "postcode": "1205", "country": "Bangladesh",
    "phone": "+8801700000000"
  },
  "pricing": {
    "subtotal": "1000.00",
    "shipping_charge": "60.00",
    "discount_total": "0.00",
    "tax_total": "0.00",
    "grand_total": "1060.00"
  },
  "shipping_method": {"id": 5, "name": "Standard Delivery", "code": "standard"},
  "notes": "Please call before delivery",
  "created_at": "2026-10-13T14:30:00+06:00"
}
```

Validation failure (200):
```json
{"is_valid": false, "errors": ["Insufficient stock for Wireless Mouse (requested: 2, available: 1)."]}
```

Idempotent return (200):
```json
{"id": 1001, "invoice_number": "SALE-20261013-001001", "status": "PENDING", "message": "Order already exists."}
```

Conflict (409):
```json
{"detail": "An order with this idempotency key already exists with different parameters."}
```

### 5.2 Order history

```
GET /api/v1/orders/
Authorization: Bearer <token>
```

Filters: `status`, `payment_status`, `start_date`, `end_date`.
Ordering: `-created_at` (default).
Pagination: standard project pagination.
Queryset: `Sale.objects.filter(customer__user=request.user, is_active=True)`.

Response (200):
```json
{
  "count": 3, "total_pages": 1, "current_page": 1,
  "next": null, "previous": null,
  "results": [
    {
      "id": 1001, "invoice_number": "SALE-20261013-001001",
      "status": "PENDING", "payment_status": "UNPAID",
      "total_amount": "1060.00", "item_count": 1,
      "created_at": "2026-10-13T14:30:00+06:00"
    }
  ]
}
```

### 5.3 Order detail

```
GET /api/v1/orders/{id}/
Authorization: Bearer <token>
```

Returns 404 if order does not belong to authenticated customer. Same structure as placement response. Does NOT expose `account`, `accounting_transaction`, `return_transaction`, `created_by`, `updated_by`.

### 5.4 Cancel order

```
POST /api/v1/orders/{id}/cancel/
Authorization: Bearer <token>
```

Request: empty body.

Success (200):
```json
{"id": 1001, "status": "CANCELLED", "message": "Order cancelled successfully."}
```

Repeated cancel (200):
```json
{"id": 1001, "status": "CANCELLED", "message": "Order is already cancelled."}
```

Non-pending order (400):
```json
{"detail": "Only pending orders can be cancelled."}
```

### 5.5 Mark COD payment collected

```
POST /api/v1/sales/{id}/mark-paid/
Authorization: Bearer <token>
```

Permission: `collect_sale_payment` custom permission on `sale_api.Sale`.

Request: empty body.

Success (200):
```json
{"id": 1001, "status": "DELIVERED", "payment_status": "COLLECTED", "message": "Payment collected."}
```

Already collected (400):
```json
{"detail": "Payment has already been collected."}
```

Wrong status (400):
```json
{"detail": "Order must be delivered before payment can be collected."}
```

---

## 6. Transactional Workflows

### 6.1 Place order

```
BEGIN TRANSACTION (atomic)
  1. Idempotency check:
     obj = Sale.objects.filter(customer=customer, idempotency_key=key).first()
     if obj:
       if fingerprint(obj) == fingerprint(request): return obj (200)
       else: raise 409
  2. get_active_cart(user) → cart (or raise "No active cart")
  3. list_cart_items(cart) → items
  4. validate products (is_active, price > 0)
  5. FOR EACH item:
     a. resolve_variant(product) → variant (auto-select or raise)
     b. re-read price from product.current_selling_price
  6. validate_address(user, address_id) → address
  7. resolve_shipping(address, method_id, subtotal) → shipping
  8. Reserve inventory:
     FOR EACH item:
       SELECT ... FOR UPDATE on ProductVariant row
       available = get_available_stock(variant)
       if available < qty: raise "Insufficient stock"
       InventoryReservation.objects.create(variant, sale, qty, ACTIVE, expires_at)
  9. Create Sale (PENDING, UNPAID, Website, idempotency_key, shipping_amount,
     shipping_address_snapshot)
  10. Create SaleItems (unit_price from product.current_selling_price)
  11. Compute totals: subtotal, shipping, grand total
  12. Mark cart CHECKED_OUT
COMMIT TRANSACTION
  13. transaction.on_commit: queue ORDER_CONFIRMATION email
  14. Return 201
```

### 6.2 Cancel order (customer)

```
BEGIN TRANSACTION (atomic)
  1. Sale.objects.select_for_update().get(id=id, customer__user=user)
  2. if sale.status != PENDING: raise "Only pending orders can be cancelled"
  3. Release reservations:
     InventoryReservation.objects.filter(sale=sale, status=ACTIVE).update(status=RELEASED)
  4. sale.status = CANCELLED
  5. sale.save()
COMMIT TRANSACTION
  6. transaction.on_commit: queue ORDER_CANCELLED email
  7. Return 200
```

### 6.3 Confirm order (staff — existing `update_sale_status`)

The existing `update_sale_status()` handles PENDING→CONFIRMED. It must be extended (not replaced) to handle storefront orders:

```
BEGIN TRANSACTION (atomic)
  1. Validate transition allowed
  2. If sale has reservations (storefront order):
     a. FOR EACH reservation where status=ACTIVE and expires_at > now():
        - SELECT ... FOR UPDATE on ProductVariant row
        - available = get_available_stock(variant)  # movements - other active reservations
        - if available < reservation.qty: raise "Stock no longer available"
        - InventoryMovement.objects.create(qty=-qty, SALE, ORDER, sale.id)
        - reservation.status = CONSUMED
     b. FOR EACH reservation where status=ACTIVE and expires_at <= now():
        - raise "Reservation expired. Order must be re-placed."
  3. If sale has NO reservations (POS order):
     - Existing _deduct_sale_stock() logic (unchanged)
  4. Resolve account (existing logic)
  5. Create accounting transaction:
     If sale.shipping_amount > 0 (storefront):
       DR Accounts Receivable = subtotal_amount
       CR Product Revenue      = subtotal_amount
       DR Accounts Receivable  = shipping_amount
       CR Shipping Revenue     = shipping_amount
     Else (POS, unchanged):
       DR sale.account         = total_amount
       CR Sales Revenue        = total_amount
  6. POST accounting transaction
  7. Save sale: status=CONFIRMED, account, accounting_transaction
COMMIT TRANSACTION
```

**Implementation approach:** Add a conditional branch in `update_sale_status()` that detects whether the sale has reservations (storefront) vs. not (POS). The POS path is completely unchanged. The storefront path uses the new reservation-aware logic.

### 6.4 Collect COD payment

```
BEGIN TRANSACTION (atomic)
  1. sale = Sale.objects.select_for_update().get(id=id)
  2. Validate: sale.status == DELIVERED, sale.payment_status == UNPAID
  3. cash_account = sale.payment_method.default_account (must be active ASSET)
  4. receivable = get_or_create_accounts_receivable_account()
  5. Create accounting transaction:
     DR cash_account          = total_amount
     CR receivable            = total_amount
     type=RECEIPT, reference=invoice_number
  6. POST accounting transaction
  7. sale.payment_status = COLLECTED
  8. sale.save(update_fields=['payment_status', 'updated_at'])
COMMIT TRANSACTION
```

### 6.5 Failure boundaries

| Failure | Rollback scope | Side effects |
|---|---|---|
| Validation error before reservation | Entire transaction | None |
| Stock reservation fails | Entire transaction | None |
| Sale creation fails | Entire transaction | None |
| Cart status update fails | Entire transaction | None |
| Email queue fails after commit | N/A (after commit) | Order exists, email logged as PENDING, Celery retries |
| Accounting fails at confirmation | Entire transaction | Sale stays PENDING, reservations stay ACTIVE |
| Accounting fails at COD collection | Entire transaction | Payment stays UNPAID |

---

## 7. Accounting Design

### 7.1 Accounts

| Account | Type | Created by |
|---|---|---|
| Sales Revenue | REVENUE | Existing (`get_or_create_sales_revenue_account()`) |
| Shipping Revenue | REVENUE | New (`get_or_create_shipping_revenue_account()`) |
| Accounts Receivable | ASSET | New (`get_or_create_accounts_receivable_account()`) |
| Cash/Bank (COD) | ASSET | Existing or seeded via data migration |

### 7.2 Entries by event

| Event | Debit | Credit | Amount |
|---|---|---|---|
| Order placed | — | — | None |
| Order confirmed (storefront) | Accounts Receivable | Product Revenue | subtotal |
| Order confirmed (storefront) | Accounts Receivable | Shipping Revenue | shipping |
| Order confirmed (POS) | sale.account | Sales Revenue | total (unchanged) |
| COD collected | Cash/Bank | Accounts Receivable | total |
| Cancel from PENDING | — | — | None |
| Cancel from CONFIRMED | Product Revenue | Accounts Receivable | subtotal |
| Cancel from CONFIRMED | Shipping Revenue | Accounts Receivable | shipping |
| Return (storefront) | Product Revenue | Accounts Receivable | subtotal |
| Return (storefront) | Shipping Revenue | Accounts Receivable | shipping |
| Return (POS) | Sales Revenue | sale.account | total (unchanged) |

### 7.3 Return accounting — existing vs. storefront

The existing `_create_sale_return_transaction()` reverses a single Sales Revenue line against `sale.account`. For POS sales (where `shipping_amount=0` and the confirmation used a single Sales Revenue line), this remains correct.

For storefront sales (where confirmation used Product Revenue + Shipping Revenue against Accounts Receivable), a new `_create_storefront_return_transaction()` is needed:

```python
def _create_storefront_return_transaction(user, sale):
    product_revenue = get_or_create_sales_revenue_account(user=user)
    shipping_revenue = get_or_create_shipping_revenue_account(user=user)
    receivable = get_or_create_accounts_receivable_account(user=user)
    lines = [
        {'account': product_revenue, 'debit_amount': sale.subtotal_amount, 'credit_amount': 0},
        {'account': shipping_revenue, 'debit_amount': sale.shipping_amount, 'credit_amount': 0},
        {'account': receivable, 'debit_amount': 0, 'credit_amount': sale.total_amount},
    ]
    txn = create_transaction(user, {'transaction_date': sale.sale_date, 'transaction_type': TransactionType.ADJUSTMENT, 'reference': ..., 'description': ..., 'lines': lines})
    return post_transaction(user, txn)
```

The `update_sale_status()` RETURNED branch detects which function to call based on whether the sale has `shipping_amount > 0` or has reservations.

---

## 8. Inventory Design

### 8.1 Reservation lifecycle

```
Placement:  ACTIVE
Confirmation: ACTIVE → CONSUMED (stock deducted via InventoryMovement)
Cancellation: ACTIVE → RELEASED
Expiry:     ACTIVE → RELEASED (management command)
```

### 8.2 Concurrency

At reservation time:
```python
with transaction.atomic():
    variant = ProductVariant.objects.select_for_update().get(id=variant_id)
    available = get_available_stock(variant)
    if available < quantity:
        raise ValidationError(...)
    InventoryReservation.objects.create(...)
```

At confirmation time:
```python
with transaction.atomic():
    for reservation in sale.reservations.filter(status=ACTIVE):
        if reservation.expires_at <= now():
            raise ValidationError("Reservation expired")
        variant = ProductVariant.objects.select_for_update().get(id=reservation.product_variant_id)
        # Re-verify stock (another order may have consumed stock after reservation)
        available = get_available_stock(variant)
        if available < reservation.quantity:
            raise ValidationError("Stock no longer available")
        # Deduct: create movement (counts against stock)
        InventoryMovement.objects.create(variant, -reservation.quantity, SALE, ORDER, sale.id)
        reservation.status = CONSUMED
        reservation.save()
```

**Key insight:** `get_available_stock()` subtracts ACTIVE reservations from movements. At confirmation, we need to check that the variant still has enough stock *excluding our own reservation*. The correct check is:

```python
# available = movements - (other active reservations)
# Our reservation is ACTIVE, so it's included in total_reserved.
# After we create the movement, our reservation becomes CONSUMED.
# The movement and the consumed reservation cancel out in the stock calc.
other_reserved = InventoryReservation.objects.filter(
    product_variant=variant,
    status=ReservationStatus.ACTIVE,
    expires_at__gt=now(),
).exclude(sale=sale).aggregate(r=Sum('quantity'))['r'] or 0

total_movements = InventoryMovement.objects.filter(
    product_variant=variant, is_active=True,
).aggregate(s=Sum('quantity'))['s'] or 0

available_excluding_ours = total_movements - other_reserved
if available_excluding_ours < reservation.quantity:
    raise ValidationError(...)
```

### 8.3 Expiry management command

`inventory_api/management/commands/expire_reservations.py`:
```python
InventoryReservation.objects.filter(
    status=ReservationStatus.ACTIVE,
    expires_at__lte=timezone.now(),
).update(status=ReservationStatus.RELEASED)
```

Run via cron or scheduled Celery beat task. Frequency: every 5 minutes.

### 8.4 get_available_stock()

```python
def get_available_stock(product_variant):
    total = InventoryMovement.objects.filter(
        product_variant=product_variant,
        is_active=True,
    ).aggregate(s=Sum('quantity'))['s'] or 0
    reserved = InventoryReservation.objects.filter(
        product_variant=product_variant,
        status=ReservationStatus.ACTIVE,
        expires_at__gt=timezone.now(),
    ).aggregate(r=Sum('quantity'))['r'] or 0
    return total - reserved
```

---

## 9. Implementation Phases

### Phase 4.1: Model changes

Files:
- `sale_api/models/sale.py` — add PaymentStatus, CANCELLED, new fields, new indexes
- `inventory_api/models/inventory.py` — add ReservationStatus, InventoryReservation
- `inventory_api/models/__init__.py` — export new models
- `sale_api/models/__init__.py` — export PaymentStatus
- `sale_api/admin.py` — register new fields in admin
- `inventory_api/admin.py` — register InventoryReservation in admin

Generate migrations: `makemigrations sale_api inventory_api`.

Dependencies: none.

### Phase 4.2: Account infrastructure

Files:
- `sale_api/services.py` — add `get_or_create_shipping_revenue_account()`, `get_or_create_accounts_receivable_account()`, `_create_storefront_return_transaction()`
- `sale_api/admin.py` — no changes needed

Dependencies: Phase 4.1.

### Phase 4.3: Inventory reservation service

Files:
- `inventory_api/services/reservation.py` (new) — `reserve_stock()`, `release_reservations()`, `consume_reservations()`, `get_available_stock()`
- `inventory_api/services/__init__.py` — re-export
- `inventory_api/management/commands/expire_reservations.py` (new)

Dependencies: Phase 4.1.

### Phase 4.4: Sale status transitions update

Files:
- `sale_api/services.py` — extend `update_sale_status()` CONFIRMED branch to handle reservations and storefront accounting; extend RETURNED branch to call `_create_storefront_return_transaction()` when applicable

Dependencies: Phases 4.1, 4.2, 4.3.

### Phase 4.5: Order creation service

Files:
- `checkout_api/services/order.py` (new) — `create_order()`, `cancel_order()`, `_resolve_variant()`, `_snapshot_address()`, `_build_idempotency_fingerprint()`
- `checkout_api/services/__init__.py` — re-export

Dependencies: Phases 4.1, 4.2, 4.3, 4.4.

### Phase 4.6: Order serializers

Files:
- `checkout_api/serializers/order.py` (new) — `OrderCreateSerializer`, `OrderDetailSerializer`, `OrderListSerializer`
- `checkout_api/serializers/__init__.py` — re-export

Dependencies: Phase 4.5.

### Phase 4.7: Order views and URLs

Files:
- `checkout_api/views/v1/order.py` (new) — `CheckoutConfirmView`, `CustomerOrderViewSet`, `CustomerOrderCancelView`
- `checkout_api/views/v1/__init__.py` — re-export
- `checkout_api/urls/v1.py` — add order URLs
- `sale_api/views/v1/sale.py` — add `mark_cod_paid` action
- `sale_api/urls/v1.py` — no changes (router auto-registers the action)

Dependencies: Phase 4.6.

### Phase 4.8: Permissions

Files:
- `checkout_api/permissions.py` (new) — `CustomerOrderPermission`
- `sale_api/views/v1/sale.py` — add `custom_permissions = {"mark_cod_paid": "collect_sale_payment"}`
- Data migration — create `collect_sale_payment` permission on `sale_api.Sale`

Dependencies: Phase 4.7.

### Phase 4.9: Email integration

Files:
- `email_api/constants.py` — add ORDER_CONFIRMATION, ORDER_CANCELLED to EMAIL_TEMPLATE_REGISTRY
- `email_api/templates/emails/order_confirmation.html` (new)
- `email_api/templates/emails/order_confirmation.txt` (new)
- `email_api/templates/emails/order_cancelled.html` (new)
- `email_api/templates/emails/order_cancelled.txt` (new)
- `checkout_api/services/order.py` — add `transaction.on_commit()` email calls

Dependencies: Phase 4.5.

### Phase 4.10: Data migration

Files:
- `sale_api/migrations/` — data migration to create:
  - COD PaymentMethod (code='COD', name='Cash on Delivery')
  - Cash/Bank ChartOfAccount (type=ASSET, linked to COD PaymentMethod)
  - Accounts Receivable ChartOfAccount (type=ASSET)
  - Shipping Revenue ChartOfAccount (type=REVENUE)

Dependencies: Phase 4.1.

### Phase 4.11: Tests

Files:
- `checkout_api/tests.py` — extend with order tests
- `inventory_api/tests.py` — reservation tests
- `sale_api/tests.py` — storefront confirmation/collection tests

Dependencies: all previous phases.

---

## 10. Test Matrix

### Order placement
- Valid order: 201, correct totals, cart CHECKED_OUT, reservations created
- Empty cart: 200 with `is_valid: false`
- Inactive product: 200 with error
- Zero-price product: 200 with error
- Single variant auto-select: resolves correctly
- Multiple variants: 200 with error
- No active variants: 200 with error
- Insufficient stock: 200 with error
- Price re-read: backend price used, not frontend
- Channel hardcoded to Website

### Idempotency
- Same key, same request: returns existing order (200)
- Same key, different fingerprint: 409 Conflict
- Missing key: 400

### Cancellation
- Cancel PENDING order: status→CANCELLED, reservations released
- Cancel non-PENDING: 400
- Cancel already cancelled: 200 idempotent
- Cancel other user's order: 404
- Reservations actually released: stock becomes available again

### COD collection
- Valid collection: payment_status→COLLECTED, accounting created
- Already collected: 400
- Wrong status: 400
- Permission denied: 403
- Concurrent collection: second request fails (select_for_update)

### Inventory
- Reservation blocks concurrent over-reservation
- Expired reservation at confirmation: fails with clear error
- Available stock excludes active reservations
- Available stock excludes soft-deleted movements
- Stock consumed at confirmation: movement created, reservation CONSUMED
- Stock released at cancellation: reservation RELEASED

### Accounting
- Confirmation: Dr Receivable, Cr Product Revenue + Shipping Revenue
- COD collection: Dr Cash, Cr Receivable
- Return: Dr Product Revenue + Shipping Revenue, Cr Receivable
- POS flow unchanged: Dr Asset, Cr Sales Revenue (no shipping line)
- No premature cash entry at placement or confirmation

### Email
- ORDER_CONFIRMATION sent after commit
- ORDER_CANCELLED sent after commit
- Email failure does not rollback order
- Idempotency key prevents duplicate emails

### Customer order isolation
- Customer A cannot see Customer B's orders
- Customer detail returns 404 for other customer's order
- Order list scoped to authenticated customer

---

## 11. Risks and Unresolved Decisions

### Risk 1: Stock consumed between reservation and confirmation

Another order could consume stock after our reservation but before confirmation. **Mitigation:** At confirmation, re-verify available stock excluding our own reservation. If insufficient, fail with clear error.

### Risk 2: Reservation expiry during confirmation

If a reservation expires between the availability check and the confirmation commit, the confirmation should fail. **Mitigation:** Check `expires_at > now()` as part of the confirmation transaction. Since we hold `select_for_update()` on the variant, no other transaction can modify the reservation during this window.

### Risk 3: Existing return-accounting breakage

The existing `_create_sale_return_transaction()` reverses Sales Revenue against `sale.account`. For storefront orders where `sale.account = Accounts Receivable` and revenue was split across two accounts, this would produce an incorrect reversal. **Mitigation:** The RETURNED branch in `update_sale_status()` detects storefront orders (by checking `shipping_amount > 0` or existence of reservations) and calls `_create_storefront_return_transaction()` instead.

### Risk 4: POS `validate_stock()` includes soft-deleted movements

The existing `validate_stock()` at `sale_api/services.py:215` does not filter `is_active=True`. This is a pre-existing bug. **Mitigation:** Do not fix in this phase. The new `get_available_stock()` correctly filters. Document the bug for a future cleanup.

### Unresolved Decision A: Management command scheduling

The `expire_reservations` management command needs to run periodically. **Recommendation:** Add a Celery beat schedule entry in settings.py, or document it as a cron job. **Question:** Which approach?

### Unresolved Decision B: Order detail serializer fields

Which fields should the customer-facing order detail expose? **Proposal:** id, invoice_number, status, payment_status, channel, items (with variant info), shipping_address (snapshot), pricing breakdown, shipping_method, notes, created_at. **Question:** Any additions or removals?

---

## 12. Remaining Approvals

1. **Management command scheduling** — Celery beat or cron for `expire_reservations`?
2. **Order detail fields** — Confirm the proposed field list for customer-facing order detail.
3. **Return flow scope** — The RETURNED transition currently exists in the POS flow. Should storefront orders support RETURNED via staff, or is that out of scope for v1?

## Recommended First Phase

**Phase 4.1: Model changes** — Add PaymentStatus, CANCELLED, new Sale fields, InventoryReservation, and generate migrations. This is the foundation all other phases depend on and can be reviewed independently before any service logic is built.
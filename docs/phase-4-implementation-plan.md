# Phase 4 — Storefront Order Creation: Finalized Implementation Plan

Finalized: 2026-10-13.
Documentation only. No code changes, migrations, or implementation.

---

## Approved Decisions

1. Reserve inventory at order placement; deduct at confirmation.
2. Reservation expiry: `CHECKOUT_RESERVATION_MINUTES`, default 30.
3. Celery Beat runs reservation cleanup every 5 minutes.
4. Accounting uses Accounts Receivable, Product Revenue, and separate Shipping Revenue.
5. COD collection debits the active asset account configured on the COD PaymentMethod.
6. Customer order endpoints live in `checkout_api`.
7. Idempotency uses a durable canonical fingerprint of all meaningful request inputs.
8. Customers may cancel only their own PENDING orders.
9. Storefront returns are out of scope for v1 and must be blocked.
10. COD is the only supported payment method for v1.
11. Order detail includes items, address, pricing, method, notes, timestamps, payment status, and order status.

---

## Mandatory Technical Corrections

These corrections override any conflicting statements in the sections below.

### T1. Create Sale before InventoryReservation

The `InventoryReservation.sale` FK is non-nullable (`on_delete=CASCADE`). The Sale row must exist in the database before any reservation row can reference it. The correct sequence inside a single `transaction.atomic()` block is: create the Sale, then create reservations, then mark the cart. If any step fails, the entire transaction rolls back.

### T2. Identify storefront orders by `channel=WEBSITE`

Never infer storefront origin from `shipping_amount > 0` or from the existence of reservations. Use the explicit, stable field `sale.channel == Sale.SaleChannel.WEBSITE`. This is the canonical discriminator between POS and storefront orders throughout confirmation, return-blocking, and accounting logic.

### T3. Preserve existing POS behavior

The existing `create_sale()`, `update_sale_status()` POS path, `validate_stock()`, `_create_sale_transaction()`, `_create_sale_return_transaction()`, and `SaleViewSet` queryset are not modified. Storefront-specific logic uses a separate branch in `update_sale_status()` keyed on `channel == WEBSITE`. Storefront returns are blocked entirely — the RETURNED transition is not allowed for `channel == WEBSITE` orders in v1.

### T4. Account provisioning must inspect and reuse

Account lookup functions must first check for an existing active, non-deleted account with the expected name and type. If found, reuse it. If not found, create it. If found but inactive or deleted, reactivate it (following the pattern in `get_or_create_sales_revenue_account()`). Never blindly create duplicates. If a required account cannot be provisioned (e.g., database constraint violation from a concurrent insert), the function must raise a clear `ValidationError`, not silently create a duplicate or repurpose an unrelated account.

### T5. Persist fingerprint on Sale; recover from concurrent conflicts

The canonical fingerprint is stored on `Sale.idempotency_key`. The unique constraint is `(customer, idempotency_key)`. On concurrent inserts with the same key, the database raises `IntegrityError`. The service catches this, fetches the existing order by `(customer, idempotency_key)`, compares the fingerprint, and returns the existing order for a match or raises HTTP 409 for a mismatch. This mirrors the pattern in `EmailService.queue()`.

### T6. Check idempotency before requiring an active cart

The idempotency lookup happens first. If an existing order matches the fingerprint, return it immediately without touching the cart. This ensures retries work even after the original request checked out the cart.

### T7. Release reservations safely; make expiry/cancellation/confirmation idempotent

- Cancellation: `InventoryReservation.objects.filter(sale=sale, status=ACTIVE).update(status=RELEASED)` is idempotent — running it twice changes zero rows the second time.
- Expiry: `filter(status=ACTIVE, expires_at__lte=now()).update(status=RELEASED)` is idempotent.
- Confirmation: `select_for_update()` on each variant row prevents concurrent confirmation of the same order. Re-checking `status=ACTIVE` and `expires_at > now()` on each reservation prevents double-consumption.

### T8. Stock availability must exclude expired reservations and account for competing reservations

`get_available_stock(variant)` = movements (`is_active=True`) minus active, non-expired reservations. At confirmation time, the current order's own reservations must be excluded from the competing-reservation count so the check verifies that *other* customers' reservations do not consume the stock we are about to deduct.

### T9. Order creation uses server-side data only

Prices re-read from `Product.current_selling_price`. Variant resolved server-side (single active variant auto-select). Shipping revalidated (address ownership, zone match, rate lookup). All totals recalculated. The entire operation is atomic — any failure rolls back all changes.

### T10. No cash recognition at confirmation; COD collection is staff-only

Confirmation creates receivable-based entries (Dr Accounts Receivable, Cr Revenue). Cash is recorded only at COD collection. Collection requires: staff authorization (`collect_sale_payment` permission), `status == DELIVERED`, `payment_status == UNPAID`, and an active asset account on the PaymentMethod. The entire collection operation is atomic with `select_for_update()` on the Sale row.

### T11. Migrations must be safe for existing deployments

New fields have defaults that preserve existing data (`shipping_amount=0`, `payment_status=UNPAID`, `shipping_address_snapshot={}`, `idempotency_key=null`). The CANCELLED status is additive. The new unique_together `(customer, idempotency_key)` only constrains rows where `idempotency_key IS NOT NULL`. Existing POS API behavior and accounting semantics are unchanged.

### T12. Email after commit

`transaction.on_commit()` queues the Celery task. Email failure does not roll back the committed order. Celery retries up to 3 times with 60-second countdown.

### T13. Celery Beat must be deployed

The reservation expiry schedule must be configured in `settings.py` with `CELERY_BEAT_SCHEDULE` and a Celery Beat process must be running in production. Documenting a cron job alone is insufficient.

---

## 1. Repository Findings — Verified

### 1.1 Sale model (`sale_api/models/sale.py`)

Current fields (lines 39-121): `customer` (FK, PROTECT, non-null), `payment_method` (FK, PROTECT, nullable), `account` (FK, PROTECT, nullable), `accounting_transaction` (FK, SET_NULL, nullable), `return_transaction` (FK, SET_NULL, nullable), `sale_date`, `invoice_number`, `channel` (default Walk-in), `status` (default PENDING), `subtotal_amount`, `discount_amount`, `tax_amount`, `total_amount = subtotal - discount + tax`, `notes`.

No `shipping_amount`, no `payment_status`, no `shipping_address_snapshot`, no `idempotency_key`.

### 1.2 SaleStatus (`sale_api/models/sale.py:12-32`)

Eight statuses, strictly linear: PENDING→CONFIRMED→PROCESSING→PACKAGED→SHIPPED→OUT_OF_DELIVERY→DELIVERED→RETURNED. No CANCELLED. PENDING can only go to CONFIRMED.

### 1.3 SaleChannel (`sale_api/models/sale.py:40-46`)

Choices: Walk-in, Facebook, Phone, **Website**, Instagram, WhatsApp. `WEBSITE` is the canonical discriminator for storefront orders.

### 1.4 Sale services (`sale_api/services.py`)

- `create_sale()` (line 223): trusts caller-supplied `unit_price`. No inventory deduction. No accounting.
- `update_sale_status()` (line 336): CONFIRMED deducts stock + creates accounting (Dr Asset, Cr Sales Revenue). RETURNED restocks + creates reversal (Dr Sales Revenue, Cr Asset).
- `validate_stock()` (line 215): **does NOT filter `is_active=True`** on movements. Soft-deleted movements are included. Pre-existing bug; not fixed in this phase.
- `get_or_create_sales_revenue_account()` (line 26): uses `select_for_update()`. Looks up by name + type. Reactivates if inactive/deleted. Creates if missing.

### 1.5 Sale return accounting (`sale_api/services.py:185-212`)

```python
_create_sale_return_transaction():
    DR  Sales Revenue        = total_amount
    CR  sale.account (Asset)  = total_amount
```

Reverses a single-revenue-line confirmation. Correct for POS sales. **Must not be modified.** Storefront returns are blocked in v1.

### 1.6 PaymentMethod (`sale_api/models/payment_method.py`)

`code` (unique), `name`, `default_account` (FK to ChartOfAccount, PROTECT, nullable), `allow_account_override` (default False). For COD, a PaymentMethod with code `COD` is created via data migration, with `default_account` pointing to a Cash/Bank asset account and `allow_account_override=False`.

### 1.7 CartItem (`cart_api/models/cart_item.py`)

FK to `Product` (not ProductVariant), `quantity`, unique constraint on active (cart, product). `related_name="cart_items"`.

### 1.8 ProductVariant (`product_api/models/product.py:104-122`)

FK to Product (`related_name="variants"`), `sku`, `color`, `size`. Inherits `SoftDeleteModel`. No price field — pricing is on Product. A product can have zero, one, or many active variants. No "default variant" concept exists.

### 1.9 InventoryMovement (`inventory_api/models/inventory.py`)

FK to ProductVariant, signed `quantity`, `movement_type` (PURCHASE/SALE/REFUND/ADJUSTMENT/OPENING), `reference_type` (PURCHASE/ORDER/RETURN/MANUAL), `reference_id`. `ReferenceType.ORDER` exists.

### 1.10 Email system (`email_api/`)

`EmailService.queue()` (line 148): checks `idempotency_key` first, creates log inside `transaction.atomic()`, catches `IntegrityError` for race conditions, uses `transaction.on_commit()` to dispatch `send_email_task.delay()`. `EmailType` includes `ORDER_CONFIRMATION`, `ORDER_CANCELLED`, `ORDER_SHIPPED` but **none are in `EMAIL_TEMPLATE_REGISTRY`**.

### 1.11 Celery (`EcommerceBackend/celery.py`)

`app = Celery("EcommerceBackend")`, `autodiscover_tasks()`. Broker: Redis. `send_email_task` has `max_retries=3`, `countdown=60`.

### 1.12 Permissions (`EcommerceBackend/core/permission.py`)

`CustomPermissionAccessMixin` applies `ModelPermissionAccess` only to actions in `custom_permissions` dict. `ModelPermissionAccess` extends `DjangoModelPermissions` with per-action custom permission codenames.

---

## 2. Gap Analysis

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
| COD PaymentMethod | Does not exist | Data migration |
| Cash/Bank account for COD | Must be provisioned carefully | Data migration, inspect existing |
| Customer order ViewSet | Does not exist | New in checkout_api |
| Order confirmation email | Type exists, no template | Template + registry entry |
| Order cancellation email | Type exists, no template | Template + registry entry |
| Storefront return blocking | No mechanism | Block RETURNED for channel=WEBSITE |
| Reservation expiry task | Does not exist | Management command + Celery Beat |
| collect_sale_payment permission | Does not exist | Data migration |

---

## 3. Proposed Data Model

### 3.1 Sale model changes (`sale_api/models/sale.py`)

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

Updated `total_amount` formula (storefront service only — POS `create_sale()` unchanged):
```python
total_amount = subtotal_amount - discount_amount + tax_amount + shipping_amount
```

For existing POS sales, `shipping_amount` defaults to 0, so `total_amount` is unchanged.

### 3.2 InventoryReservation model (new, `inventory_api/models/inventory.py`)

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

No EXPIRED status — stale reservations are set to RELEASED by the expiry command. Lifecycle: ACTIVE → CONSUMED (confirmation) or ACTIVE → RELEASED (cancellation or expiry).

### 3.3 Migration plan

1. `sale_api/migrations/` — add PaymentStatus, CANCELLED to SaleStatus, new fields on Sale, new indexes, new unique_together.
2. `inventory_api/migrations/` — add ReservationStatus, InventoryReservation model.
3. `sale_api/migrations/` — data migration:
   - Create `collect_sale_payment` permission on `sale_api.Sale`.
   - Inspect for existing Cash/Bank ASSET account; create only if none suitable exists.
   - Create Accounts Receivable ASSET account (inspect first).
   - Create Shipping Revenue REVENUE account (inspect first).
   - Create COD PaymentMethod (code='COD'), link to Cash/Bank account.
4. `EcommerceBackend/settings.py` — add `CELERY_BEAT_SCHEDULE` entry for reservation expiry.

---

## 4. Final API Contracts

### 4.1 Place order

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

**Fields never trusted from the frontend:** product prices, variant mapping, subtotal, shipping charge, discount, tax, grand total, order status, payment status, invoice number, channel.

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

### 4.2 Order history

```
GET /api/v1/orders/
Authorization: Bearer <token>
```

Filters: `status`, `payment_status`, `start_date`, `end_date`.
Ordering: `-created_at` (default).
Pagination: standard project pagination (PageNumberPagination, default 10).
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

### 4.3 Order detail

```
GET /api/v1/orders/{id}/
Authorization: Bearer <token>
```

Returns 404 if order does not belong to authenticated customer.

Response fields: `id`, `invoice_number`, `status`, `payment_status`, `channel`, `customer`, `items` (with variant info), `shipping_address` (snapshot), `pricing` (breakdown), `shipping_method`, `notes`, `created_at`, `updated_at`, `allowed_next_statuses`.

Fields NOT exposed: `account`, `accounting_transaction`, `return_transaction`, `created_by`, `updated_by`, `deleted_at`.

### 4.4 Cancel order

```
POST /api/v1/orders/{id}/cancel/
Authorization: Bearer <token>
```

Request: empty body.

Success (200):
```json
{"id": 1001, "status": "CANCELLED", "message": "Order cancelled successfully."}
```

Repeated cancel (200 — idempotent):
```json
{"id": 1001, "status": "CANCELLED", "message": "Order is already cancelled."}
```

Non-pending order (400):
```json
{"detail": "Only pending orders can be cancelled."}
```

Other user's order (404): not found.

### 4.5 Mark COD payment collected

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

Permission denied (403):
```json
{"detail": "You do not have permission to perform this action."}
```

---

## 5. Transactional Workflows

### 5.1 Place order

```
BEGIN TRANSACTION (atomic)
  1. Idempotency check (BEFORE cart validation):
     existing = Sale.objects.filter(
       customer=customer, idempotency_key=fingerprint
     ).first()
     if existing:
       if fingerprint_matches(existing, request):
         return existing (200)    # idempotent return
       else:
         raise 409 Conflict
  2. get_active_cart(user) → cart (or raise "No active cart")
  3. list_cart_items(cart) → items
  4. validate products (is_active, price > 0)
  5. FOR EACH item:
     a. resolve_variant(product) → variant
        - product.variants.filter(is_active=True, deleted_at__isnull=True)
        - count == 1: auto-select
        - count == 0: raise "no available variants"
        - count > 1: raise "multiple variants, please select one"
     b. re-read price: product.current_selling_price
  6. validate_address(user, address_id) → address
  7. resolve_shipping(address, method_id, subtotal) → shipping
  8. Create Sale (T1: Sale must exist before reservations):
     Sale.objects.create(
       customer=customer, status=PENDING, payment_status=UNPAID,
       channel=WEBSITE, idempotency_key=fingerprint,
       shipping_amount=shipping.charge,
       shipping_address_snapshot=snapshot(address),
       sale_date=today, notes=notes,
       subtotal_amount=subtotal, total_amount=grand_total,
       created_by=user, updated_by=user,
     )
  9. Create SaleItems (unit_price from product.current_selling_price)
  10. Reserve inventory:
      FOR EACH item:
        variant = ProductVariant.objects.select_for_update().get(id=variant_id)
        available = get_available_stock(variant)
        if available < qty: raise "Insufficient stock"
        InventoryReservation.objects.create(
          product_variant=variant, sale=sale, quantity=qty,
          status=ACTIVE, expires_at=now() + CHECKOUT_RESERVATION_MINUTES,
        )
  11. Mark cart CHECKED_OUT
COMMIT TRANSACTION
  12. transaction.on_commit: queue ORDER_CONFIRMATION email
  13. Return 201
```

**Failure at any step rolls back everything** — no partial Sale, SaleItems, reservations, or cart-state changes.

### 5.2 Cancel order (customer)

```
BEGIN TRANSACTION (atomic)
  1. sale = Sale.objects.select_for_update().get(
       id=id, customer__user=user, is_active=True
     )
  2. if sale.status != PENDING: raise "Only pending orders can be cancelled"
  3. Release reservations (idempotent):
     InventoryReservation.objects.filter(
       sale=sale, status=ACTIVE
     ).update(status=RELEASED)
  4. sale.status = CANCELLED
  5. sale.updated_by = user
  6. sale.save(update_fields=['status', 'updated_by', 'updated_at'])
COMMIT TRANSACTION
  7. transaction.on_commit: queue ORDER_CANCELLED email
  8. Return 200
```

No accounting reversal needed — no entries were posted at placement.

### 5.3 Confirm order (staff — extends `update_sale_status()`)

The existing `update_sale_status()` is extended with a conditional branch. The POS path (`channel != WEBSITE`) is completely unchanged. The storefront path (`channel == WEBSITE`) uses reservation-aware logic.

```
BEGIN TRANSACTION (atomic)
  1. Validate transition allowed (PENDING → CONFIRMED)
  2. if sale.channel == SaleChannel.WEBSITE:
     a. active_reservations = sale.reservations.filter(status=ACTIVE)
     b. if not active_reservations.exists(): raise "No reservations found"
     c. FOR EACH reservation:
        - if reservation.expires_at <= now():
          raise "Reservation expired. Order must be re-placed."
        - variant = ProductVariant.objects.select_for_update().get(id=...)
        - other_reserved = sum of active, non-expired reservations
          for this variant EXCLUDING this sale's reservations
        - total_movements = sum of movements (is_active=True) for variant
        - available_excluding_ours = total_movements - other_reserved
        - if available_excluding_ours < reservation.quantity:
          raise "Stock no longer available for {variant}"
        - InventoryMovement.objects.create(
            product_variant=variant, quantity=-reservation.quantity,
            movement_type=SALE, reference_type=ORDER, reference_id=sale.id,
          )
        - reservation.status = CONSUMED
        - reservation.save(update_fields=['status', 'updated_at'])
     d. Resolve account (existing _resolve_sale_account logic)
     e. Create accounting transaction:
        DR  Accounts Receivable  = subtotal_amount
        CR  Product Revenue       = subtotal_amount
        DR  Accounts Receivable  = shipping_amount
        CR  Shipping Revenue      = shipping_amount
        POST immediately
     f. Save sale: status=CONFIRMED, account, accounting_transaction
  3. else (POS path — unchanged):
     - Existing _deduct_sale_stock(), _create_sale_transaction() logic
  4. sale.status = CONFIRMED; sale.save(...)
COMMIT TRANSACTION
```

### 5.4 Collect COD payment

```
BEGIN TRANSACTION (atomic)
  1. sale = Sale.objects.select_for_update().get(id=id)
  2. Validate sale.status == DELIVERED (else 400)
  3. Validate sale.payment_status == UNPAID (else 400)
  4. cash_account = sale.payment_method.default_account
     - Validate: not None, is_active, deleted_at is null, account_type == ASSET
     - If invalid: raise "COD payment method is not properly configured"
  5. receivable = get_or_create_accounts_receivable_account()
  6. Create accounting transaction:
     DR  cash_account   = total_amount
     CR  receivable     = total_amount
     type=RECEIPT, reference=invoice_number,
     description="COD payment collected for sale #{id}"
  7. POST accounting transaction
  8. sale.payment_status = COLLECTED
  9. sale.save(update_fields=['payment_status', 'updated_at'])
COMMIT TRANSACTION
```

No duplicate collection possible: `select_for_update()` + `payment_status == UNPAID` check inside the transaction.

### 5.5 Block storefront returns

In `update_sale_status()`, when `next_status == RETURNED` and `sale.channel == SaleChannel.WEBSITE`:
```python
raise ValidationError(
    "Storefront returns are not supported in v1. "
    "Please contact support."
)
```

This prevents the RETURNED branch from executing for storefront orders, protecting against incorrect POS-style return accounting.

### 5.6 Failure boundaries

| Failure | Rollback scope | Side effects |
|---|---|---|
| Validation error before reservation | Entire transaction | None |
| Stock reservation fails | Entire transaction | None |
| Sale creation fails | Entire transaction | None |
| Cart status update fails | Entire transaction | None |
| Email queue fails after commit | N/A (after commit) | Order exists, email logged as PENDING, Celery retries |
| Accounting fails at confirmation | Entire transaction | Sale stays PENDING, reservations stay ACTIVE |
| Accounting fails at COD collection | Entire transaction | Payment stays UNPAID |
| Concurrent idempotency insert | IntegrityError caught | Existing order fetched and returned |

---

## 6. Accounting Design

### 6.1 Accounts

| Account | Type | Provisioning |
|---|---|---|
| Sales Revenue | REVENUE | Existing (`get_or_create_sales_revenue_account()`) |
| Shipping Revenue | REVENUE | New. Lookup by name + type; create if missing. |
| Accounts Receivable | ASSET | New. Lookup by name + type; create if missing. |
| Cash/Bank (COD) | ASSET | Existing or created by data migration. Inspect before creating. |

All provisioning functions follow the `get_or_create_sales_revenue_account()` pattern: `select_for_update()`, lookup by name + type, reactivate if inactive/deleted, create if missing, raise on failure.

### 6.2 Entries by event

| Event | Debit | Credit | Amount |
|---|---|---|---|
| Order placed | — | — | None |
| Order confirmed (storefront) | Accounts Receivable | Product Revenue | subtotal |
| Order confirmed (storefront) | Accounts Receivable | Shipping Revenue | shipping |
| Order confirmed (POS) | sale.account | Sales Revenue | total (unchanged) |
| COD collected | Cash/Bank (PaymentMethod.default_account) | Accounts Receivable | total |
| Cancel from PENDING | — | — | None |
| Return (storefront) | **Blocked in v1** | — | — |
| Return (POS) | Sales Revenue | sale.account | total (unchanged) |

### 6.3 Return accounting

Storefront returns are blocked in v1. The existing `_create_sale_return_transaction()` is not modified and remains correct for POS sales. When storefront returns are implemented in a future phase, the reversal will use:

```
DR  Product Revenue       = subtotal_amount
DR  Shipping Revenue      = shipping_amount
CR  Accounts Receivable   = total_amount
```

---

## 7. Inventory Design

### 7.1 Reservation lifecycle

```
Placement:     ACTIVE
Confirmation:  ACTIVE → CONSUMED
Cancellation:  ACTIVE → RELEASED
Expiry:        ACTIVE → RELEASED (Celery Beat, every 5 min)
```

### 7.2 get_available_stock()

```python
def get_available_stock(product_variant):
    total = InventoryMovement.objects.filter(
        product_variant=product_variant,
        is_active=True,                     # exclude soft-deleted
    ).aggregate(s=Sum('quantity'))['s'] or 0
    reserved = InventoryReservation.objects.filter(
        product_variant=product_variant,
        status=ReservationStatus.ACTIVE,
        expires_at__gt=timezone.now(),      # exclude expired
    ).aggregate(r=Sum('quantity'))['r'] or 0
    return total - reserved
```

### 7.3 Reservation concurrency

At placement:
```python
variant = ProductVariant.objects.select_for_update().get(id=variant_id)
available = get_available_stock(variant)
if available < quantity: raise ValidationError(...)
InventoryReservation.objects.create(...)
```

At confirmation, stock re-verification excludes the current order's own reservations:
```python
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
    raise ValidationError("Stock no longer available")
```

### 7.4 Reservation expiry

Management command: `inventory_api/management/commands/expire_reservations.py`

```python
InventoryReservation.objects.filter(
    status=ReservationStatus.ACTIVE,
    expires_at__lte=timezone.now(),
).update(status=ReservationStatus.RELEASED)
```

Celery Beat schedule in `settings.py`:
```python
CELERY_BEAT_SCHEDULE = {
    'expire-reservations': {
        'task': 'inventory_api.tasks.expire_reservations_task',
        'schedule': 300.0,  # every 5 minutes
    },
}
```

A Celery Beat process must be running in production. The task is a thin wrapper around the management command logic.

### 7.5 Product→Variant resolution

```python
def resolve_variant(product):
    active_variants = product.variants.filter(
        is_active=True, deleted_at__isnull=True,
    )
    count = active_variants.count()
    if count == 0:
        raise ValidationError(
            f"Product '{product.name}' has no available variants."
        )
    if count == 1:
        return active_variants.first()
    raise ValidationError(
        f"Product '{product.name}' has multiple variants. "
        "Please select one."
    )
```

---

## 8. Implementation Phases

### Phase 4.1: Model and migration changes

Files:
- `sale_api/models/sale.py` — add PaymentStatus, CANCELLED, new fields, new indexes, new unique_together
- `inventory_api/models/inventory.py` — add ReservationStatus, InventoryReservation
- `inventory_api/models/__init__.py` — export ReservationStatus, InventoryReservation
- `sale_api/models/__init__.py` — export PaymentStatus
- `sale_api/admin.py` — register new fields
- `inventory_api/admin.py` — register InventoryReservation

Generate: `makemigrations sale_api inventory_api`.

Acceptance criteria:
- Migrations apply cleanly on a fresh database.
- Migrations apply cleanly on a database with existing POS data.
- Existing `Sale` rows have `shipping_amount=0`, `payment_status=UNPAID`, `idempotency_key=null`.
- Existing POS API endpoints return unchanged responses.

Dependencies: none.

### Phase 4.2: Account provisioning and settings

Files:
- `sale_api/services.py` — add `get_or_create_shipping_revenue_account()`, `get_or_create_accounts_receivable_account()`
- `EcommerceBackend/settings.py` — add `CHECKOUT_RESERVATION_MINUTES = env('CHECKOUT_RESERVATION_MINUTES', default=30)`
- `EcommerceBackend/env.py.example` — add `CHECKOUT_RESERVATION_MINUTES`

Acceptance criteria:
- Account functions inspect for existing accounts before creating.
- Functions reactivate inactive/deleted accounts.
- Functions raise clear errors on failure.
- `select_for_update()` prevents concurrent duplicate creation.

Dependencies: Phase 4.1.

### Phase 4.3: Inventory reservation service and expiry

Files:
- `inventory_api/services/reservation.py` (new) — `reserve_stock()`, `release_reservations()`, `consume_reservations()`, `get_available_stock()`
- `inventory_api/services/__init__.py` — re-export
- `inventory_api/management/commands/expire_reservations.py` (new)
- `inventory_api/tasks.py` (new) — `expire_reservations_task`
- `EcommerceBackend/settings.py` — add `CELERY_BEAT_SCHEDULE` entry

Acceptance criteria:
- `reserve_stock()` uses `select_for_update()` and checks available stock.
- `release_reservations()` is idempotent (running twice changes zero rows the second time).
- `consume_reservations()` is idempotent.
- `get_available_stock()` excludes soft-deleted movements and expired reservations.
- Expiry command releases stale ACTIVE reservations.
- Celery Beat schedule is configured.

Dependencies: Phase 4.1.

### Phase 4.4: Sale status transition updates

Files:
- `sale_api/services.py` — extend `update_sale_status()` with `channel == WEBSITE` branch for CONFIRMED (reservation-aware deduction, receivable accounting) and RETURNED (block with error)
- `sale_api/services.py` — no changes to POS paths

Acceptance criteria:
- POS confirmation path is byte-for-byte unchanged.
- POS return path is byte-for-byte unchanged.
- Storefront confirmation: reserves consumed, movements created, receivable accounting posted.
- Storefront return: blocked with clear error message.
- Expired reservations at confirmation: fails with clear error.
- Stock re-verification excludes own reservations.

Dependencies: Phases 4.1, 4.2, 4.3.

### Phase 4.5: Order creation and cancellation services

Files:
- `checkout_api/services/order.py` (new) — `create_order()`, `cancel_order()`, `_resolve_variant()`, `_snapshot_address()`, `_build_fingerprint()`
- `checkout_api/services/__init__.py` — re-export

Acceptance criteria:
- `create_order()` is fully atomic — any failure rolls back all changes.
- Idempotency checked before cart validation.
- Fingerprint persisted on `Sale.idempotency_key`.
- Concurrent duplicate inserts caught via `IntegrityError`, existing order returned.
- Prices re-read from `Product.current_selling_price`.
- Channel hardcoded to `WEBSITE`.
- `cancel_order()` uses `select_for_update()`, releases reservations idempotently.
- Email queued via `transaction.on_commit()`.

Dependencies: Phases 4.1, 4.2, 4.3, 4.4.

### Phase 4.6: Order serializers

Files:
- `checkout_api/serializers/order.py` (new) — `OrderCreateSerializer`, `OrderDetailSerializer`, `OrderListSerializer`
- `checkout_api/serializers/__init__.py` — re-export

Acceptance criteria:
- `OrderCreateSerializer` validates `shipping_address_id`, `shipping_method_id`, `idempotency_key` (required), `notes` (optional).
- `OrderDetailSerializer` exposes approved fields only — no accounting internals.
- `OrderListSerializer` is compact (id, invoice, status, payment_status, total, item_count, created_at).

Dependencies: Phase 4.5.

### Phase 4.7: Customer order views and URLs

Files:
- `checkout_api/views/v1/order.py` (new) — `CheckoutConfirmView`, `CustomerOrderViewSet`, `CustomerOrderCancelView`
- `checkout_api/views/v1/__init__.py` — re-export
- `checkout_api/urls/v1.py` — add order URL patterns
- `checkout_api/permissions.py` (new) — `CustomerOrderPermission`

Acceptance criteria:
- `POST /api/v1/checkout/confirm/` requires authentication.
- `GET /api/v1/orders/` scoped to authenticated customer.
- `GET /api/v1/orders/{id}/` returns 404 for other customer's order.
- `POST /api/v1/orders/{id}/cancel/` scoped to authenticated customer, PENDING only.
- All endpoints tagged `@extend_schema(tags=["Checkout"])`.

Dependencies: Phase 4.6.

### Phase 4.8: COD collection endpoint and permissions

Files:
- `sale_api/views/v1/sale.py` — add `mark_cod_paid` action with `custom_permissions`
- `sale_api/migrations/` — data migration for `collect_sale_payment` permission

Acceptance criteria:
- `mark_cod_paid` action on `SaleViewSet` at `POST /api/v1/sales/{id}/mark-paid/`.
- Permission: `collect_sale_payment` via `CustomPermissionAccessMixin`.
- `select_for_update()` on Sale row.
- Validates `status == DELIVERED`, `payment_status == UNPAID`.
- Accounting: Dr Cash/Bank (from PaymentMethod.default_account), Cr Accounts Receivable.
- Sets `payment_status = COLLECTED`.
- Fully atomic.
- Returns 400 for already-collected or wrong-status orders.

Dependencies: Phase 4.7.

### Phase 4.9: Email templates and integration

Files:
- `email_api/constants.py` — add ORDER_CONFIRMATION, ORDER_CANCELLED to `EMAIL_TEMPLATE_REGISTRY`
- `email_api/templates/emails/order_confirmation.html` (new)
- `email_api/templates/emails/order_confirmation.txt` (new)
- `email_api/templates/emails/order_cancelled.html` (new)
- `email_api/templates/emails/order_cancelled.txt` (new)
- `checkout_api/services/order.py` — add `transaction.on_commit()` email calls

Acceptance criteria:
- Templates render without error.
- `EmailService.queue()` called with correct `email_type`, `recipient`, `context`, `idempotency_key`.
- Email queued after transaction commit, not before.
- Email failure does not roll back the order.
- Idempotency key prevents duplicate emails.

Dependencies: Phase 4.5.

### Phase 4.10: Deployment configuration

Files:
- `EcommerceBackend/settings.py` — `CELERY_BEAT_SCHEDULE` already added in Phase 4.3
- Deployment documentation — Celery Beat process must run alongside the worker

Acceptance criteria:
- `CHECKOUT_RESERVATION_MINUTES` configurable via environment variable.
- `CELERY_BEAT_SCHEDULE` includes reservation expiry task.
- Documentation notes that Celery Beat must be deployed.

Dependencies: Phase 4.3.

### Phase 4.11: Tests

Files:
- `checkout_api/tests.py` — extend with order placement, idempotency, cancellation tests
- `inventory_api/tests.py` — reservation, concurrency, expiry tests
- `sale_api/tests.py` — storefront confirmation, COD collection, POS regression tests

Dependencies: all previous phases.

---

## 9. Test Matrix

### Order placement
- Valid order: 201, correct totals, cart CHECKED_OUT, reservations ACTIVE
- Empty cart: 200 with `is_valid: false`
- Inactive product: 200 with error
- Zero-price product: 200 with error
- Single variant auto-select: resolves correctly
- Multiple variants: 200 with error
- No active variants: 200 with error
- Insufficient stock: 200 with error
- Price re-read: backend price used, not frontend-supplied
- Channel hardcoded to Website in response
- Sale created before reservations (FK constraint satisfied)
- Entire operation atomic: partial failure rolls back all

### Idempotency
- Same key, same fingerprint: returns existing order (200), no new Sale created
- Same key, different fingerprint: 409 Conflict
- Missing key: 400
- Concurrent insert with same key: IntegrityError caught, existing order returned
- Idempotency check happens before cart validation: retry after cart checkout succeeds

### Cancellation
- Cancel PENDING order: status→CANCELLED, reservations RELEASED
- Cancel non-PENDING: 400
- Cancel already-cancelled: 200 idempotent (no error)
- Cancel other user's order: 404
- Reservations actually released: stock available for new orders
- Concurrent cancellation: second request sees CANCELLED, returns 200

### COD collection
- Valid collection: payment_status→COLLECTED, accounting created
- Already collected: 400
- Wrong status (not DELIVERED): 400
- Permission denied: 403
- Concurrent collection: second request fails (select_for_update)
- Missing/deleted/inactive cash account: clear error
- Accounting: Dr Cash/Bank, Cr Accounts Receivable, correct amount

### Inventory concurrency
- Two simultaneous reservations for same variant: one succeeds, one fails
- Reservation + simultaneous POS sale: POS uses old validate_stock (unaffected)
- Confirmation after reservation expired: fails with clear error
- Confirmation with stock consumed by another order: fails with clear error
- Available stock excludes soft-deleted movements
- Available stock excludes expired reservations
- Available stock excludes own reservations at confirmation time

### Accounting
- Confirmation: Dr Accounts Receivable, Cr Product Revenue + Shipping Revenue, POSTED
- COD collection: Dr Cash/Bank, Cr Accounts Receivable, POSTED
- POS confirmation unchanged: Dr Asset, Cr Sales Revenue
- POS return unchanged: Dr Sales Revenue, Cr Asset
- No cash entry at placement
- No cash entry at confirmation
- Total debits equal total credits in all transactions

### Email
- ORDER_CONFIRMATION queued after commit
- ORDER_CANCELLED queued after commit
- Email failure does not rollback order
- Idempotency key prevents duplicate emails

### Customer order isolation
- Customer A cannot see Customer B's orders
- Customer detail returns 404 for other customer's order
- Order list scoped to authenticated customer

### POS regression
- Existing `create_sale()` behavior unchanged
- Existing `update_sale_status()` POS path unchanged
- Existing `SaleViewSet` queryset unchanged
- Existing POS API response format unchanged
- Existing POS accounting entries unchanged
- Existing POS return flow unchanged

### Celery Beat
- Expiry task runs on schedule
- Stale reservations are released
- Non-expired reservations are untouched
- Already-released reservations are unaffected (idempotent)

---

## 10. Risks and Mitigations

### Risk 1: Stock consumed between reservation and confirmation

Another order could consume stock after our reservation. **Mitigation:** At confirmation, re-verify available stock excluding our own reservation. If insufficient, fail with clear error.

### Risk 2: Reservation expiry during confirmation

If a reservation expires between the start of confirmation and the commit, the confirmation should fail. **Mitigation:** Check `expires_at > now()` inside the transaction while holding `select_for_update()` on the variant row.

### Risk 3: Existing return-accounting breakage

The existing `_create_sale_return_transaction()` reverses Sales Revenue against `sale.account`. Storefront orders use different accounts. **Mitigation:** Block storefront returns in v1 entirely. When returns are implemented later, use a separate function keyed on `channel == WEBSITE`.

### Risk 4: POS `validate_stock()` includes soft-deleted movements

Pre-existing bug at `sale_api/services.py:215`. **Mitigation:** Not fixed in this phase. The new `get_available_stock()` correctly filters. Document for future cleanup.

### Risk 5: Cash/Bank account provisioning conflicts

A Cash/Bank account may already exist from manual setup. **Mitigation:** Data migration inspects for existing accounts before creating. Provisioning functions use `select_for_update()` and name+type lookup.

### Risk 6: Celery Beat not deployed

If Celery Beat is not running, reservations never expire. **Mitigation:** Deployment documentation must explicitly require a Beat process. Add a health check or monitoring alert.

---

## 11. Acceptance Criteria Summary

| Area | Criteria |
|---|---|
| Atomicity | Order placement, confirmation, cancellation, and COD collection are each fully atomic |
| Idempotency | Duplicate requests with same key return existing order; conflicting keys return 409 |
| Inventory | Reservations block over-sell; expired reservations fail confirmation; availability excludes soft-deleted movements |
| Accounting | Revenue recognized at confirmation; cash at collection only; debits always equal credits |
| POS regression | No existing POS behavior, API contract, or accounting semantics changed |
| Email | Queued after commit; failure does not rollback; idempotent |
| Permissions | Customer endpoints scoped to owner; COD collection requires `collect_sale_payment` |
| Celery Beat | Reservation expiry runs every 5 minutes in production |
| Migrations | Safe for existing deployments; defaults preserve existing data |
| Returns | Storefront returns blocked; POS returns unchanged |

---

## 12. Recommended First Phase

**Phase 4.1: Model and migration changes.** This is the foundation all other phases depend on. It can be reviewed independently before any service logic is built. It establishes the data contract (PaymentStatus, CANCELLED, new Sale fields, InventoryReservation) and verifies migration safety on existing data.

Awaiting approval to begin Phase 4.1.
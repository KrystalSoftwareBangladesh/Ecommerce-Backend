# Phase 4 — Storefront Order Creation: Implementation Specification

Specification date: 2026-10-13.
Audit-only task. No code changes, no migrations, no implementation.

---

## 1. Repository Findings

### Verified Files, Models, Services, and Constraints

| Component | File | Key classes/functions |
|---|---|---|
| Sale model | `sale_api/models/sale.py` | `Sale`, `SaleItem`, `SaleStatus`, `SaleChannel` |
| Sale services | `sale_api/services.py` | `create_sale()`, `update_sale()`, `update_sale_status()`, `validate_stock()`, `_deduct_sale_stock()`, `_restock_returned_sale()`, `_create_sale_transaction()`, `get_or_create_sales_revenue_account()` |
| Sale serializers | `sale_api/serializers/sale.py` | `SaleCreateSerializer`, `SaleDetailSerializer`, `SaleListSerializer`, `SaleStatusUpdateSerializer` |
| Sale views | `sale_api/views/v1/sale.py` | `SaleViewSet` (ModelViewSet, no permission override) |
| Sale URLs | `sale_api/urls/v1.py` | `sales/`, `sales/{id}/`, `sales/{id}/update-status/` |
| PaymentMethod model | `sale_api/models/payment_method.py` | `PaymentMethod` (code, name, default_account, allow_account_override) |
| Cart model | `cart_api/models/cart.py` | `Cart` (status: ACTIVE/CHECKED_OUT/ABANDONED) |
| CartItem model | `cart_api/models/cart_item.py` | `CartItem` (FK to **Product**, not ProductVariant, quantity) |
| Cart services | `cart_api/services/cart.py` | `get_active_cart()`, `get_or_create_active_cart()`, `checkout_cart()`, `abandon_cart()` |
| CartItem services | `cart_api/services/cart_item.py` | `add_cart_item()`, `update_cart_item()`, `remove_cart_item()` |
| Checkout validation | `checkout_api/services.py` | `validate_checkout()`, `_validate_cart()`, `_validate_cart_items()`, `_validate_products()`, `_validate_address()`, `_resolve_shipping()`, `_build_item_lines()` |
| Product model | `product_api/models/product.py` | `Product` (current_selling_price), `ProductVariant` (sku, color, size, is_active) |
| CustomerProfile | `customer_api/models/customer.py` | `CustomerProfile` (user, customer_type) |
| CustomerAddress | `customer_api/models/customer_address.py` | `CustomerAddress` (address_type: BILLING/SHIPPING, all address fields) |
| ShippingZone | `shipping_api/models/shipping_zone.py` | `ShippingZone`, `ShippingZoneRule` (CITY/POSTCODE matching) |
| ShippingMethod | `shipping_api/models/shipping_method.py` | `ShippingMethod` (name, code) |
| ShippingRate | `shipping_api/models/shipping_rate.py` | `ShippingRate` (base_charge, free_shipping_threshold) |
| Shipping service | `shipping_api/services/shipping.py` | `match_zone()`, `calculate_shipping_charge()`, `get_shipping_options()` |
| InventoryMovement | `inventory_api/models/inventory.py` | `InventoryMovement`, `MovementType`, `ReferenceType` |
| ChartOfAccount | `account_api/models/chart_of_account.py` | `ChartOfAccount`, `AccountType` (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE) |
| AccountingTransaction | `transaction_api/models/transaction.py` | `AccountingTransaction`, `AccountingTransactionLine`, `TransactionStatus`, `TransactionType` |
| Transaction services | `transaction_api/services.py` | `create_transaction()`, `post_transaction()` |
| EmailLog | `email_api/models/email_log.py` | `EmailLog` (email_type, status, idempotency_key, recipient, metadata) |
| Email service | `email_api/services/email.py` | `EmailService.create_log()` → `transaction.on_commit()` → `send_email_task.delay()` |
| Email tasks | `email_api/tasks.py` | `send_email_task` (Celery shared_task, max_retries=3, countdown=60) |
| Email constants | `email_api/constants.py` | `EmailType` (includes ORDER_CONFIRMATION, ORDER_CANCELLED, ORDER_SHIPPED), `EmailStatus` |
| Core permissions | `EcommerceBackend/core/permission.py` | `PublicReadPermissionMixin`, `ModelPermissionAccess`, `CustomPermissionAccessMixin` |
| Celery config | `EcommerceBackend/celery.py` | `app = Celery("EcommerceBackend")`, autodiscover_tasks() |

### Verified Constraints

- `Sale.customer` is non-nullable (PROTECT). Customer profile is mandatory.
- `SaleItem.product_variant` is PROTECT. Cannot delete a variant referenced by a sale item.
- `SaleItem.unique_together = ('sale', 'product_variant')`. No duplicate variants per sale.
- `CartItem` FK to Product uses `on_delete=PROTECT`, `related_name="cart_items"`.
- `ProductVariant` inherits `SoftDeleteModel` (has `is_active`, `deleted_at`).
- `ProductVariant` FK to Product uses `related_name="variants"`.
- `InventoryMovement` has no `is_active` filtering in `validate_stock()` — soft-deleted movements are included in stock calculation.
- `ReferenceType.ORDER` already exists at `inventory_api/models/inventory.py:20`.
- `EmailType.ORDER_CONFIRMATION`, `ORDER_CANCELLED`, `ORDER_SHIPPED` exist but have NO entries in `EMAIL_TEMPLATE_REGISTRY`.
- `SaleViewSet` has no `permission_classes` override. Returns ALL active sales.
- `SaleStatus` has no CANCELLED state. Transitions are strictly linear.
- `Sale.total_amount = subtotal - discount + tax`. No shipping component.
- `AccountType` choices: ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE. No RECEIVABLE type.

---

## 2. Current Workflow

### Sale Creation (POS flow)

1. Staff user submits `POST /api/v1/sales/` with customer, items (product_variant_id, quantity, **unit_price**), optional payment_method, account, discount_amount, tax_amount.
2. `create_sale()` wraps in `transaction.atomic()`.
3. Resolves account from payment_method's default_account or caller-supplied account.
4. Creates `Sale` with `status=PENDING`.
5. Creates `SaleItem` per item. **Trusts caller-supplied `unit_price`**.
6. Computes `subtotal = sum(qty * unit_price)`, `total = subtotal - discount + tax`.
7. Auto-generates invoice number if blank.
8. Returns sale. **No inventory deduction. No accounting transaction.**

### Sale Confirmation (POS flow)

1. Staff user submits `POST /api/v1/sales/{id}/update-status/` with `status=CONFIRMED`.
2. `update_sale_status()` wraps in `transaction.atomic()`.
3. Resolves and validates account (must be ASSET type, active).
4. Validates `total_amount > 0`.
5. **Deducts stock**: for each item, calls `validate_stock()` then creates `InventoryMovement(quantity=-qty, movement_type=SALE, reference_type=ORDER)`.
6. **Creates accounting transaction**: Debit asset account, Credit Sales Revenue. Immediately POSTED.
7. Saves sale with new status, account, accounting_transaction.

### Cart → Checkout Validation

1. Customer calls `POST /api/v1/checkout/validate/` with `shipping_address_id`, `shipping_method_id`.
2. `validate_checkout()` retrieves active cart, validates products/prices, validates address, matches shipping zone, calculates charges.
3. Returns `is_valid`, `cart` (items with current prices), `pricing` (subtotal, shipping, grand total), `shipping` (method, zone, charge).
4. **No records created. No stock check. Prices re-read from Product.current_selling_price.**

### Gap: No storefront order creation exists.

---

## 3. Gap Analysis

| Requirement | Current state | Gap |
|---|---|---|
| Create order from cart | `checkout_cart()` flips status only | Need full order-creation service |
| Backend-controlled prices | `create_sale()` trusts caller `unit_price` | Must override with `Product.current_selling_price` |
| Product→Variant mapping | CartItem→Product, SaleItem→ProductVariant | Need single-variant auto-select logic |
| Shipping amount on order | `Sale` has no `shipping_amount` field | Need model field + migration |
| Shipping address snapshot | `Sale` has no address fields | Need JSONField snapshot |
| Payment status | Only fulfillment `status` exists | Need `payment_status` field (UNPAID/COLLECTED) |
| CANCELLED status | Not in `SaleStatus` | Need new status + transitions |
| Inventory reservation | No reservation model | Need `InventoryReservation` model |
| Idempotency | No idempotency mechanism | Need `idempotency_key` field + unique constraint |
| Customer-scoped orders | `SaleViewSet` returns all sales | Need customer-scoped queryset + permissions |
| Shipping revenue account | Only Sales Revenue account exists | Need Shipping Revenue account |
| COD accounting | Accounting at confirmation assumes cash received | Need receivable-based accounting for COD |
| Order confirmation email | `ORDER_CONFIRMATION` type exists, no template | Need template + registry entry |
| Order cancellation email | `ORDER_CANCELLED` type exists, no template | Need template + registry entry |

---

## 4. Proposed Data Model

### 4.1 Sale Model Changes

New fields on `Sale` (`sale_api/models/sale.py`):

| Field | Type | Default | Notes |
|---|---|---|---|
| `payment_status` | CharField(max_length=20) | `UNPAID` | Choices: UNPAID, COLLECTED, REFUNDED |
| `shipping_amount` | DecimalField(12,2) | 0 | Separated from product subtotal |
| `shipping_address_snapshot` | JSONField | `{}` | Frozen copy of address at order time |
| `idempotency_key` | CharField(max_length=255) | null | Unique together with `customer` |

Updated `total_amount` formula:
```
total_amount = subtotal_amount - discount_amount + tax_amount + shipping_amount
```

Meta additions:
- `unique_together = (('invoice_number',), ('customer', 'idempotency_key'))`
- Index on `(customer, status)` for order-history queries.

### 4.2 SaleStatus Changes

Add `CANCELLED` to `SaleStatus` and update transitions:

```python
class SaleStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    PROCESSING = 'PROCESSING', 'Processing'
    PACKAGED = 'PACKAGED', 'Packaged'
    SHIPPED = 'SHIPPED', 'Shipped'
    OUT_OF_DELIVERY = 'OUT_OF_DELIVERY', 'Out of Delivery'
    DELIVERED = 'DELIVERED', 'Delivered'
    RETURNED = 'RETURNED', 'Returned'
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

Customers can cancel from PENDING only. Staff can cancel from PENDING or CONFIRMED.

### 4.3 PaymentStatus (new)

```python
class PaymentStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    COLLECTED = 'COLLECTED', 'Collected'
    REFUNDED = 'REFUNDED', 'Refunded'
```

### 4.4 InventoryReservation Model (new)

New model in `inventory_api/models/inventory.py`:

```python
class ReservationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    CONSUMED = 'CONSUMED', 'Consumed'
    RELEASED = 'RELEASED', 'Released'
    EXPIRED = 'EXPIRED', 'Expired'

class InventoryReservation(TimeStampedModel, UserStampedModel):
    product_variant = FK(ProductVariant, PROTECT, related_name='reservations')
    sale = FK(Sale, CASCADE, related_name='reservations')
    quantity = PositiveIntegerField()
    status = CharField(max_length=20, choices=ReservationStatus, default=ACTIVE)
    expires_at = DateTimeField()

    class Meta:
        indexes = [
            Index(fields=['product_variant', 'status']),
            Index(fields=['sale', 'status']),
            Index(fields=['expires_at']),
        ]
```

Key behaviors:
- Only `status=ACTIVE` reservations count toward reserved quantity.
- `expires_at` allows automatic expiry of stale reservations.
- `select_for_update()` on the variant row during reservation to prevent concurrent over-reservation.

### 4.5 Available Stock Calculation

The new stock calculation must exclude active reservations:

```python
def get_available_stock(product_variant):
    """Concurrency-safe available stock calculation."""
    total_movements = InventoryMovement.objects.filter(
        product_variant=product_variant,
    ).aggregate(stock=Sum('quantity'))['stock'] or 0

    total_reserved = InventoryReservation.objects.filter(
        product_variant=product_variant,
        status=ReservationStatus.ACTIVE,
        expires_at__gt=now(),
    ).aggregate(reserved=Sum('quantity'))['reserved'] or 0

    return total_movements - total_reserved
```

**Important:** The existing `validate_stock()` in `sale_api/services.py:215` does NOT filter by `is_active=True` on movements. This is a pre-existing bug. The new implementation should filter by `is_active=True`.

### 4.6 SaleItem Model

No changes needed. `SaleItem` already stores `product_variant`, `quantity`, `unit_price`, `line_total`.

---

## 5. Final API Contracts

### 5.1 Place an Order

```
POST /api/v1/checkout/confirm/
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "shipping_address_id": 12,
  "shipping_method_id": 5,
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "notes": "Please call before delivery"
}
```

**Fields never trusted from the frontend:**
- Product prices (re-read from `Product.current_selling_price`)
- Variant mapping (resolved server-side)
- Subtotal, shipping charge, discount, tax, grand total (recalculated)
- Order status (always PENDING)
- Payment status (always UNPAID)
- Invoice number (auto-generated)
- Channel (hardcoded to Website)

**Success response (201 Created):**
```json
{
  "id": 1001,
  "invoice_number": "SALE-20261013-001001",
  "status": "PENDING",
  "payment_status": "UNPAID",
  "channel": "Website",
  "customer": {
    "id": 5,
    "user": {"id": 10, "username": "customer1"}
  },
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
    "first_name": "John",
    "last_name": "Doe",
    "address_1": "123 Main St",
    "city": "Dhaka",
    "postcode": "1205",
    "country": "Bangladesh",
    "phone": "+8801700000000"
  },
  "pricing": {
    "subtotal": "1000.00",
    "shipping_charge": "60.00",
    "discount_total": "0.00",
    "tax_total": "0.00",
    "grand_total": "1060.00"
  },
  "shipping_method": {
    "id": 5,
    "name": "Standard Delivery",
    "code": "standard"
  },
  "notes": "Please call before delivery",
  "created_at": "2026-10-13T14:30:00+06:00"
}
```

**Validation error (200 with `is_valid: false`):**
```json
{
  "is_valid": false,
  "errors": ["Insufficient stock for Wireless Mouse (requested: 2, available: 1)."]
}
```

**Idempotency conflict (409 Conflict):**
```json
{
  "detail": "Order already exists for this idempotency key.",
  "order_id": 1001,
  "invoice_number": "SALE-20261013-001001"
}
```

**Input validation error (400 Bad Request):**
```json
{
  "success": false,
  "message": "This field is required.",
  "errors": {"shipping_address_id": ["This field is required."]}
}
```

### 5.2 Customer Order History

```
GET /api/v1/orders/
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "count": 3,
  "total_pages": 1,
  "current_page": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1001,
      "invoice_number": "SALE-20261013-001001",
      "status": "PENDING",
      "payment_status": "UNPAID",
      "total_amount": "1060.00",
      "item_count": 1,
      "created_at": "2026-10-13T14:30:00+06:00"
    }
  ]
}
```

**Filters:** `status`, `payment_status`, `start_date`, `end_date`.
**Ordering:** `-created_at` (default), `total_amount`.
**Pagination:** Standard project pagination (PageNumberPagination, default 10).

**Permissions:** `IsAuthenticated`. Queryset scoped to `sale.customer.user = request.user`.

### 5.3 Customer Order Detail

```
GET /api/v1/orders/{id}/
Authorization: Bearer <token>
```

**Response (200 OK):** Same structure as the placement response (Section 5.1 success response), plus `allowed_next_statuses`.

**Permissions:** `IsAuthenticated`. Returns 404 if the order does not belong to the authenticated customer.

**Fields NOT exposed to customers:**
- `account` (internal accounting)
- `accounting_transaction` (internal accounting)
- `return_transaction` (internal accounting)
- `created_by` / `updated_by` (internal)

### 5.4 Cancel an Order

```
POST /api/v1/orders/{id}/cancel/
Authorization: Bearer <token>
```

**Request:** Empty body (no fields required).

**Success response (200 OK):**
```json
{
  "id": 1001,
  "invoice_number": "SALE-20261013-001001",
  "status": "CANCELLED",
  "payment_status": "UNPAID",
  "message": "Order cancelled successfully."
}
```

**Error responses:**
- 404: Order not found or not owned by customer.
- 400: `"Only pending orders can be cancelled by customers."` (if status is not PENDING).
- 400: `"Order is already cancelled."` (idempotent — return 200 with current status).

**Behavior:**
- Allowed only when `status == PENDING` for customers.
- Releases all ACTIVE inventory reservations for the order.
- Sets `status = CANCELLED`.
- Does NOT create accounting transactions (no revenue was recognized at placement).
- Sends `ORDER_CANCELLED` email via `transaction.on_commit()`.

### 5.5 Mark COD Payment Collected

```
POST /api/v1/orders/{id}/mark-paid/
Authorization: Bearer <token>
```

**Request:** Empty body.

**Success response (200 OK):**
```json
{
  "id": 1001,
  "invoice_number": "SALE-20261013-001001",
  "status": "DELIVERED",
  "payment_status": "COLLECTED",
  "message": "Payment collected successfully."
}
```

**Error responses:**
- 403: User does not have the required permission.
- 404: Order not found.
- 400: `"Payment has already been collected."` (if payment_status is already COLLECTED).
- 400: `"Order must be delivered before payment can be collected."` (if status is not DELIVERED).

**Permissions:** `IsAuthenticated` + custom permission `collect_sale_payment` on `sale_api.Sale`. This follows the `CustomPermissionAccessMixin` pattern used by `category_api` and `blog_api`.

**Behavior:**
- Validates `status == DELIVERED` and `payment_status == UNPAID`.
- Sets `payment_status = COLLECTED`.
- Creates accounting transaction: Debit Cash/Bank (asset), Credit Accounts Receivable (asset).
- Does NOT create new revenue entries (revenue was already recognized at CONFIRMED).

---

## 6. Transactional Workflows

### 6.1 Place an Order

```
1. BEGIN TRANSACTION
2. Validate request payload (serializer)
3. get_active_cart(user) → cart
4. list_cart_items(cart) → items with select_related("product")
5. _validate_products(items) → check is_active, price > 0
6. FOR EACH item:
   a. Resolve Product → ProductVariant
      - product.variants.filter(is_active=True, deleted_at__isnull=True)
      - If count == 1: auto-select
      - If count == 0: raise "Product '{name}' has no available variants"
      - If count > 1: raise "Product '{name}' has multiple variants. Please select one."
   b. Re-read price: product.current_selling_price
7. _validate_address(user, address_id) → address
8. _resolve_shipping(address, method_id, subtotal) → shipping details
9. Check idempotency_key:
   a. Sale.objects.filter(customer=customer, idempotency_key=key).first()
   b. If exists: raise 409 Conflict with existing order details
10. Reserve inventory (with SELECT FOR UPDATE on variant rows):
    FOR EACH item:
      a. SELECT ... FOR UPDATE on ProductVariant row
      b. available = get_available_stock(variant)
      c. If available < quantity: raise "Insufficient stock for {name}"
      d. InventoryReservation.objects.create(
           product_variant=variant, sale=sale, quantity=qty,
           status=ACTIVE, expires_at=now()+30min
         )
11. Create Sale (status=PENDING, payment_status=UNPAID, channel=Website)
12. Create SaleItems (unit_price from Product.current_selling_price)
13. Compute totals: subtotal, shipping, discount, tax, grand total
14. Snapshot address into shipping_address_snapshot JSONField
15. Mark cart as CHECKED_OUT
16. COMMIT TRANSACTION
17. transaction.on_commit: send ORDER_CONFIRMATION email
18. Return 201 with order detail
```

### 6.2 Retry Idempotent Request

```
1. BEGIN TRANSACTION
2. Sale.objects.select_for_update().filter(
     customer=customer, idempotency_key=key
   ).first()
3. If found and request matches (same address_id, method_id):
   - Return existing order (200 or 201)
4. If found but request differs:
   - Raise 409 Conflict
5. If not found:
   - Proceed with order creation (Section 6.1)
6. COMMIT TRANSACTION
```

**Request equivalence:** Compare `shipping_address_id` and `shipping_method_id` against the stored order's `shipping_address_snapshot` and `shipping_method` FK. If they match, treat as the same request.

**Incomplete/failed attempts:** If the idempotency key exists but the order is in an unexpected state (e.g., already cancelled), return the existing order with its current status. Do not create a new order.

### 6.3 Confirm an Order (staff action)

```
1. BEGIN TRANSACTION
2. Validate status transition (PENDING → CONFIRMED)
3. Resolve and validate account (ASSET type)
4. Release any remaining ACTIVE reservations (they're about to be consumed)
5. FOR EACH item:
   a. SELECT ... FOR UPDATE on ProductVariant row
   b. validate_stock(variant, quantity) — using get_available_stock()
   c. InventoryMovement.objects.create(
        quantity=-qty, movement_type=SALE,
        reference_type=ORDER, reference_id=sale.id
      )
6. FOR EACH reservation:
   a. Set status = CONSUMED
7. Create accounting transaction:
   - Debit Accounts Receivable (ASSET), Credit Product Revenue (REVENUE)
   - Debit Accounts Receivable (ASSET), Credit Shipping Revenue (REVENUE)
8. POST accounting transaction
9. Save sale: status=CONFIRMED, account, accounting_transaction
10. COMMIT TRANSACTION
```

### 6.4 Cancel an Order

```
1. BEGIN TRANSACTION
2. Validate: status == PENDING (for customer) or PENDING/CONFIRMED (for staff)
3. If status == PENDING:
   a. Release all ACTIVE reservations:
      InventoryReservation.objects.filter(
        sale=sale, status=ACTIVE
      ).update(status=RELEASED)
   b. No accounting reversal needed (no entries at placement)
4. If status == CONFIRMED:
   a. Restock: create positive InventoryMovement per item
   b. Reverse accounting: Debit Revenue, Credit Accounts Receivable
   c. Release any remaining ACTIVE reservations
5. Set status = CANCELLED
6. COMMIT TRANSACTION
7. transaction.on_commit: send ORDER_CANCELLED email
```

### 6.5 Collect COD Payment

```
1. BEGIN TRANSACTION
2. Validate: status == DELIVERED, payment_status == UNPAID
3. Get or create Cash/Bank asset account
4. Create accounting transaction:
   - Debit Cash/Bank (ASSET) for total_amount
   - Credit Accounts Receivable (ASSET) for total_amount
5. POST accounting transaction
6. Set payment_status = COLLECTED
7. COMMIT TRANSACTION
```

### 6.6 Failure Handling

| Failure point | Behavior |
|---|---|
| Validation fails before reservation | Transaction rolls back. No side effects. |
| Reservation fails (insufficient stock) | Transaction rolls back. No side effects. |
| Database error during sale creation | Transaction rolls back. Reservations released. |
| Email queue fails after commit | Order is created. Email failure is logged but does not affect the order. Celery retries up to 3 times. |
| Accounting fails at confirmation | Transaction rolls back. Order stays PENDING. Reservations remain ACTIVE. |
| Accounting fails at COD collection | Transaction rolls back. Payment status stays UNPAID. |

**Critical:** All async operations (email) use `transaction.on_commit()` to ensure they only execute after the database transaction is committed.

---

## 7. Accounting Design

### 7.1 Chart of Accounts

New accounts needed:

| Account name | Type | Purpose |
|---|---|---|
| Sales Revenue | REVENUE | Already exists (`get_or_create_sales_revenue_account()`) |
| Shipping Revenue | REVENUE | New. Shipping charge revenue. |
| Accounts Receivable | ASSET | New. COD orders: money owed by customer until delivery-agent collects. |
| Cash/Bank | ASSET | Existing or new. Used when COD payment is collected. |

All accounts follow the auto-code pattern in `account_api/models/chart_of_account.py`.

### 7.2 Accounting Entries by Lifecycle Event

| Event | Debit | Credit | Amount |
|---|---|---|---|
| Order placed (PENDING) | — | — | No entries |
| Order confirmed | Accounts Receivable | Product Revenue | subtotal - discount + tax |
| Order confirmed | Accounts Receivable | Shipping Revenue | shipping_amount |
| COD payment collected | Cash/Bank | Accounts Receivable | total_amount |
| Order cancelled (from PENDING) | — | — | No entries |
| Order cancelled (from CONFIRMED) | Product Revenue | Accounts Receivable | subtotal - discount + tax |
| Order cancelled (from CONFIRMED) | Shipping Revenue | Accounts Receivable | shipping_amount |

**Key principles:**
- Revenue is recognized at CONFIRMED, not at placement.
- Cash is recorded only at COLLECTED, not at confirmation.
- Accounts Receivable bridges the gap between revenue recognition and cash collection.
- Cancellation from PENDING has no accounting impact (no entries were posted).
- Cancellation from CONFIRMED reverses the revenue recognition.

### 7.3 Implementation

Create `get_or_create_shipping_revenue_account()` following the same pattern as `get_or_create_sales_revenue_account()` in `sale_api/services.py:26-55`.

Create `get_or_create_accounts_receivable_account()` for the receivable account.

The existing `create_transaction()` and `post_transaction()` in `transaction_api/services.py` support multiple lines per transaction. The confirmation transaction will have 4 lines:
1. Debit Accounts Receivable, Credit Product Revenue (for product amount)
2. Debit Accounts Receivable, Credit Shipping Revenue (for shipping amount)

Or equivalently, 2 debit lines and 2 credit lines in a single transaction.

---

## 8. Inventory Design

### 8.1 Reservation Model

New `InventoryReservation` model in `inventory_api/models/inventory.py`:

```python
class ReservationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    CONSUMED = 'CONSUMED', 'Consumed'
    RELEASED = 'RELEASED', 'Released'
    EXPIRED = 'EXPIRED', 'Expired'

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
            models.Index(
                fields=['product_variant', 'status'],
            ),
            models.Index(fields=['sale', 'status']),
            models.Index(fields=['expires_at']),
        ]
```

### 8.2 Available Stock Calculation

```python
def get_available_stock(product_variant):
    total_movements = InventoryMovement.objects.filter(
        product_variant=product_variant,
        is_active=True,
    ).aggregate(stock=Sum('quantity'))['stock'] or 0

    total_reserved = InventoryReservation.objects.filter(
        product_variant=product_variant,
        status=ReservationStatus.ACTIVE,
        expires_at__gt=timezone.now(),
    ).aggregate(reserved=Sum('quantity'))['reserved'] or 0

    return total_movements - total_reserved
```

**Important:** The new calculation filters `is_active=True` on movements, fixing the pre-existing bug in `sale_api/services.py:215`.

### 8.3 Concurrency Strategy

```
1. SELECT ... FOR UPDATE on the ProductVariant row
2. Calculate available stock
3. If available >= requested:
   - Create InventoryReservation (status=ACTIVE)
4. Else:
   - Raise ValidationError
5. Release lock (end of transaction)
```

`select_for_update()` locks the variant row for the duration of the transaction, preventing two concurrent requests from over-reserving the same stock.

### 8.4 Reservation Expiry

Default expiry: 30 minutes from creation. This handles abandoned checkouts.

A management command or periodic task should expire stale reservations:
```python
InventoryReservation.objects.filter(
    status=ReservationStatus.ACTIVE,
    expires_at__lte=timezone.now(),
).update(status=ReservationStatus.EXPIRED)
```

### 8.5 Reservation Lifecycle

| Event | Reservation action |
|---|---|
| Order placed | Create ACTIVE reservations |
| Order confirmed | Convert ACTIVE → CONSUMED, deduct stock via InventoryMovement |
| Order cancelled (PENDING) | Release ACTIVE → RELEASED |
| Order cancelled (CONFIRMED) | Release any remaining ACTIVE → RELEASED, restock via InventoryMovement |
| Reservation expires | ACTIVE → EXPIRED (periodic task) |
| Stock no longer available | Order placement fails with clear error |

### 8.6 Product→Variant Mapping

For v1:

```python
def resolve_variant(product):
    active_variants = product.variants.filter(
        is_active=True,
        deleted_at__isnull=True,
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

**Data safety:** `ProductVariant` inherits `SoftDeleteModel`, so `is_active=True` and `deleted_at__isnull=True` filters are valid. The `count()` query is lightweight.

---

## 9. Implementation Phases

### Phase 4.1: Model Changes

1. Add `CANCELLED` to `SaleStatus`, update `SALE_STATUS_TRANSITIONS`.
2. Add `PaymentStatus` choices.
3. Add fields to `Sale`: `payment_status`, `shipping_amount`, `shipping_address_snapshot`, `idempotency_key`.
4. Add `unique_together = ('customer', 'idempotency_key')` to Sale.
5. Update `total_amount` formula to include `shipping_amount`.
6. Create `InventoryReservation` model.
7. Generate migrations.
8. Update admin registrations.

**Dependencies:** None.

### Phase 4.2: Inventory Reservation Service

1. Create `inventory_api/services/reservation.py`:
   - `reserve_stock(sale, items)` — creates reservations with `select_for_update()`.
   - `release_reservations(sale)` — releases ACTIVE reservations.
   - `consume_reservations(sale)` — converts ACTIVE → CONSUMED.
   - `get_available_stock(variant)` — movements minus active reservations.
   - `expire_stale_reservations()` — management command.
2. Update `sale_api/services.py:validate_stock()` to use `get_available_stock()` and filter `is_active=True`.

**Dependencies:** Phase 4.1.

### Phase 4.3: Accounting Infrastructure

1. Create `get_or_create_shipping_revenue_account()` in `sale_api/services.py`.
2. Create `get_or_create_accounts_receivable_account()` in `sale_api/services.py`.
3. Create `_create_cod_collection_transaction()` for payment collection.
4. Update `_create_sale_transaction()` to include shipping revenue line.
5. Update `_create_sale_return_transaction()` to include shipping reversal.

**Dependencies:** Phase 4.1.

### Phase 4.4: Order Creation Service

1. Create `checkout_api/services/order.py` (or extend existing `services.py`):
   - `create_order(user, shipping_address_id, shipping_method_id, idempotency_key, notes)` — full order creation flow.
   - `_resolve_variant(product)` — single-variant auto-select.
   - `_snapshot_address(address)` — returns JSON dict.
2. Create `cancel_order(user, sale)` — customer cancellation.
3. Create `collect_cod_payment(user, sale)` — staff payment collection.

**Dependencies:** Phases 4.1, 4.2, 4.3.

### Phase 4.5: Order Serializers

1. Create `checkout_api/serializers/order.py`:
   - `OrderCreateSerializer` — input validation (shipping_address_id, shipping_method_id, idempotency_key, notes).
   - `OrderItemSerializer` — item detail with variant info.
   - `OrderPricingSerializer` — pricing breakdown.
   - `OrderShippingSerializer` — shipping address snapshot + method.
   - `OrderDetailSerializer` — full order response.
   - `OrderListSerializer` — compact list response.
2. Create `checkout_api/serializers/customer_order.py` for customer-facing order views.

**Dependencies:** Phase 4.4.

### Phase 4.6: Order Views and URLs

1. Create `checkout_api/views/v1/order.py`:
   - `CheckoutConfirmView` — `POST /api/v1/checkout/confirm/`.
   - `CustomerOrderViewSet` — `GET /api/v1/orders/`, `GET /api/v1/orders/{id}/`.
   - `CustomerOrderCancelView` — `POST /api/v1/orders/{id}/cancel/`.
2. Create `sale_api/views/v1/sale.py` additions:
   - `mark_cod_paid` action on `SaleViewSet` — `POST /api/v1/sales/{id}/mark-paid/`.
3. Register URLs in `checkout_api/urls/v1.py` and `sale_api/urls/v1.py`.

**Dependencies:** Phase 4.5.

### Phase 4.7: Permissions

1. Create customer-scoped order permissions:
   - `CustomerOrderPermission` — ensures customer can only access their own orders.
   - `collect_sale_payment` custom permission for the mark-paid action.
2. Register the custom permission in Django's permission system via migration or data migration.

**Dependencies:** Phase 4.6.

### Phase 4.8: Email Integration

1. Add `ORDER_CONFIRMATION`, `ORDER_CANCELLED`, `ORDER_SHIPPED` to `EMAIL_TEMPLATE_REGISTRY`.
2. Create email templates (`emails/order_confirmation.html`, `.txt`, etc.).
3. Call `EmailService.create_log()` with `transaction.on_commit()` in order creation and cancellation services.

**Dependencies:** Phase 4.4.

### Phase 4.9: Tests

1. Unit tests for reservation service.
2. API tests for order placement.
3. API tests for order history and detail.
4. API tests for cancellation.
5. API tests for COD collection.
6. Concurrency tests for reservation.
7. Idempotency tests.
8. Accounting correctness tests.

**Dependencies:** All previous phases.

---

## 10. Test Matrix

| Test | Type | What it verifies |
|---|---|---|
| Valid order placement | API | Happy path — 201, correct totals, cart CHECKED_OUT |
| Empty cart rejection | API | 422 error when cart is empty |
| Inactive product rejection | API | Product validation |
| Zero-price product rejection | API | Price validation |
| Single variant auto-select | Service | Variant resolution with one active variant |
| Multiple variant rejection | Service | Error when product has multiple variants |
| No variant rejection | Service | Error when product has no active variants |
| Insufficient stock | API | Reservation fails |
| Concurrent reservation | Service | Two requests don't over-reserve |
| Reservation expiry | Service | Stale reservations are expired |
| Stock released on cancellation | Service | ACTIVE → RELEASED |
| Stock consumed on confirmation | Service | ACTIVE → CONSUMED, movements created |
| Idempotent retry returns existing | API | Same key, same request → existing order |
| Idempotent key conflict | API | Same key, different request → 409 |
| Shipping charge calculation | API | Correct charge, free shipping threshold |
| Address snapshot preserved | API | Snapshot matches original address |
| Price re-read from backend | Service | Ignores frontend prices |
| No sale created at validation | API | validate_checkout creates nothing |
| Cart status unchanged by validation | API | validate_checkout doesn't change cart |
| Customer order isolation | API | Customer A can't see Customer B's orders |
| Customer order detail 404 | API | Returns 404 for other customer's order |
| Cancel PENDING order | API | Status → CANCELLED, reservations released |
| Cancel non-PENDING order | API | 400 error |
| Cancel already cancelled | API | Idempotent — 200 with current status |
| Mark COD collected | API | payment_status → COLLECTED |
| Mark COD already collected | API | 400 error |
| Mark COD wrong status | API | 400 if not DELIVERED |
| COD collection permissions | API | 403 for non-staff |
| Accounting at confirmation | Service | Dr Receivable, Cr Revenue (product + shipping) |
| Accounting at COD collection | Service | Dr Cash, Cr Receivable |
| Accounting at cancellation | Service | Reversal if CONFIRMED, nothing if PENDING |
| No premature cash entry | Service | Placement and confirmation don't record cash |
| Email enqueued after commit | Service | ORDER_CONFIRMATION email sent |
| Email cancellation sent | Service | ORDER_CANCELLED email sent |
| Email failure doesn't rollback | Service | Order created even if email fails |
| Input validation errors | API | Missing fields → 400 |
| Unauthenticated rejection | API | 401 |

---

## 11. Risks and Unresolved Decisions

### Risk 1: Reservation expiry race condition

If a reservation expires between the availability check and the actual order creation, the order could be created with insufficient stock. **Mitigation:** Use `select_for_update()` within the same transaction, and check expiry as part of the lock.

### Risk 2: Cart item→Product→Variant mapping edge cases

A product could be deactivated or its variants could change between cart addition and order placement. **Mitigation:** Validate everything at order time, not at cart time.

### Risk 3: Accounting account creation race condition

Two concurrent order confirmations could try to create the Shipping Revenue account simultaneously. **Mitigation:** Use `select_for_update()` in `get_or_create_shipping_revenue_account()`, following the existing pattern in `get_or_create_sales_revenue_account()`.

### Risk 4: Existing `validate_stock()` bug

`sale_api/services.py:215` does not filter by `is_active=True` on movements. The new `get_available_stock()` fixes this, but existing POS sales still use the old function. **Mitigation:** Update `validate_stock()` to use the new function, or keep both and deprecate the old one.

### Risk 5: CANCELLED status on existing sales

Adding CANCELLED to the existing `SALE_STATUS_TRANSITIONS` changes the allowed transitions for PENDING and CONFIRMED. **Mitigation:** This is additive — no existing sales are affected, and no existing transitions are removed.

### Risk 6: `total_amount` formula change

Adding `shipping_amount` to the formula changes how `total_amount` is computed. Existing sales have `shipping_amount=0` (default), so their totals are unchanged. **Mitigation:** Default value of 0 ensures backward compatibility.

### Unresolved Decision A: Accounts Receivable account type

`AccountType` has ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE. Accounts Receivable is conceptually an ASSET (current asset). The existing system uses ASSET for cash/bank accounts. **Recommendation:** Use ASSET for Accounts Receivable. It follows the existing pattern and is accounting-correct.

### Unresolved Decision B: Shipping Revenue account auto-creation

Should `get_or_create_shipping_revenue_account()` auto-create the account like `get_or_create_sales_revenue_account()` does? **Recommendation:** Yes, for consistency. Both are system-managed accounts.

### Unresolved Decision C: Cash/Bank account for COD collection

Which asset account should receive the debit when COD payment is collected? Options:
1. Use the sale's existing `account` field (set at confirmation).
2. Use the payment method's `default_account`.
3. Require a separate `cash_account_id` in the mark-paid request.

**Recommendation:** Option 2 — use the payment method's `default_account`. For COD, create a "Cash on Delivery" PaymentMethod with a default Cash account. The mark-paid endpoint should accept an optional `payment_method_id` override.

### Unresolved Decision D: Reservation expiry duration

The proposed 30-minute expiry is a default. **Question:** Should this be configurable (e.g., via settings.py) or hardcoded?

### Unresolved Decision E: Order detail endpoint path

The proposed `GET /api/v1/orders/{id}/` reuses the `Sale` model but serves a customer-scoped view. **Question:** Should this be a separate ViewSet in `checkout_api` or a customer-scoped action on the existing `SaleViewSet` in `sale_api`?

**Recommendation:** Separate ViewSet in `checkout_api`. The existing `SaleViewSet` is for staff/POS use and should not be modified. Customer-facing order views have different serializers (no accounting data), different permissions (customer-scoped), and different URL patterns.

---

## 12. Final Recommendation

**The design is ready for implementation** with the following prerequisites resolved first:

1. **Approve the inventory reservation model** (Section 8.1). This is the largest architectural addition.
2. **Approve the accounting design** (Section 7). Confirm that Accounts Receivable + Shipping Revenue accounts are acceptable.
3. **Confirm COD payment collection flow** (Section 5.5). Specifically: which account receives the cash debit, and who has permission to mark payment collected.
4. **Confirm reservation expiry duration** (30 minutes default or configurable).
5. **Confirm order endpoint paths** (`/api/v1/orders/` in `checkout_api` vs modifying `sale_api`).

Once these decisions are confirmed, implementation can proceed through Phases 4.1 → 4.9 in order, with each phase independently testable.

---

## Decisions Requiring Approval

1. **Inventory reservation model** — Approve the `InventoryReservation` model with `select_for_update()` concurrency strategy and 30-minute default expiry.
2. **Accounting design** — Approve Accounts Receivable (ASSET) + Shipping Revenue (REVENUE) accounts, and the three-phase accounting pattern (no entry at placement, revenue at confirmation, cash at collection).
3. **COD cash account** — Approve using the payment method's `default_account` for the cash debit at collection, with a dedicated "Cash on Delivery" PaymentMethod.
4. **Order endpoint ownership** — Approve customer-facing order endpoints (`/api/v1/orders/`) in `checkout_api` as a separate ViewSet, not modifying the existing `SaleViewSet`.
5. **Idempotency equivalence** — Approve comparing `shipping_address_id` and `shipping_method_id` for request equivalence. Different address or method with the same key returns 409.
6. **Reservation expiry** — Approve 30-minute default, or specify a different duration.
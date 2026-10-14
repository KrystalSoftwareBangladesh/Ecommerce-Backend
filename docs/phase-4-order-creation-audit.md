# Phase 4 — Order Creation Readiness Audit

Audit date: 2026-10-13.
Audit-only task. No code changes, no new files, no migrations, no API implementation.

Our first storefront release supports Cash on Delivery (COD) only.

---

## 1. Existing Implementation

### Sale Model (`sale_api/models/sale.py`)

| Field | Type | Notes |
|---|---|---|
| `customer` | FK to CustomerProfile | PROTECT |
| `payment_method` | FK to PaymentMethod | PROTECT, nullable |
| `account` | FK to ChartOfAccount | PROTECT, nullable (asset account for cash receipt) |
| `accounting_transaction` | FK | SET_NULL, nullable |
| `return_transaction` | FK | SET_NULL, nullable |
| `sale_date` | DateField | |
| `invoice_number` | CharField | unique, auto-generated |
| `channel` | CharField | Choices: Walk-in, Facebook, Phone, **Website**, Instagram, WhatsApp |
| `status` | CharField | PENDING → CONFIRMED → PROCESSING → PACKAGED → SHIPPED → OUT_OF_DELIVERY → DELIVERED → RETURNED |
| `subtotal_amount` | Decimal(15,2) | |
| `discount_amount` | Decimal(15,2) | Default 0 |
| `tax_amount` | Decimal(15,2) | Default 0 |
| `total_amount` | Decimal(15,2) | `= subtotal - discount + tax` |
| `notes` | TextField | |

**Missing fields for storefront orders:** `shipping_amount`, `shipping_address_*` (snapshot), `payment_status`, `idempotency_key`.

### SaleItem Model (`sale_api/models/sale.py:124`)

| Field | Type | Notes |
|---|---|---|
| `sale` | FK to Sale | CASCADE |
| `product_variant` | FK to ProductVariant | PROTECT |
| `quantity` | PositiveIntegerField | |
| `unit_price` | Decimal(15,2) | Price snapshot at creation |
| `line_total` | Decimal(15,2) | `= quantity × unit_price` |

**Key observation:** `SaleItem` references `ProductVariant`, not `Product`. It stores a price snapshot via `unit_price`. The `unique_together = ('sale', 'product_variant')` constraint prevents duplicate variants per sale.

### Sale Services (`sale_api/services.py`)

| Function | Lines | What it does |
|---|---|---|
| `create_sale()` | 223-263 | Creates sale in PENDING. **Does NOT deduct inventory or create accounting transactions.** Trusts `unit_price` from caller. Computes `total = subtotal - discount + tax`. |
| `update_sale()` | 266-305 | Edits PENDING sales only. Same pricing logic. |
| `update_sale_status()` | 336-398 | On CONFIRMED: validates account, **deducts stock** (`_deduct_sale_stock`), **creates accounting transaction**. On RETURNED: restocks, creates reversal transaction. |
| `validate_stock()` | 215-220 | Sums `InventoryMovement.quantity` for a variant, raises if < requested. |
| `_deduct_sale_stock()` | 308-321 | Creates negative `InventoryMovement` (type=SALE, reference=ORDER) per item. |
| `_create_sale_transaction()` | 168-182 | Debit asset account, credit sales revenue. Posts immediately. |

**Critical:** Inventory deduction and accounting happen at CONFIRMED status, not at PENDING. This is the existing POS pattern.

### Sale Serializers (`sale_api/serializers/sale.py`)

- `SaleCreateSerializer` accepts: `customer`, `payment_method_id`, `account_id`, `sale_date`, `invoice_number`, `channel`, `discount_amount`, `tax_amount`, `notes`, `items[]` (each with `product_variant_id`, `quantity`, `unit_price`).
- **`unit_price` is a writable field from the frontend.** The backend does not re-derive it from the product.
- `SaleDetailSerializer` returns all fields plus nested customer, items, payment method, account, transactions, and `allowed_next_statuses`.

### Sale Views (`sale_api/views/v1/sale.py`)

- `SaleViewSet` is a full `ModelViewSet` with project default permissions (`IsAuthenticated`).
- `create` calls `create_sale()`.
- `update_status` action calls `update_sale_status()`.
- `destroy` soft-deletes PENDING sales only.
- **No sale-specific permissions exist.** The ViewSet does not scope queries to the requesting user — it returns ALL active sales. Storefront orders need customer-scoped permissions.

### Status Transitions (`sale_api/models/sale.py:23-32`)

Strictly linear, one step at a time:

```
PENDING → CONFIRMED → PROCESSING → PACKAGED → SHIPPED → OUT_OF_DELIVERY → DELIVERED → RETURNED
```

There is no CANCEL transition. `RETURNED` is terminal.

### Side Effects by Transition

| Transition | Inventory | Accounting | Extra validation |
|---|---|---|---|
| PENDING → CONFIRMED | Deducts stock (negative movements) | Creates + posts SALE transaction | Account required (ASSET type), total > 0 |
| CONFIRMED → PROCESSING | None | None | None |
| PROCESSING → PACKAGED | None | None | None |
| PACKAGED → SHIPPED | None | None | None |
| SHIPPED → OUT_OF_DELIVERY | None | None | None |
| OUT_OF_DELIVERY → DELIVERED | None | None | None |
| DELIVERED → RETURNED | Restocks (positive movements) | Creates + posts ADJUSTMENT (reversal) | Original accounting_transaction must exist |

### Cart Model (`cart_api/models/`)

- `Cart`: status (ACTIVE/CHECKED_OUT/ABANDONED), unique constraint on one active cart per user.
- `CartItem`: FK to **`Product`** (not ProductVariant), `quantity`, unique constraint on active (cart, product).

### Checkout Validation (`checkout_api/services.py`)

- `validate_checkout()` validates cart, products, address, shipping zone/method.
- Returns `is_valid`, `cart` (items with current prices), `pricing` (subtotal, shipping, grand total), `shipping` (method, zone, charge).
- **Does NOT validate stock** (ProductVariant gap).
- **Does NOT create any records.**
- Prices are re-derived from `Product.current_selling_price` — never trusted from frontend.

### Inventory System (`inventory_api/models/inventory.py`)

- `InventoryMovement`: FK to `ProductVariant`, signed `quantity`, `movement_type`, `reference_type`, `reference_id`.
- Movement types: PURCHASE, SALE, REFUND, ADJUSTMENT, OPENING.
- Reference types: PURCHASE, **ORDER**, RETURN, MANUAL.
- Stock = `SUM(InventoryMovement.quantity)` for a variant. No denormalized stock counter.
- **`ReferenceType.ORDER` already exists** (line 20) and is used by the sale system.

### Accounting System (`transaction_api/services.py`)

- `create_transaction()`: creates DRAFT transaction with double-entry lines.
- `post_transaction()`: moves to POSTED (immutable).
- Sale pattern at CONFIRMED: Debit asset account, Credit Sales Revenue. Immediately posted.
- Return pattern: Debit Sales Revenue, Credit asset account (reversal).

### PaymentMethod Model (`sale_api/models/payment_method.py`)

- `code`, `name`, `default_account` (FK to ChartOfAccount), `allow_account_override`.
- If `allow_account_override=False` and `default_account` is set, the caller cannot supply a different account.

---

## 2. Reusable Functionality

| Component | Reusable for orders? | Notes |
|---|---|---|
| `Sale` / `SaleItem` models | **Yes, with additions** | Need `shipping_amount`, address snapshot, `payment_status`. `channel=Website` already exists. |
| `create_sale()` | **Partially** | The item-creation and total-calculation logic is reusable. But it trusts `unit_price` from the caller — storefront orders must override with backend prices. |
| `update_sale_status()` to CONFIRMED | **Yes** | Stock deduction + accounting at confirmation. COD can use this. |
| `validate_stock()` | **Yes, once variant mapping exists** | Works at variant level. Needs variant selection to be solved first. |
| `_deduct_sale_stock()` | **Yes** | Creates negative `InventoryMovement` with `reference_type=ORDER`. |
| `_create_sale_transaction()` | **Yes** | Debit asset / credit revenue. For COD, this should fire at confirmation (before delivery). |
| `checkout_api.validate_checkout()` | **Yes, as pre-validation** | Cart/address/shipping validation. Must re-run at order time. |
| `get_shipping_options()` | **Yes** | Zone matching + charge calculation. Reusable for order shipping. |
| `get_active_cart()` / `list_cart_items()` | **Yes** | Standard cart retrieval. |
| `CartStatus.CHECKED_OUT` | **Yes** | Mark cart as checked out after order creation. |
| `SaleChannel.WEBSITE` | **Yes** | Already defined in `Sale.SaleChannel.choices`. |
| `ReferenceType.ORDER` | **Yes** | Already defined in `inventory_api/models/inventory.py:20`. |

---

## 3. Missing Functionality

| Missing | Impact | Notes |
|---|---|---|
| **Product-to-Variant mapping** | **Blocking** | CartItem → Product, but SaleItem → ProductVariant. Cart has no variant selection. Need business decision on how to resolve. |
| **`shipping_amount` on Sale** | **Blocking** | `total_amount = subtotal - discount + tax`. Shipping is not part of the formula. Schema change needed. |
| **Address snapshot on Sale** | **Blocking** | No fields to store the delivery address. Need either inline fields or a JSON snapshot. |
| **`payment_status` on Sale** | **Blocking** | Only `status` (fulfillment) exists. COD needs separate payment tracking (UNPAID → COLLECTED). |
| **Idempotency** | **Important** | No mechanism to prevent duplicate orders from retries. |
| **Order-submission endpoint** | **Blocking** | No `/api/v1/checkout/confirm/` exists. |
| **Cart-to-order conversion** | **Blocking** | `checkout_cart()` just flips status. No Sale creation, no item mapping. |
| **COD payment collection** | **Future** | Delivery-agent marks payment as collected. Separate from order placement. |
| **Customer-scoped order permissions** | **Blocking** | `SaleViewSet` returns ALL sales. Storefront customers must only see their own. |
| **CANCEL transition** | **Important** | `SaleStatus` has no CANCELLED state. Need to add one for order cancellation. |

---

## 4. Risks and Architectural Constraints

### Risk 1: Product-to-Variant mapping

`CartItem.product` → `Product` has many `ProductVariant` (SKU/color/size). The cart has no concept of which variant the customer wants. Options:

**A. Single-variant products only (v1 shortcut).** If a product has exactly one active variant, auto-select it. If it has multiple, reject with "please select variant." This works for stores that don't use variants or use them minimally.

**B. Require variant selection before order.** Add a `product_variant` FK to `CartItem` (schema change to cart). Frontend sends variant ID when adding to cart. This is the correct long-term solution but changes the cart API contract.

**C. Skip variant mapping, use Product-level stock.** Not viable — stock is tracked at variant level.

**Recommendation:** Option A for v1. Most products likely have one variant. Multi-variant products can be handled in v2.

### Risk 2: Price changes between validation and confirmation

`Product.current_selling_price` can change between `POST /checkout/validate/` and `POST /checkout/confirm/`. The order creation service **must** re-read prices from the database and use those as `SaleItem.unit_price`. The existing `create_sale()` trusts `unit_price` from the caller — the storefront flow must override this.

### Risk 3: Sale has no shipping amount

The total formula is `subtotal - discount + tax`. Shipping is not modeled. Adding `shipping_amount` requires:
1. A new `DecimalField` on `Sale`.
2. A migration.
3. Updating `total_amount` formula to `subtotal - discount + tax + shipping`.
4. Updating the accounting transaction to include shipping revenue (or treat it as part of the total).

### Risk 4: Accounting timing for COD

The existing pattern creates an accounting transaction at CONFIRMED: debit asset (cash), credit sales revenue. For COD, cash isn't received until delivery. Options:

**A. Create accounting at confirmation (current pattern).** Assumes payment will be collected. If cancelled, create a reversal. Simple, matches existing flow.

**B. Defer accounting to delivery.** More accurate for COD but requires changing the CONFIRMED logic. More complex.

**Recommendation:** Option A for v1. The existing pattern is proven. Cancellation creates a reversal. The accounting team can reconcile.

### Risk 5: No idempotency

A customer double-clicking "Place Order" could create two identical orders. Solutions:
- Client-generated idempotency key (UUID in request header or body).
- Unique constraint on (user, idempotency_key) on Sale.
- Short-lived lock (Redis or database advisory lock).

**Recommendation:** Client-generated UUID in the request body, stored on Sale as `idempotency_key` with a unique constraint. Return the existing order if the key matches.

### Risk 6: No CANCEL transition

`SaleStatus` transitions are strictly linear with no cancellation path. Adding a CANCELLED status requires:
1. Adding `CANCELLED` to `SaleStatus`.
2. Defining allowed transitions (e.g., PENDING → CANCELLED, CONFIRMED → CANCELLED).
3. If cancelling after CONFIRMED: restock inventory + create reversal accounting transaction (same as RETURNED logic).
4. A new `POST /api/v1/orders/{id}/cancel/` endpoint.

---

## 5. Proposed Order API Contract

### Endpoint

```
POST /api/v1/checkout/confirm/
```

**Authentication:** Required (`IsAuthenticated`).

### Request

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
- Subtotal, shipping charge, discount, tax, grand total (recalculated server-side)
- Order status (always starts as PENDING)
- Payment status (always starts as UNPAID)
- Invoice number (auto-generated)
- Channel (hardcoded to `Website`)

### Response (201 Created)

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

### Response (422 Validation Failed)

```json
{
  "success": false,
  "message": "Product 'Wireless Mouse' is no longer available.",
  "errors": {
    "items": ["Product 'Wireless Mouse' is no longer available."]
  }
}
```

### Response (409 Conflict — duplicate idempotency key)

```json
{
  "id": 1001,
  "invoice_number": "SALE-20261013-001001",
  "status": "PENDING",
  "message": "Order already exists for this idempotency key."
}
```

### Validation Rules (must re-run at confirmation)

1. User has an active cart with active items.
2. All products are active and have valid prices.
3. Shipping address is active, type SHIPPING, belongs to customer.
4. Address matches a shipping zone.
5. Selected shipping method has an active rate for the zone.
6. **Stock check** — resolve variant, validate stock for each item.
7. Idempotency key is unique (or return existing order).

### Business Rules

- Order starts as `PENDING`, `payment_status=UNPAID`.
- Cart status changes to `CHECKED_OUT`.
- **No inventory deduction at order placement.** Deduction happens at CONFIRMED (staff action).
- **No accounting transaction at order placement.** Created at CONFIRMED.
- `channel` is hardcoded to `Website` by the backend.
- `SaleItem.unit_price` is set from `Product.current_selling_price`, never from frontend.

### Fulfillment Lifecycle (existing)

```
PENDING → CONFIRMED → PROCESSING → PACKAGED → SHIPPED → OUT_OF_DELIVERY → DELIVERED
```

At CONFIRMED: inventory deducted, accounting transaction created.
At RETURNED: inventory restocked, reversal transaction created.

### Payment Status (new, separate from fulfillment)

```
UNPAID → COLLECTED
```

- `UNPAID`: Order placed, COD not yet collected.
- `COLLECTED`: Delivery agent collected cash from customer.
- Payment status updates via a separate action: `POST /api/v1/orders/{id}/mark-paid/`
- Payment status does NOT affect fulfillment status transitions.

### Order List and Detail Endpoints (proposed)

- `GET /api/v1/orders/` — list the authenticated customer's orders, paginated.
- `GET /api/v1/orders/{id}/` — order detail, scoped to the authenticated customer.

These are separate from the existing `GET /api/v1/sales/` which is for staff/POS use.

---

## 6. Decisions Requiring Confirmation

### Decision 1: Product-to-Variant mapping

**Proposal:** For v1, auto-select the single variant if a product has exactly one active variant. Reject with error if multiple variants exist. This avoids changing the cart API contract.

**Question:** Is this acceptable? What percentage of products have multiple variants?

### Decision 2: Sale model changes

**Proposal:** Add these fields to `Sale` via migration:
- `shipping_amount` (DecimalField, default=0)
- `shipping_address_snapshot` (JSONField) — stores the address at order time
- `payment_status` (CharField, choices: UNPAID/COLLECTED, default=UNPAID)
- `idempotency_key` (CharField, unique, nullable)

Update `total_amount` formula to `subtotal - discount + tax + shipping`.

**Question:** Should `shipping_amount` be included in the accounting transaction (debits the asset account along with the product total)? Or should it be tracked separately?

### Decision 3: Accounting timing for COD

**Proposal:** Create accounting transaction at CONFIRMED (existing pattern). Debit asset account, credit sales revenue. If order is cancelled before delivery, create a reversal.

**Question:** Is this acceptable, or should accounting defer to DELIVERED?

### Decision 4: Inventory deduction timing

**Proposal:** Deduct at CONFIRMED (existing pattern). This prevents overselling between order placement and delivery. If cancelled, restock via reversal.

**Alternative:** Deduct at order placement (PENDING). Risk: customer cancels, stock is unnecessarily locked.

**Question:** Which timing is preferred?

### Decision 5: Idempotency mechanism

**Proposal:** Client-generated UUID in the request body (`idempotency_key`). Unique constraint on `Sale.idempotency_key`. If a duplicate key arrives, return the existing order (HTTP 409 or 200).

**Question:** Should duplicate submissions return 409 (conflict) or 200 with the existing order?

### Decision 6: Order endpoints scope

**Proposal for v1:**
- `POST /api/v1/checkout/confirm/` — place order
- `GET /api/v1/orders/` — list customer's orders
- `GET /api/v1/orders/{id}/` — order detail
- `POST /api/v1/orders/{id}/mark-paid/` — mark COD payment collected (delivery agent)

**Question:** Do we need order cancellation (`POST /api/v1/orders/{id}/cancel/`) in v1?

---

## 7. Recommended Implementation Sequence

```
1. Sale model migration
   - Add shipping_amount, shipping_address_snapshot,
     payment_status, idempotency_key
   - Update total_amount formula
   - Add CANCELLED status and transitions

2. Order service (checkout_api or new order_api)
   - Reuse checkout_api validation
   - Resolve Product → ProductVariant
     (single-variant auto-select)
   - Re-read prices from Product.current_selling_price
   - Calculate shipping via existing shipping service
   - Create Sale + SaleItems in PENDING
   - Snapshot address inline
   - Mark cart as CHECKED_OUT
   - Handle idempotency

3. Order serializers and views
   - POST /api/v1/checkout/confirm/
   - GET /api/v1/orders/ (customer-scoped)
   - GET /api/v1/orders/{id}/
   - Customer-scoped permissions

4. Payment status update
   - POST /api/v1/orders/{id}/mark-paid/
   - Only for DELIVERED orders with payment_status=UNPAID

5. Order cancellation (if approved)
   - POST /api/v1/orders/{id}/cancel/
   - Restock if already CONFIRMED
   - Create reversal accounting transaction if needed

6. Tests
   - Full order creation flow
   - Price re-read (ignores frontend prices)
   - Idempotency (duplicate key returns existing order)
   - Stock validation
   - Cart status changes to CHECKED_OUT
   - Address snapshot preserved
   - Shipping charge calculated correctly
   - Unauthenticated rejection
   - Empty cart rejection
   - Customer cannot see other customers' orders
   - Cancellation with inventory restock
```

---

## 8. Frontend Integration Handoff

### Decisions needed from frontend team

1. **Variant selection:** For v1, products with multiple variants will be rejected at order time. The frontend must handle this error. Acceptable?
2. **Idempotency key:** The frontend must generate a UUID and send it in the request body. On retry, reuse the same UUID.
3. **Request contract:** Only `shipping_address_id`, `shipping_method_id`, `idempotency_key`, and optional `notes`. No prices, no totals.
4. **Response contract:** See Section 5 above. The response includes the full order summary with server-calculated prices.
5. **Order list/detail:** Separate endpoints for order history. The frontend should NOT cache order prices from the checkout response — always use the order detail endpoint.
6. **Payment status:** The frontend should poll or receive webhooks for payment status updates. `UNPAID` → `COLLECTED` happens when the delivery agent confirms cash collection.

### Proposed request example (not yet implemented)

```
POST /api/v1/checkout/confirm/
Authorization: Bearer <token>
Content-Type: application/json

{
  "shipping_address_id": 12,
  "shipping_method_id": 5,
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "notes": "Please call before delivery"
}
```

### Proposed response example (not yet implemented)

See Section 5 for the full response schema.

### What the frontend must NOT do

- Send product prices, subtotals, or totals in the request.
- Assume the order is paid when `status` is `PENDING`.
- Cache pricing from the validation response for use in the confirmation response.
- Assume inventory has been reserved or deducted at order placement.
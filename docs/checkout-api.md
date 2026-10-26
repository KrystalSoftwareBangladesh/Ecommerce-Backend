# Storefront checkout and order API

Contract for the storefront frontend. All endpoints are under `/api/v1/`,
take and return JSON, and require a logged-in customer:

```
Authorization: Bearer <access token>     # SimpleJWT
```

Without a valid token every endpoint returns **401**. Money values in
`POST /checkout/validate/`, `POST /checkout/confirm/` and
`GET /orders/{id}/` are JSON numbers (two decimal places, e.g.
`1060.00`); in `GET /orders/` the list summary `total_amount` is a JSON
string (`"1060.00"`). Currency is BDT. Payment is Cash on Delivery only.

## Error format

Every error response uses the project envelope:

```json
{ "success": false, "message": "<summary>", "errors": <details> }
```

- Field errors: `errors` is an object, e.g.
  `{"shipping_method_id": ["This field is required."]}`, and `message` is
  the first message.
- Business-rule errors (out of stock, no active cart, key conflict, …):
  `errors` is a list of strings and `message` is `"Validation failed."`.
  **Show `errors[0]` to the customer.**

## 0. Delivery area and shipping address

Before pricing, the storefront asks the customer where the order is going
and which address to use. Two endpoints support that step:

### `GET /shipping/zones/available/`

Active shipping zones (delivery areas such as *Inside Dhaka* / *Outside
Dhaka*), ordered by `display_order`. **Not paginated** — a plain array.

```json
[ { "id": 1, "name": "Inside Dhaka", "code": "inside-dhaka",
    "description": "", "is_default": false, "display_order": 1 },
  { "id": 2, "name": "Outside Dhaka", "code": "outside-dhaka",
    "description": "", "is_default": true, "display_order": 2 } ]
```

### `POST` / `PATCH /customer-addresses/`

A shipping address may carry the chosen zone in `shipping_zone` (zone id,
nullable). Only active zones are accepted; an inactive or deleted zone id
returns **400**. Reads return `shipping_zone`, `shipping_zone_name` and (on
detail) `shipping_zone_code`, all `null` for addresses saved before this
field existed.

```json
{ "address_type": "SHIPPING", "first_name": "Jane", "last_name": "Doe",
  "address_1": "123 Test St", "city": "Dhaka", "postcode": "1205",
  "country": "Bangladesh", "phone": "+8801700000000",
  "shipping_zone": 1 }
```

**Zone resolution** for `/shipping/options/`, `/checkout/validate/` and
`/checkout/confirm/` is, in order: the address's `shipping_zone` (if still
active) → postcode rule → city rule → default zone. The storefront flow is
therefore: pick a zone → create the address with that zone, or `PATCH` an
untagged saved address with it → `GET /shipping/options/?address_id=` →
validate → confirm.

## 1. Validate checkout — `POST /checkout/validate/`

Prices the current cart for an address and shipping method. Creates
nothing, reserves nothing.

Request:

| Field | Type | Required |
|---|---|---|
| `shipping_address_id` | int | yes — one of the customer's active SHIPPING addresses |
| `shipping_method_id` | int | yes |

Response **200**, both when the checkout is valid and when it is not:

```json
{
  "is_valid": true,
  "cart": { "id": 7, "items": [
    { "id": 3, "product_id": 12, "product_name": "Widget",
      "quantity": 2, "unit_price": 500.00, "line_total": 1000.00 } ] },
  "pricing": { "subtotal": 1000.00, "shipping_charge": 60.00,
               "discount_total": 0.00, "tax_total": 0.00,
               "grand_total": 1060.00 },
  "shipping": { "address_id": 5, "method_id": 2, "method_name": "Standard",
                "method_code": "standard", "zone_name": "Dhaka Metro",
                "zone_code": "dhaka-metro", "base_charge": 60.00,
                "is_free_shipping": false,
                "free_shipping_threshold": 2000.00 },
  "errors": []
}
```

When `is_valid` is `false`, `errors` lists the problems and `cart`,
`pricing` and `shipping` may be `null`. Validation does not check stock;
stock is reserved at confirmation.

## 2. Place the order — `POST /checkout/confirm/`

Creates the order from the active cart, reserves stock and checks the cart
out. The order starts as `PENDING` / `UNPAID`. A product that has no
variant is sold through a default variant created on first sale (SKU
`P-<product id>`); a product whose variant has no inventory ledger is sold
**untracked** — see *Stock reservation and expiry* below.

Request:

| Field | Type | Required |
|---|---|---|
| `shipping_address_id` | int | yes |
| `shipping_method_id` | int | yes |
| `idempotency_key` | string, ≤255 | yes — see below |
| `notes` | string | no (default `""`) |

Responses:

| Status | When |
|---|---|
| **201** | Order created, **or** an identical retry (same key, same inputs) — body is the order detail (section 4), same `id` as the first response. |
| **400** | Field errors; no active cart (`"No active cart found."`); empty cart; inactive or unpriced product; product with several active variants; invalid address; no shipping zone or rate; **out of stock** (`"Insufficient stock for …"`, stock-tracked products only); COD payment not configured. Nothing is created. |
| **409** | The `idempotency_key` was already used with different inputs. Nothing is created. |
| **401** | Not authenticated. |

### Idempotency

- Generate one key (e.g. a UUID) **per checkout attempt**, before the first
  request, and reuse it for every retry of that attempt (timeouts, network
  errors, double clicks).
- Same key + same `shipping_address_id`, `shipping_method_id` and `notes`
  returns the original order with **201**, even after the cart was checked
  out and even if the retry overlaps the original request. If the original
  order was already cancelled (e.g. stock reservation expired), the retry
  still returns **201** with `status: "CANCELLED"`. The frontend must
  inspect the returned `status` — a **201** does not always mean the order
  is actionable.
- Same key + any different input returns **409**. Make a new key when the
  customer changes the address, method or notes.
- Keys are per customer.
- Two different keys for the same cart cannot both succeed: one creates the
  order, the other gets **400** `"No active cart found."`.

### Stock reservation and expiry

Stock is held for 30 minutes (`CHECKOUT_RESERVATION_MINUTES`). If staff
have not confirmed the order by then, it is **cancelled automatically**
(status `CANCELLED`) and the customer gets an email asking them to place a
new order. Cancellation happens within about 5 minutes of expiry.

**Untracked products (approved 2026-10-25).** Stock is only reserved for a
variant that has an inventory ledger (at least one active inventory
movement). A variant with no ledger — every imported catalogue product
until its opening stock is recorded — is sold *untracked*: no reservation
is created, the order never expires, and staff confirmation records no
stock movement. Once opening stock exists for the variant, new orders are
reserved and deducted as usual; a pending untracked order confirmed after
stock was recorded is stock-checked and deducted at confirmation. The
frontend needs no change: `product_variant.sku` in the order detail is the
default `P-<product id>` for such products.

## 3. Order list — `GET /orders/`

The customer's own storefront orders, newest first. **Not paginated** —
the response is a plain array.

```json
[ { "id": 41, "invoice_number": "SALE-20261013-000041",
    "status": "PENDING", "payment_status": "UNPAID",
    "total_amount": "1060.00", "item_count": 1,
    "created_at": "2026-10-13T09:15:02.123456Z" } ]
```

## 4. Order detail — `GET /orders/{id}/`

**404** if the order does not exist or belongs to another customer.

```json
{
  "id": 41,
  "invoice_number": "SALE-20261013-000041",
  "status": "PENDING",
  "payment_status": "UNPAID",
  "channel": "Website",
  "customer": { "id": 9, "user": { "id": 15, "username": "jane" } },
  "items": [ { "id": 77,
               "product_variant": { "id": 30, "sku": "WDG-001", "name": null },
               "product_name": "Widget", "quantity": 2,
               "unit_price": 500.00, "line_total": 1000.00 } ],
  "shipping_address": { "first_name": "Jane", "last_name": "Doe",
                        "company": "", "address_1": "123 Test St",
                        "address_2": "", "city": "Dhaka", "state": "",
                        "postcode": "1205", "country": "Bangladesh",
                        "phone": "+8801700000000" },
  "pricing": { "subtotal": 1000.00, "shipping_charge": 60.00,
               "discount_total": 0.00, "tax_total": 0.00,
               "grand_total": 1060.00 },
  "shipping_method": { "id": 2, "name": "Standard", "code": "standard" },
  "notes": "",
  "created_at": "2026-10-13T09:15:02.123456Z",
  "updated_at": "2026-10-13T09:15:02.456789Z",
  "allowed_next_statuses": [ { "value": "CONFIRMED", "label": "Confirmed" },
                             { "value": "CANCELLED", "label": "Cancelled" } ]
}
```

`shipping_address` and `shipping_method` are snapshots taken when the order
was placed; later address edits do not change them. `shipping_method` can
be `null` on orders created before it was recorded.
`allowed_next_statuses` describes the order workflow; the customer can only
act on `CANCELLED` (section 5).

### Statuses

`status`: `PENDING` → `CONFIRMED` → `PROCESSING` → `PACKAGED` → `SHIPPED`
→ `OUT_OF_DELIVERY` → `DELIVERED`; `PENDING` → `CANCELLED` (by the
customer, by staff, or automatically on reservation expiry).
`payment_status`: `UNPAID` → `COLLECTED` (recorded by staff after cash is
collected on delivery).

## 5. Cancel an order — `POST /orders/{id}/cancel/`

No request body. Only `PENDING` orders can be cancelled; the stock is
released and a cancellation email is sent.

| Status | When |
|---|---|
| **200** | `{"id": 41, "status": "CANCELLED", "message": "Order cancelled successfully."}` |
| **200** | Already cancelled: same shape, `"message": "Order is already cancelled."` |
| **400** | Not `PENDING` any more (e.g. staff confirmed it): `errors[0]` is `"Only pending orders can be cancelled."` |
| **404** | Not the customer's order. |

If two cancel requests for one order arrive at the same moment, one gets
200 and the other may get 400 rather than "already cancelled"; refetch the
order to show its state.

# Domain Model

Describes the **current implementation**, verified against the models in the
repository. Business rules that govern these entities are in
[business-rules.md](business-rules.md).

---

## Apps and their responsibility

| App | Responsibility | Models |
|---|---|---|
| `user_api` | Accounts, authentication, roles (Django `Group`s), permissions | `User` |
| `customer_api` | Customer profile attached to a user account | `CustomerProfile` |
| `category_api` | Hierarchical product categorisation, storefront menu, bulk import | `Category` |
| `product_api` | Catalogue: products, variants, price history, brands, images | `Product`, `ProductVariant`, `ProductPriceHistory`, `Brand`, `ProductImage` |
| `origin_api` | Hierarchical country/region of origin | `Origin` |
| `supplier_api` | Suppliers and their category coverage | `Supplier` |
| `inventory_api` | Auditable stock movement ledger | `InventoryMovement` |
| `purchase_api` | Purchases from suppliers, stock in | `Purchase`, `PurchaseItem` |
| `sale_api` | Sales, sale lines, payment methods, stock out | `Sale`, `SaleItem`, `PaymentMethod` |
| `account_api` | Chart of accounts (double-entry) | `ChartOfAccount` |
| `transaction_api` | Accounting journal: transactions and their debit/credit lines | `AccountingTransaction`, `AccountingTransactionLine` |
| `review_api` | Product reviews with moderation | `Review` |
| `wishlist_api` | Per-user product wishlist | `Wishlist` |
| `cart_api` | Shopping cart and cart lines | `Cart`, `CartItem` |
| `meta_api` | Choice/enum lookups for clients (currently moderation statuses) | *(none)* |

There is **no `Order` model** — a completed customer purchase is a `Sale`.
There is **no blog** and **no SEO/meta model**; `meta_api` is a choice-lookup
app, not SEO metadata.

## Relationships

```text
User 1──1 CustomerProfile
User *──* Group (roles)          User created_by/updated_by ──> almost every model

Category ──┐ self-FK parent (hierarchy, display_order, show_in_menu)
Origin   ──┘ self-FK parent

Product *──* Category
Product   ──> Origin            (FK, nullable)
Product 1──* ProductVariant     (sku)
Product 1──* ProductImage
Product 1──* ProductPriceHistory

Brand                            (standalone — no FK to Product; see note)

Supplier *──* Category
Purchase  ──> Supplier
Purchase  ──> ChartOfAccount
Purchase  ──> AccountingTransaction        (accounting_transaction)
Purchase  ──> AccountingTransaction        (cancellation_transaction)
Purchase 1──* PurchaseItem ──> ProductVariant

Sale      ──> CustomerProfile
Sale      ──> PaymentMethod ──> ChartOfAccount (default_account)
Sale      ──> ChartOfAccount
Sale      ──> AccountingTransaction        (accounting_transaction)
Sale      ──> AccountingTransaction        (return_transaction)
Sale   1──* SaleItem ──> ProductVariant

InventoryMovement ──> ProductVariant       (+ movement_type, reference_type, reference_id)

ChartOfAccount self-FK parent
ChartOfAccount ──> AccountingTransaction   (opening_transaction)
AccountingTransaction 1──* AccountingTransactionLine ──> ChartOfAccount

Review   ──> Product   (unique per created_by + product, moderated)
Wishlist ──> Product   (owner is created_by)
Cart     ──> (owner is created_by, status ACTIVE/CHECKED_OUT/ABANDONED)
Cart  1──* CartItem ──> Product
```

**Note on `Brand`:** `Brand` has a full model, serializer set, ViewSet and
`/api/v1/brands/` endpoints, but **no foreign key from `Product`**. Products
are not currently associated with a brand in the database.

**Note on ownership:** `Cart` and `Wishlist` have no dedicated `user` field —
ownership is expressed through `created_by` from `UserStampedModel`.

## Key enumerations

| Enum | Location | Values |
|---|---|---|
| `User.ROLE_CHOICES` | `user_api/models/user.py` | `OWNER`, `STAFF`, `CUSTOMER` |
| `CustomerProfile.CUSTOMER_TYPE_CHOICES` | `customer_api/models.py` | `POS`, `FACEBOOK`, `WEBSITE` |
| `AccountType` | `account_api/models/chart_of_account.py` | asset / liability / equity / income / expense family |
| `TransactionStatus`, `TransactionType` | `transaction_api/models/transaction.py` | draft/posted; transaction classification |
| `PurchaseStatus` | `purchase_api/models/purchase.py` | `DRAFT`, `CONFIRMED`, `CANCELLED` |
| `SaleStatus` | `sale_api/models/sale.py` | with `get_next_sale_statuses()` transition helper |
| `MovementType` | `inventory_api/models/inventory.py` | `PURCHASE`, `SALE`, `REFUND`, `ADJUSTMENT`, `OPENING` |
| `ReferenceType` | `inventory_api/models/inventory.py` | `PURCHASE`, `ORDER`, `RETURN`, `MANUAL` |
| `PaymentType` | `supplier_api/models/supplier.py` | supplier payment terms |
| `ModerationStatus` | `EcommerceBackend/core/choices.py` | `PENDING`, `APPROVED`, `REJECTED` |
| `CartStatus` | `EcommerceBackend/core/choices.py` | `ACTIVE`, `CHECKED_OUT`, `ABANDONED` |

Enums surfaced in the OpenAPI schema are named via `ENUM_NAME_OVERRIDES` in
`EcommerceBackend/settings.py`. Add an entry there when introducing a new
choice set that appears in more than one serializer.

## Custom model permissions

Declared in `Meta.permissions` and shipped with a migration:

- `user_api.User` — `change_user_email`, `change_user_username`,
  `change_user_password`, `assign_user_role`, `remove_user_role`
- `category_api.Category` — `mark_category_as_menu`,
  `remove_category_from_menu`

See [business-rules.md](business-rules.md#custom-model-permissions) for how
they are applied.

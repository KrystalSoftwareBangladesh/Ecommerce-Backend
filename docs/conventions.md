# Development Conventions

This file records what the repository **actually does** today, and — where
patterns conflict — which direction is preferred for **new code**.

Read it as three separate things and never mix them:

- **Current implementation** — verified from the code.
- **Approved project convention** — a rule you must follow.
- **Preferred direction (new code only)** — apply to new work; do **not**
  retrofit existing apps.

Approved conventions and their dates are listed in the decisions log in
[../AGENTS.md](../AGENTS.md#decisions-log).

---

## App and file layout

**Current implementation.** 13 of 15 apps use packages:
`models/`, `serializers/`, `views/v1/`, `urls/`. Exceptions:
`customer_api` and `meta_api` use a flat `models.py`; `origin_api` has no
`tests.py`.

Package `__init__.py` files re-export their public names with `__all__`.
`views/v1/__init__.py` re-exports every ViewSet so `urls/v1.py` can do
`from <app>.views import v1` and reference `v1.XViewSet`.

**Preferred direction (new code only).** Use the package layout for new apps.
When adding a module to a package, add it to that package's `__init__.py`
and `__all__`.

---

## Models

**Current implementation.**

- Domain models inherit
  `TimeStampedModel, UserStampedModel, SoftDeleteModel` from
  `EcommerceBackend/core/models.py`. `Review` also inherits
  `ModerationModel`. Line-item models (`SaleItem`, `PurchaseItem`,
  `AccountingTransactionLine`, `ProductPriceHistory`) inherit less or nothing.
- `CustomerProfile` and `User` do not use the core bases — `CustomerProfile`
  declares its own `is_active`/`created_at`/`updated_at`; `User` extends
  `AbstractUser` and has its own `is_deleted`/`added_at`/`updated_at`.
- `Meta` almost always sets `verbose_name`, `verbose_name_plural` and
  `ordering`, and usually `indexes`.
- Slug generation happens in `save()` via a `_generate_unique_slug()` helper
  (`Product`, `Category`, `Origin`, `Brand`).
- Constraints are declared in `Meta.constraints` — including partial unique
  constraints (`ProductImage` default image, `Review` one-per-user-per-product,
  `Cart` one active cart per user).

**Ambiguity — `db_table`.** Four models pin an explicit table name
(`chart_of_accounts`, `categories`, `origins`, `brands`); everything else uses
Django's default. No preference recorded — match the app you are working in.

---

## Where business logic lives

**Current implementation — three coexisting patterns.**

| Pattern | Where |
|---|---|
| View calls a service | `purchase_api`, `sale_api`, `transaction_api`, `account_api`, `cart_api`, `wishlist_api`, `review_api`, `meta_api`, `product_api` (images), `category_api` (import) |
| Serializer calls a service in `create()`/`update()` | `product_api/serializers/brand.py`, `product_api/serializers/product_image.py`, `cart_api/serializers/cart_item.py`, `review_api/serializers/review.py` |
| Logic inline in the view, no service | `category_api/views/v1/category.py` (702 lines: `reorder`, `bulk_menu_update`, `path`, `roots`, `children`, `summary`), `user_api/views/v1/user.py`, `product_api/views/v1/product.py` |

Five apps have no service module at all: `customer_api`, `inventory_api`,
`origin_api`, `supplier_api`, `user_api`.

**Approved project convention (new features).** The workflow in
[../AGENTS.md](../AGENTS.md#implementation-workflow) is mandatory for new
features: a new domain operation goes in a service, and the view calls it.
Existing apps are grandfathered.

**Ambiguity — `services.py` vs `services/`.** Flat file: `account_api`,
`category_api`, `purchase_api`, `sale_api`, `transaction_api`. Package:
`cart_api`, `meta_api`, `product_api`, `review_api`, `wishlist_api`. No
preference recorded — match the app you are working in, and use a package
when the app will have more than one service module.

**Ambiguity — functions vs classes.** Module-level functions are the majority
(9 modules). Two use classes with static methods: `CategoryImportService`
(`category_api/services.py`) and `BrandService`
(`product_api/services/brand.py`). No preference recorded.

**Current implementation — service style, where functions are used.**

- Prefixed `_` for private helpers.
- `@transaction.atomic` on the public entry point that mutates state.
- Raise `rest_framework.exceptions.ValidationError` for rule violations
  (76 occurrences across 9 modules).
- Return the mutated instance.
- `cart_api` and `wishlist_api` use keyword-only arguments
  (`def add_cart_item(*, user, ...)`); the other apps use positional
  `(user, data)` or `(instance, user)`. No preference recorded.

---

## Serializers

**Current implementation.**

- One module per resource under `<app>/serializers/`, re-exported in
  `__init__.py`.
- `ModelSerializer` for model-backed payloads (78 classes); plain
  `Serializer` for action payloads and response-only shapes (34 classes).
  `drf-writable-nested`'s `WritableNestedModelSerializer` is used once
  (`purchase_api`).
- Read serializers split by action: `<Model>ListSerializer` (lean, list view)
  and `<Model>DetailSerializer` (expanded, retrieve view).
- Validation lives in `validate_<field>()` and `validate()`; `read_only_fields`
  protects audit and generated fields.
- Nested reads use a small summary serializer
  (`UserSummarySerializer`, `CategorySummarySerializer`,
  `TransactionAccountSummarySerializer`) rather than the full detail
  serializer.

**Ambiguity — write-serializer naming.** Combined
`<Model>CreateUpdateSerializer`: `Brand`, `ChartOfAccount`, `PaymentMethod`,
`Product`, `ProductImage`, `ProductVariant`, `Supplier`, `Review`, `CartItem`.
Separate `<Model>CreateSerializer` + `<Model>UpdateSerializer`: `Origin`,
`CustomerProfile`, `Purchase`, `Sale`, `User`. `category_api` uses neither —
it has `CategorySerializer` for writes and `CategoryDetailsSerializer`
(note the plural `Details`) for retrieve.

**Preferred direction (new code only).** Use `<Model>ListSerializer`,
`<Model>DetailSerializer` and `<Model>CreateUpdateSerializer`; split create
and update only when the validation rules genuinely differ.

---

## Views / ViewSets

**Current implementation.**

- `viewsets.ModelViewSet` for CRUD resources; `generics.*` and `APIView` for
  the singleton/auth endpoints in `user_api`; `ViewSet` for
  `CategoryImportViewSet`.
- `get_serializer_class()` branches on `self.action` — used in essentially
  every ViewSet.
- `get_queryset()` narrows by soft-delete state and adds
  `select_related` / `prefetch_related` / `Prefetch` per action.
- Custom endpoints use `@action(detail=..., methods=[...], url_path="...")`
  with a matching `@extend_schema`.
- Audit stamping is done either in `perform_create()`/`perform_update()`
  (`account_api`, `origin_api`, `supplier_api`, `sale_api`, `inventory_api`,
  `product_api` images) or inside the serializer's `create()`/`update()` from
  `self.context["request"].user`. Both are in active use; no preference
  recorded.

---

## Permissions

**Current implementation — five patterns.**

| Pattern | Where |
|---|---|
| `IsAuthenticated` only | `account_api`, `cart_api`, `inventory_api`, `origin_api`, `purchase_api`, `sale_api`, `supplier_api`, `transaction_api`, `wishlist_api`, `product_api` variants |
| `PublicReadPermissionMixin` (+ `IsAuthenticated` for writes) | `product_api` (product, brand, images), `origin_api`, `review_api`, `category_api` |
| `ModelPermissionAccess` (full Django model permissions) | `user_api` `UserViewSet`, `GroupViewSet` |
| `CustomPermissionAccessMixin` (per-action permission) | `category_api` `CategoryViewSet` |
| Bespoke class declared inline in a view module | `CustomerProfilePermission` in `customer_api/views/v1/customer_profile.py` |

No app has a `permissions.py`. The shared classes all live in
`EcommerceBackend/core/permission.py`.

**Preferred direction (new code only).**

- Storefront-readable resources: `PublicReadPermissionMixin`, extending
  `public_actions` for any additional public `@action`:

  ```python
  public_actions = PublicReadPermissionMixin.public_actions + ["my_action"]
  ```

- Everything else: `IsAuthenticated`.
- An action that needs its own permission: `CustomPermissionAccessMixin` plus
  a `custom_permissions` mapping of `action name -> permission codename`. The
  codename must be declared in the model's `Meta.permissions` and shipped in
  a migration.

  ```python
  class CategoryViewSet(
      CustomPermissionAccessMixin,
      PublicReadPermissionMixin,
      viewsets.ModelViewSet,
  ):
      permission_classes = [IsAuthenticated]
      custom_permissions = {
          "mark_as_menu": "mark_category_as_menu",
          "remove_from_menu": "remove_category_from_menu",
      }
  ```

- Use `ModelPermissionAccess` when the whole ViewSet should be model-permission
  driven, as in `user_api`.
- Do not define new permission classes inside a view module.

Superusers hold every permission implicitly.

---

## Soft delete

**Current implementation — four patterns.**

| Pattern | Where |
|---|---|
| `instance.soft_delete()` (sets `is_active` **and** `deleted_at`) | `purchase_api`, `transaction_api`, `review_api`, `cart_api`, `wishlist_api` |
| Manual `updated_by` + `is_active=False` + `deleted_at=now()` + `save()` | `origin_api`, `supplier_api` |
| `is_active=False` only — `deleted_at` never set | `product_api` (product, variant), `customer_api` |
| Hard delete | `user_api` `destroy()` calls `user.delete()`, while the queryset filters on a separate `is_deleted` flag that nothing sets |

Querysets filter correspondingly inconsistently:
`filter(is_active=True, deleted_at__isnull=True)` (`Brand`),
`filter(deleted_at__isnull=True)` (`Category`, `Product`),
`filter(is_active=True)` (others).

**Preferred direction (new code only).** Call
`instance.soft_delete()` from `SoftDeleteModel`, and filter querysets with
`deleted_at__isnull=True`. Stamp `updated_by` in a separate `save()` before
the soft delete when audit attribution is needed — `review_api` shows the
pattern.

---

## Filtering

**Current implementation — three patterns.**

- Dedicated `<app>/filters.py` with a `FilterSet`, referenced as
  `filterset_class`: `account_api` (`ChartOfAccountFilter`), `category_api`
  (`CategoryFilter`).
- `FilterSet` defined inline in the view module: `ProductFilter` in
  `product_api/views/v1/product.py`.
- `filterset_fields = [...]` declared directly on the ViewSet: every other
  app.

**Preferred direction (new code only).** Use `filterset_fields` for plain
field equality. As soon as a filter needs a `method=`, custom parsing or a
`help_text`, move it into `<app>/filters.py` as a `FilterSet` class.

---

## Validation

**Current implementation.** Both layers validate.

- Serializers: `validate_<field>()` and `validate()` for shape, presence and
  cross-field rules.
- Services: domain and state-machine rules, raising
  `rest_framework.exceptions.ValidationError` — e.g. "Only draft purchases can
  be confirmed", "Total debit and credit must be equal", stock availability.

**Preferred direction (new code only).** Input shape and field-level rules go
in the serializer. Rules that depend on current persisted state, other
records, or a status transition go in the service.

---

## Exceptions

**Current implementation.** Raise DRF exceptions
(`ValidationError`, `NotFound`, `PermissionDenied`) and let
`EcommerceBackend.core.exceptions.custom_exception_handler` shape the
response. There are no custom exception classes anywhere in the codebase.

---

## Transactions

**Current implementation.** `transaction.atomic` appears in services (10
modules), views (`category_api` `reorder`, `account_api`, `product_api`
images) and one serializer (`user_api/serializers/auth.py`, wrapping
`User` + `CustomerProfile` creation).

**Preferred direction (new code only).** Wrap the service entry point, as a
decorator on the public function.

---

## Admin

**Current implementation.** `@admin.register(Model)` with a
`<Model>Admin(admin.ModelAdmin)` class, setting `list_display`,
`list_filter`, `search_fields` and `readonly_fields`. `review_api/admin.py`
(209 lines) additionally defines admin actions.
`user_api` registers `Permission` with `admin.site.register(...)` — the only
place not using the decorator.
`inventory_api`'s class is named `PurchaseAdmin` though it registers
`InventoryMovement`.

---

## Migrations

**Approved project convention.**

- Never edit an applied migration. Create a new one.
- Review generated migrations before committing.
- A new entry in a model's `Meta.permissions` requires its own migration.

**Current implementation.** ~70 migrations across the apps; no data-migration
framework, no squashing, no `RunPython` conventions established.

---

## Naming

- Apps: `<domain>_api`.
- Models: singular PascalCase. Choice enums: `models.TextChoices` (or
  `IntegerChoices` in `core/choices.py`).
- Serializers: `<Model><Role>Serializer`.
- ViewSets: `<Model>ViewSet`; non-viewset views: `<Purpose>View`.
- Router basenames: mostly singular (`brand`, `product`, `origin`), sometimes
  plural (`purchases`, `sales`, `wishlists`, `categories`, `roles`, `users`).
  Inconsistent; no preference recorded.
- Services: `<verb>_<noun>` (`create_sale`, `confirm_purchase`,
  `soft_delete_product_image`); private helpers prefixed `_`.
- URL paths and `url_path` values: plural, kebab-case.
- Files: snake_case, one resource per module.

---

## Imports, typing and formatting

**Current implementation.**

- Absolute imports throughout, grouped stdlib → Django → third-party →
  `EcommerceBackend.core` → local app, separated by blank lines.
- Many modules open with a path comment (`# product_api/views/v1/brand.py`).
- **No type annotations** are used, apart from `User.full_name -> str`.
- flake8 with the config in `.flake8`; default 79-column limit; `# noqa` used
  sparingly for unavoidable long lines. `tests.py`, `migrations`, `env.py`
  and virtualenvs are excluded from linting.
- No black, isort, mypy, pre-commit or editorconfig in the repository.

---

## Testing

See [testing.md](testing.md).

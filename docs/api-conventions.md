# API Conventions

Describes the **current implementation**. Where the repository is
inconsistent, the pattern to follow for new code is in
[conventions.md](conventions.md).

---

## Versioning and URLs

- Every endpoint is served under `/api/v1/`.
- Views live in `<app>/views/v1/`, routes in `<app>/urls/v1.py`.
- `<app>/urls/__init__.py` mounts `v1/`; `EcommerceBackend/all_urls.py`
  concatenates every app's `urlpatterns` under `api/`.
- Resource paths are plural and kebab-cased:
  `/api/v1/chart-of-accounts/`, `/api/v1/inventory-movements/`,
  `/api/v1/payment-methods/`, `/api/v1/product-images/`.
- Custom actions use kebab-cased `url_path`:
  `/api/v1/categories/{id}/mark-as-menu/`,
  `/api/v1/purchases/{id}/confirm/`, `/api/v1/transactions/{id}/post/`.
- Most viewsets are registered with `DefaultRouter`. `meta_api` uses plain
  `path()`; `user_api` uses both (`auth/*`, `users/me/*`, `permissions/`,
  `users/verify/` are explicit paths).

## Authentication

- JWT via `rest_framework_simplejwt.authentication.JWTAuthentication`, set as
  the global default.
- `Authorization: Bearer <access token>`.
- `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` — an endpoint is protected
  unless its view opts out.

## Pagination

- Global default: `EcommerceBackend.core.pagination.Pagination`
  (there is no class named `StandardPagination`).
- Page size 10, overridable with `?page_size=`, capped at 100.
- An invalid page number falls back to the first page; an out-of-range page
  falls back to the last page rather than raising 404.
- Response shape:

```json
{
  "count": 42,
  "total_pages": 5,
  "current_page": 1,
  "next": "http://.../?page=2",
  "previous": null,
  "results": []
}
```

- Individual actions can opt out with `pagination_class=None`
  (e.g. `GET /api/v1/categories/path/`).

## Success response format

**There is no global success envelope.** Standard CRUD endpoints return the
serializer output directly, and list endpoints return the paginated shape
above.

Two places do wrap responses, and they are the exception rather than the
rule:

- `POST /api/v1/auth/register/` returns `{"success", "message", "data"}`.
- Six `user_api` custom actions (`destroy`, `assign-role`, `remove-role`,
  `change-password`, `change-username`, `change-email`) return
  `{"success": true, "message": "..."}`.

Do not add a new envelope to an existing endpoint without approval — clients
depend on the current shapes.

## Error response format

All DRF exceptions pass through
`EcommerceBackend.core.exceptions.custom_exception_handler`, which rewrites
the body to:

```json
{
  "success": false,
  "message": "First error message, or the DRF detail string",
  "errors": { "field": ["original DRF error payload"] }
}
```

`message` is taken from `detail` when present, otherwise from the first value
in the error dict. Raise
`rest_framework.exceptions.ValidationError` / `NotFound` /
`PermissionDenied` and let the handler shape the response.

## Filtering, search and ordering

- Backends declared per ViewSet, typically
  `[DjangoFilterBackend, SearchFilter, OrderingFilter]`.
- `SearchFilter` and `OrderingFilter` are DRF's own
  (`rest_framework.filters`) — `EcommerceBackend/core/filter.py` is empty.
- Filtering is declared with `filterset_fields` on the ViewSet (most apps),
  a `FilterSet` class in `<app>/filters.py` (`account_api`, `category_api`),
  or a `FilterSet` defined inline in the view module (`ProductFilter` in
  `product_api/views/v1/product.py`). See
  [conventions.md](conventions.md#filtering).
- Search is declared with `search_fields`; ordering with `ordering_fields`
  plus a default `ordering`.

## Detail lookup

- Default is `pk`.
- `category_api` and `product_api` accept **either a numeric id or a slug** on
  detail routes, using
  `lookup_field = "id"`, `lookup_url_kwarg = "id"`,
  `lookup_value_regex = r"[^/]+"` and a `get_object()` override that branches
  on `lookup_value.isdigit()`.

## Permissions

See [conventions.md](conventions.md#permissions) for the full picture and the
preferred direction for new endpoints.

## OpenAPI / drf-spectacular

- Schema at `/schema/`, Swagger UI at `/docs/`, ReDoc at `/redoc/`.
- **Every** view module in the repository applies
  `@extend_schema(tags=["..."])` at class level. Keep this at 100%.
- Existing tags: `Accounts`, `Authentication`, `Brands`, `Cart`,
  `Categories`, `Categories - Import`, `Customers`, `Inventory Movement`,
  `Meta`, `Origins`, `Permissions & Groups`, `Products`, `Purchases`,
  `Reviews`, `Sale Payment Methods`, `Sales`, `Suppliers`, `Transactions`,
  `Users`, `Wishlists`.
- Custom `@action` endpoints declare `request`, `responses` and
  `description`, and repeat `tags` when the class-level decorator does not
  carry through.
- Non-body inputs are declared with `OpenApiParameter`; a module-level
  constant is used when the same parameter repeats
  (`CATEGORY_LOOKUP_PARAMETER`, `PRODUCT_LOOKUP_PARAMETER`).
- Response-only serializers are written for actions that do not return a
  model (`CategoryStatisticsSerializer`,
  `CategoryBulkMenuUpdateResponseSerializer`, `CategoryPathResponseSerializer`)
  so the schema stays accurate.
- `SPECTACULAR_SETTINGS.ENUM_NAME_OVERRIDES` names shared enums; add an entry
  when a new choice set appears in more than one serializer.

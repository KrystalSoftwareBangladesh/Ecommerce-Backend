# Architecture

Describes the **current implementation**. Conventions and preferred direction
for new code are in [conventions.md](conventions.md). Entities and
relationships are in [domain-model.md](domain-model.md).

---

## Current implementation

### Technologies

| Concern | Implementation |
|---|---|
| Framework | Django 5.2.5 |
| API | Django REST Framework 3.16.1 |
| Auth | `djangorestframework-simplejwt` (JWT) |
| Schema/docs | `drf-spectacular` + `drf-spectacular-sidecar` |
| Filtering | `django-filter` |
| CORS | `django-cors-headers` |
| Nested writes | `drf-writable-nested` (used only in `purchase_api/serializers/purchase.py`) |
| Import parsing | `pandas`, `openpyxl` (used only in `category_api/services.py`) |
| Images | `Pillow` |
| Database | PostgreSQL (`psycopg2-binary`) |
| Server | gunicorn |

`PyMySQL` is required only by the WooCommerce export scripts in `scripts/`,
which run outside Django.

### Application structure

Each business domain is a separate Django app named `<domain>_api`. The 17
apps registered in `LOCAL_APPS` are:

`user_api`, `customer_api`, `account_api`, `transaction_api`, `category_api`,
`supplier_api`, `product_api`, `inventory_api`, `purchase_api`, `sale_api`,
`origin_api`, `review_api`, `meta_api`, `wishlist_api`, `cart_api`,
`content_security_api`, `request_log_api`.

Responsibilities are listed in [domain-model.md](domain-model.md).

`meta_api` is the only app with no models — it exposes choice/enum lookups
(currently moderation statuses) to clients.

`content_security_api` and `request_log_api` are the two cross-cutting
apps. `content_security_api` owns no business domain of its own and instead
reads content belonging to other apps. It
reaches them one way only — through
`content_security_api/services/content_sources.py`, which maps a content
type onto a model, the fields to scan and a queryset. No other module in the
scanner imports `Product` or `Category`, and the scanner never writes to
them, so a new content type is one registry entry rather than a change to
the detection engine.

`request_log_api` observes every HTTP request from middleware and writes one
immutable `RequestLog` row per request. Nothing in the application reads a
request log to make a decision, so it is an observability layer around the
API rather than a dependency of it. See
[Request logging](#request-logging) below.

### Request flow

```text
Request
  → EcommerceBackend/urls.py            (admin/, schema/, docs/, redoc/, api/)
  → EcommerceBackend/all_urls.py        (concatenates every app's urlpatterns)
  → <app>/urls/__init__.py              (mounts v1/)
  → <app>/urls/v1.py                    (DefaultRouter registration or path())
  → <app>/views/v1/<resource>.py        (ViewSet / APIView)
  → <app>/serializers/<resource>.py     (input validation, output shaping)
  → <app>/services*                     (domain operation, where one exists)
  → <app>/models/<resource>.py
  → Database
```

Every endpoint is reachable under `/api/v1/`.

### Layer responsibilities as currently implemented

**Views** handle request/response, choose the serializer via
`get_serializer_class()` on `self.action`, and build querysets. Several views
also contain domain logic directly — see
[conventions.md](conventions.md#where-business-logic-lives).

**Services** hold multi-step domain operations, wrap them in
`transaction.atomic`, and raise `rest_framework.exceptions.ValidationError`.
Ten apps have a service module; five (`customer_api`, `inventory_api`,
`origin_api`, `supplier_api`, `user_api`) have none.

**Serializers** perform field and cross-field validation. Four of them also
delegate writes to services (`product_api/serializers/brand.py`,
`product_api/serializers/product_image.py`,
`cart_api/serializers/cart_item.py`, `review_api/serializers/review.py`).

**Models** hold data, relationships and database constraints, and a small
amount of derived behaviour (`Purchase` totals, `Sale` status transitions,
slug generation on save).

### Authentication and authorization

- `AUTH_USER_MODEL = 'user_api.User'`, extending `AbstractUser` with `role`,
  `middle_name`, `is_deleted` and `added_at`.
- `AUTHENTICATION_BACKENDS` = `user_api.backends.EmailOrUsernameBackend` then
  Django's `ModelBackend`, so login accepts either identifier.
- `DEFAULT_AUTHENTICATION_CLASSES = [JWTAuthentication]`.
- `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` — endpoints are protected
  unless a view opts out.
- Token endpoints: `POST /api/v1/auth/register/`, `/auth/login/`,
  `/auth/logout/` (blacklists the refresh token), `/auth/refresh/`.
- Roles are Django `Group`s, exposed as `/api/v1/roles/`; assignment via
  `/api/v1/users/{id}/assign-role/` and `/remove-role/`.
- Model-level permissions are enforced by the shared classes described in
  [conventions.md](conventions.md#permissions).

### Database

- PostgreSQL in every deployed environment; `DATABASES` comes verbatim from
  `EcommerceBackend/env.py`.
- Tests run against SQLite in memory via
  `EcommerceBackend/test_settings.py`.
- `DEFAULT_AUTO_FIELD = BigAutoField`.
- Schema changes are applied by the deploy workflow
  (`python manage.py migrate`).
- No database routers, no replicas, no partitioning.

### Shared core components

Location: `EcommerceBackend/core/`. Reuse these instead of writing new ones.

**`models.py`** — abstract bases:

| Class | Provides |
|---|---|
| `TimeStampedModel` | `created_at`, `updated_at` (both indexed) |
| `UserStampedModel` | `created_by`, `updated_by` (FK to `User`, `SET_NULL`) |
| `SoftDeleteModel` | `is_active`, `deleted_at`, plus `soft_delete()` and `restore()` |
| `ModerationModel` | `status`, `approved_at`, `approved_by`, plus `approve()`, `reject()`, `reset_to_pending()`, `is_approved` |

Most domain models inherit
`TimeStampedModel, UserStampedModel, SoftDeleteModel`. `Review` adds
`ModerationModel`.

**`pagination.py`** — `Pagination`, wired globally as
`DEFAULT_PAGINATION_CLASS`. See [api-conventions.md](api-conventions.md).

**`permission.py`** — `PublicReadPermissionMixin`, `ModelPermissionAccess`,
`CustomPermissionAccessMixin`. See
[conventions.md](conventions.md#permissions).

**`choices.py`** — `ModerationStatus`, `CartStatus`.

**`exceptions.py`** — `custom_exception_handler`, wired as DRF's
`EXCEPTION_HANDLER`.

**`filter.py`** — currently **empty**. There is no shared `SearchFilter`;
apps use `rest_framework.filters.SearchFilter` directly.

### External integrations

None at runtime. The only outbound integration is the WooCommerce export
tooling in `scripts/`, run manually against a MySQL source to produce the
JSON seeds in `resources/`, which are then loaded by the management commands
listed in `README.md`.

### Bulk import

`category_api/services.py` implements `CategoryImportService` with
`import_from_json()`, `import_from_csv()` and `import_from_xlsx()` —
atomic, with row-level error tracking, parent resolution by id or name, slug
generation and audit stamping. Exposed at
`POST /api/v1/categories/import-{json,csv,xlsx}/`.
Full usage: [category-import-api.md](category-import-api.md).

### Request logging

`request_log_api.middleware.RequestLogMiddleware` is registered directly
after `CorsMiddleware`, so it is the outermost application middleware: one
record covers the whole lifecycle, every response is observed including 4xx
and 5xx, and a CORS preflight is answered ahead of it rather than logged.

```text
Request
  → RequestLogMiddleware        (request id, timer, request context)
  → application
  → RequestLogMiddleware        (status, response, duration, exception)
  → services/sanitizer.py       (recursive redaction, centralised)
  → services/builder.py         (one structured event dict)
  → services/storage.py         (RequestLogStorage -> PostgreSQL)
```

Properties that matter:

- **Best effort.** Every step is wrapped; a logging failure is written to
  this module's logger and swallowed. The API response is never affected.
- **Immutable.** The ViewSet exposes list and retrieve only; create, update
  and delete are not routed, and the admin disables all three.
- **Sanitised centrally.** Request payloads, response payloads, query
  parameters, multipart fields, headers, error details and tracebacks all
  pass through `services/sanitizer.py`. Individual endpoints never decide
  what is sensitive. `Authorization` and `Cookie` are not on the captured
  header allow-list, so they are never read at all.
- **No file contents.** Multipart uploads are recorded by field name,
  filename, content type and size only.
- **Storage is swappable.** The middleware and builder produce a plain dict
  and hand it to `RequestLogStorage`. Moving to another logging backend is a
  new subclass plus the `REQUEST_LOG_STORAGE` setting; no queue, worker or
  external service exists today.
- **Separate from audit logging.** Request logs answer "who called what and
  what happened", not "which field changed from what to what".

Defaults live in `request_log_api/constants.py` and every one of them is
overridable with a `REQUEST_LOG_*` setting, read through
`request_log_api/services/config.py`: `REQUEST_LOG_ENABLED`,
`REQUEST_LOG_EXCLUDED_PATH_PREFIXES`, `REQUEST_LOG_TRUSTED_PROXY_COUNT`,
`REQUEST_LOG_MAX_REQUEST_BODY_BYTES`, `REQUEST_LOG_MAX_RESPONSE_BODY_BYTES`,
`REQUEST_LOG_MAX_TRACEBACK_LENGTH`, `REQUEST_LOG_SENSITIVE_EXACT_KEYS`,
`REQUEST_LOG_SENSITIVE_KEY_FRAGMENTS`, `REQUEST_LOG_STORAGE`.

`REQUEST_LOG_TRUSTED_PROXY_COUNT` defaults to `0`, which means
`X-Forwarded-For` is recorded but never trusted and `REMOTE_ADDR` is the
client. A deployment behind a load balancer must set it to the number of
proxies it actually runs.

Full specification: [api-request-logging-plan.md](api-request-logging-plan.md).

### Background jobs, caching, email, signals

**None are present.** There is no Celery, no task queue, no cron, no cache
backend, no email backend and no Django signal handlers anywhere in the
codebase. Introducing any of these is an architectural change — ask first.

### File and media handling

- `MEDIA_ROOT = BASE_DIR / 'media'`, `MEDIA_URL = '/media/'`; local
  filesystem storage only.
- Two upload fields exist: `Brand.logo` (`brands/logos/`) and
  `ProductImage.image` (`products/images/`).
- Upload endpoints use `MultiPartParser` / `FormParser`.
- Product image lifecycle (default selection, ordering, replacement, soft
  delete) is implemented in `product_api/services/product.py`.

### Deployment

`.github/workflows/`:

- `linter.yml` — runs flake8 on push/PR to `dev`. The blocking step is
  `flake8 ./ --select=E9,E501,F63,F7,F82,F401`; a second style pass runs with
  `--exit-zero`. **Tests are not run in CI.**
- `deploy_bestcomputerhub_dev.yml` — on push to `dev`, scp the tree to the
  dev server, then `pip install -r requirements.txt`, `migrate`,
  `collectstatic`, restart gunicorn.
- `deploy_zayrahlife_dev.yml.disable` and `deploy_bikkhato_dev.yml.disable`
  are the same workflow, currently disabled.

---

## Future / planned architecture

Nothing is approved for future architecture at this time. Preferred
directions for new code (soft delete, permissions, service placement) are
recorded in [conventions.md](conventions.md) and in the decisions log in
[../AGENTS.md](../AGENTS.md).

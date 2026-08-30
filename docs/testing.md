# Testing

Describes the **current implementation** and the approved expectation.

---

## Framework and commands

Django's built-in test runner with `unittest`-style classes and DRF's test
client. There is no pytest, no tox, no coverage tooling.

```bash
source env/bin/activate

# whole suite
python manage.py test --settings=EcommerceBackend.test_settings

# one app
python manage.py test sale_api --settings=EcommerceBackend.test_settings

# one class or method
python manage.py test sale_api.tests.SaleInvoiceGenerationTests \
  --settings=EcommerceBackend.test_settings
```

`EcommerceBackend/test_settings.py` overrides `settings.py` with SQLite
in-memory, the MD5 password hasher and filesystem storage. Running without
`--settings` uses the PostgreSQL database from `EcommerceBackend/env.py`.

---

## Structure

**Current implementation.** A flat `tests.py` per app, except
`content_security_api` and `request_log_api`, which use a `tests/` package.
There are no fixtures and no shared base test case; `content_security_api`
is the only app with a `factories.py`.

| App | `tests.py` |
|---|---|
| `product_api` | 542 lines |
| `sale_api` | 469 |
| `transaction_api` | 450 |
| `account_api` | 419 |
| `purchase_api` | 284 |
| `category_api` | 243 |
| `user_api` | 234 |
| `cart_api`, `customer_api`, `inventory_api`, `meta_api`, `review_api`, `supplier_api`, `wishlist_api` | 3-line placeholder |
| `origin_api` | no `tests.py` at all |
| `content_security_api`, `request_log_api` | `tests/` package — **linted**, since `.flake8` excludes `tests.py` by name only |

`request_log_api/tests/` additionally ships `urls.py`, a probe URLconf
mounted with `override_settings(ROOT_URLCONF=...)` so the middleware can be
exercised against an upload, an unhandled exception and a payload of secrets
without touching a real business endpoint.

`.flake8` excludes `tests.py` from linting, so a flat test module is not
style-checked; a `tests/` package is.

---

## Patterns in the suites that do exist

- Classes named `<Feature>ApiTests` / `<Feature>APITestCase`, methods named
  `test_<behaviour>_<expected_outcome>`.
- Base class is `django.test.TestCase` or
  `rest_framework.test.APITestCase`, used interchangeably.
- Fixtures are built in `setUp()` with direct `Model.objects.create(...)`
  calls — no factory library.
- Authentication via `self.client.force_authenticate(user=...)`
  (`APIClient` from `rest_framework.test`).
- API tests hit **hardcoded absolute URLs** (`'/api/v1/product-variants/'`),
  not `reverse()`.
- Permission tests attach `django.contrib.auth.models.Permission` objects
  looked up through `ContentType` — see `category_api/tests.py` and
  `user_api/tests.py`.
- Service tests import the service function directly and assert on the
  resulting rows (`sale_api`, `purchase_api`, `account_api`,
  `transaction_api`, `product_api`).
- Image tests build an in-memory PNG with `PIL` +
  `SimpleUploadedFile` (`product_api`).

---

## Expectation

**Approved project convention (2026-08-23).** Tests are **best effort**.
There is no coverage threshold and no rule that the suite must pass before a
task is complete. Add tests where the change warrants them; prefer API tests
through `/api/v1/`.

CI does not run tests — `.github/workflows/linter.yml` runs flake8 only.

---

## Known state of the suite

As of 2026-08-30, `python manage.py test --settings=EcommerceBackend.test_settings`
reports **407 tests, 16 failures and 5 errors**. The failures and errors are
pre-existing and unrelated to any current work — the count was identical
before `request_log_api` was added, which contributed 90 passing tests:

| Symptom | Cause |
|---|---|
| `product_api.tests` fails to import — the entire module never runs | `product_api/tests.py` imports `reorder_product_images`, `replace_product_image`, `set_product_image_default`, `soft_delete_product_image`, `upload_product_image` from `product_api.services`, but `product_api/services/__init__.py` re-exports only `BrandService` |
| 11 `user_api` failures, all `404` | Tests request `/auth/register/`, `/users/me/`; the real routes are `/api/v1/auth/register/`, `/api/v1/users/me/` |
| `test_nested_import` error | `test_nested_import.py` at the repository root is a `manage.py shell` script, not a test module, but the runner tries to load it |
| Remaining failures in `account_api`, `transaction_api`, `sale_api`, `purchase_api` | Not yet diagnosed |

**Do not treat a red suite as evidence that your change broke something** —
run the relevant app's tests before and after, and compare. Per
[../AGENTS.md](../AGENTS.md#agent-behaviour-rules), report these rather than
fixing them as part of an unrelated task.

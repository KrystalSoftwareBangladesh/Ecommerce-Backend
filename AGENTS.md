# AGENTS.md

Primary entry point for coding agents. Read this before starting any task.

## Project identity

Reusable, business-agnostic Django + Django REST Framework e-commerce backend.
One codebase serves several storefronts (Zayrah Life, Best Computer Hub,
bikkhato). Deployments differ by configuration, never by code.

**Do not introduce store-specific logic.**

## Stack

Django 5.2.5 · DRF 3.16.1 · SimpleJWT · drf-spectacular · django-filter ·
PostgreSQL · gunicorn. Full list in `requirements.txt`.

## Architecture at a glance

- 15 domain apps, all named `*_api`, registered in `LOCAL_APPS`
  (`EcommerceBackend/settings.py`).
- Shared components live in `EcommerceBackend/core/`
  (`models.py`, `pagination.py`, `permission.py`, `choices.py`,
  `exceptions.py`). Reuse them before writing new ones.
- Routing: `EcommerceBackend/urls.py` → `api/` →
  `EcommerceBackend/all_urls.py` → each app's `urls/__init__.py` → `urls/v1.py`.
  Every endpoint is served under **`/api/v1/`**.
- Settings read from `EcommerceBackend/env.py`, which is gitignored and
  created from `.env.example`.

Details: [docs/architecture.md](docs/architecture.md) ·
[docs/domain-model.md](docs/domain-model.md)

## Standard app layout

```text
<name>_api/
├── models/          # package; customer_api and meta_api use a flat models.py
├── serializers/
├── services.py      # or services/ package — see docs/conventions.md
├── views/v1/
├── urls/            # __init__.py mounts v1/, v1.py registers the router
├── migrations/
├── filters.py       # only where a FilterSet class is needed
├── admin.py
├── apps.py
└── tests.py
```

## Repository rules

- **Never edit an applied migration.** Create a new one and review it before
  committing.
- **flake8 is the source of truth for linting.** Run `flake8` (or
  `flake8 path/to/file.py`) before finishing; the repo is currently clean and
  CI blocks on it. Do not add `# noqa` without a reason.
- Search before creating. Before adding a model, serializer, view, service,
  filter, permission or utility, look for an existing one and prefer
  extending it.
- Avoid N+1 queries — use `select_related()` / `prefetch_related()` /
  `Prefetch`.
- Do not commit `EcommerceBackend/env.py`, `media/`, or secrets.
- Branches are named `<issue-number>-<kebab-slug>`; commits read
  `done:` / `fixed:` / `updt:` + `issue#NNN - description`; PRs target `dev`.

## Agent behaviour rules

These are approved project rules, not suggestions.

1. **Inspect before modifying.** Read the file you are changing *and* the
   equivalent file in a neighbouring app before writing code. Conventions in
   this repo are not uniform — match the local pattern.
2. **Ask when a business rule is ambiguous.** Especially for accounting,
   inventory, pricing and permissions. Do not infer a rule from a single
   example. See [docs/business-rules.md](docs/business-rules.md).
3. **Report pre-existing breakage; do not fix it unasked.** If you find a
   broken import, failing test or dead module unrelated to your task, name it
   in your summary and leave it alone.
4. **Conventions marked "Preferred direction" in
   [docs/conventions.md](docs/conventions.md) apply to new code only.** Do not
   retrofit existing apps to them.

## Implementation workflow

**Mandatory for new features** (approved 2026-08-23). Existing apps are
grandfathered and are not retrofitted.

```text
Models → Services → Serializers → APIs/ViewSets → Permissions → Admin → Tests
```

1. **Models** — inherit the relevant abstract bases from
   `EcommerceBackend/core/models.py`; add indexes, constraints and
   `related_name`; generate the migration.
2. **Services** — put the domain operation in the app's service module, wrap
   state changes in `transaction.atomic`, raise
   `rest_framework.exceptions.ValidationError` for rule violations.
3. **Serializers** — separate list / detail / write serializers; field-level
   and cross-field input validation lives here.
4. **APIs/ViewSets** — keep thin; select the serializer in
   `get_serializer_class()` on `self.action`; register in `urls/v1.py`; tag
   with `@extend_schema(tags=[...])`.
5. **Permissions** — see [docs/conventions.md](docs/conventions.md#permissions).
6. **Admin** — register with `@admin.register(Model)`.
7. **Tests** — see below.

## Coding conventions

Short version: 4-space indent, ≤79 columns (flake8 default), absolute imports,
stdlib → Django → third-party → `EcommerceBackend.core` → local app. No type
annotations are used in the codebase today.

Everything else — models, services, serializers, views, permissions, soft
delete, filtering, naming, migrations, OpenAPI — is in
[docs/conventions.md](docs/conventions.md). Read the relevant section before
implementing.

## Testing expectations

Tests are **best effort**, not a hard gate (approved 2026-08-23). Add tests
where the change warrants them; prefer API tests through `/api/v1/`.

Current state, for accuracy: 84 tests exist, 7 of 15 apps have placeholder
`tests.py`, `origin_api` has none, 22 currently fail, and CI does not run
them. Do not treat a failing suite as evidence your change broke something —
check [docs/testing.md](docs/testing.md) first.

## Commands

```bash
source env/bin/activate

python manage.py migrate
python manage.py runserver
python manage.py test --settings=EcommerceBackend.test_settings
python manage.py test <app> --settings=EcommerceBackend.test_settings
python manage.py makemigrations <app>
flake8
```

Swagger UI at `/docs/`, ReDoc at `/redoc/`, raw schema at `/schema/`.

## Documentation maintenance

Documentation is part of development:

1. Update [docs/project-structure.md](docs/project-structure.md) when files or
   folders are created, deleted, renamed or moved.
2. Update [docs/architecture.md](docs/architecture.md) if architecture changes.
3. Update [docs/business-rules.md](docs/business-rules.md) if business rules
   change.
4. Update [docs/domain-model.md](docs/domain-model.md) if models or their
   relationships change.

## Completion checklist

- [ ] Code implemented, matching the neighbouring app's pattern
- [ ] Migrations created and reviewed (never edited in place)
- [ ] URLs registered under `urls/v1.py`
- [ ] `@extend_schema(tags=[...])` applied
- [ ] Admin updated if needed
- [ ] Tests added where warranted
- [ ] `flake8` clean
- [ ] Documentation updated (see above)
- [ ] Pre-existing problems found along the way reported, not silently fixed

## Decisions log

Approved project decisions. Append new entries here.

| Date | Decision |
|---|---|
| 2026-08-23 | Models → Services → Serializers → APIs/ViewSets → Permissions → Admin → Tests is mandatory for new features; existing apps are grandfathered. |
| 2026-08-23 | Where the repo is inconsistent, docs describe all existing patterns and mark a preferred direction for new code only. |
| 2026-08-23 | Preferred soft delete for new code: `SoftDeleteModel.soft_delete()`. |
| 2026-08-23 | Preferred permissions for new endpoints: `PublicReadPermissionMixin` for storefront-readable resources, `IsAuthenticated` otherwise, `CustomPermissionAccessMixin` for actions needing a dedicated permission. |
| 2026-08-23 | Testing is best effort; no hard coverage gate. |
| 2026-08-23 | Agents report pre-existing breakage rather than fixing it unasked. |
| 2026-08-25 | Content Security Scanner lives in `content_security_api`, a cross-cutting app that reads other apps' content through `services/content_sources.py` only and never writes to them. |
| 2026-08-25 | Scanner severity weights (INFO 0 / LOW 10 / MEDIUM 25 / HIGH 50 / CRITICAL 80), capped-sum risk score and status thresholds (0 CLEAN, 1-24 LOW_RISK, 25-49 REVIEW, 50-79 HIGH_RISK, 80-100 CRITICAL) approved. See [docs/business-rules.md](docs/business-rules.md#content-security). |
| 2026-08-25 | The scanner ships no keyword or domain rules. Only deterministic technical rules are seeded; suspicious keyword and domain lists are entered by authorised users. |
| 2026-08-25 | Detection rules take no user-supplied regular expression; matching modes are fixed (`WORD`/`SUBSTRING`, `EXACT`/`SUBDOMAIN`) and rules are global, not content-type scoped. |
| 2026-08-25 | Finding review is `PENDING -> FALSE_POSITIVE` or `PENDING -> CONFIRMED -> RESOLVED`; review never changes a scan's risk score or status, and a re-scan carries review state forward for identical findings. |
| 2026-08-25 | The scanner detects and reports only. It never modifies, sanitises, unpublishes or deactivates scanned content, and makes no external network request. |

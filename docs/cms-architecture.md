# CMS — Technical Architecture & Data Model Design

**Version:** 1.0 (draft for technical review)
**Status:** Awaiting approval — implementation must not start before
the open questions in [§16](#16-open-questions) are answered.
**Input:** `CMS Backend Requirement Specification v1.0`
**Date:** 2026-11-06

---

## 1. Executive summary

The CMS is implemented as **Wagtail embedded in the existing Django
project**, exposed headlessly:

- **Wagtail is the CMS engine and single source of truth** — page tree,
  revisions, drafts, scheduling, locking, reference tracking, media
  renditions and the activity log all come from Wagtail models.
- **Nuxt Admin is the primary editing surface**, driving the CMS through
  DRF management APIs under `/api/v1/cms/` (JWT auth, existing RBAC).
- **Wagtail Admin** is mounted at `/cms-admin/` (session auth, staff
  users) and writes the same models. Business rules live in the service
  layer and in model-level constraints so both interfaces obey them.
- **The storefront** consumes published content through public read-only
  APIs. Pages are never served by Django; Nuxt renders everything.
- Everything lives in one new app, `cms_api`, plus new third-party apps
  (Wagtail and its dependencies). No changes to existing domain apps.

## 2. Audit findings (current state)

Verified 2026-11-06 on branch `463-cms-feature`:

1. **Wagtail is not installed.** No reference anywhere; not in
   `requirements.txt`. The integration itself is new work.
2. **No `CACHES` setting exists.** No Django cache is configured in
   `EcommerceBackend/settings.py`; no code uses `django.core.cache`.
   Requirement 13 (API caching + invalidation) needs new cache
   infrastructure. Redis is already the Celery broker, so Redis is
   available on every deployment.
3. **RBAC** = `user_api.User` (extends `AbstractUser`, `role` in
   OWNER/STAFF/CUSTOMER) + Django model permissions, including custom
   codenames declared in `Meta.permissions`
   (e.g. `blog_api.BlogPost`: `publish_blog_post`, `unpublish_blog_post`).
   Enforced in DRF via `ModelPermissionAccess` /
   `CustomPermissionAccessMixin` (`EcommerceBackend/core/permission.py`).
4. **Closest prior art is `blog_api`** — draft/publish split with
   non-writable `status`/`published_at`, publish/unpublish as dedicated
   custom-permission actions, SEO fields on the model. The CMS follows
   the same shape where Wagtail does not already provide the behaviour.
5. **`drf-writable-nested`** is installed and is the convention for
   nested writes — used for page composition rows.
6. **Celery + Beat** are deployed (`EcommerceBackend/celery.py`, two
   Beat tasks). New scheduled tasks join the existing Beat schedule.
7. **`FRONTEND_BASE_URL_SETTINGS`** exists in `env.py` — reused for
   Wagtail admin base URL and preview/redirect targets.
8. **Routing**: `EcommerceBackend/all_urls.py` concatenates each app's
   `urls.urlpatterns` under `/api/v1/`. `cms_api` plugs in the same way.

## 3. Architectural decisions

| # | Decision |
|---|---|
| AD-1 | Wagtail is embedded in this project (new third-party apps + `cms_api`); there is no separate CMS service, frontend or database. |
| AD-2 | Pages are **never served by Django**. The Wagtail page `serve()` view is unused; Nuxt renders pages from the public API. `wagtail.urls` (page serving) is not mounted. |
| AD-3 | One concrete page model, `CmsPage`, with a `template_key`. Templates only seed an initial composition at creation; they never constrain later editing. |
| AD-4 | Global sections are Wagtail **snippets** (`CmsSection`) with `DraftStateMixin`, `RevisionMixin`, `PreviewableMixin`, `LockableMixin` — independent draft/publish/revisions. |
| AD-5 | Section *types* are code-defined StreamField blocks (`cms_api/sections/`). Administrators cannot create new types. A read-only schema API lets Nuxt Admin render editing forms. |
| AD-6 | Page composition = ordered `CmsPageSection` rows (Wagtail `Orderable`, `ParentalKey` to the page), each row being **either** a reference to a global `CmsSection` **or** inline page-specific content. Removing a row never deletes the referenced section. Page-specific content is revisioned with its page. |
| AD-7 | Publishing = Wagtail revision publish. Saving a draft never touches published content; public APIs read only `live` state. A global section's published content is resolved live, so publishing it updates every referencing page at once. |
| AD-8 | Redirects use `wagtail.contrib.redirects`. Slug-change redirects are created by our publish service (the API path, not only the Wagtail admin prompt). Chains are collapsed; every change is audit-logged. |
| AD-9 | Media for CMS content uses **Wagtail images/documents** (same `MEDIA_ROOT` storage as today — no new storage infrastructure). Existing plain-`ImageField` media (`ProductImage`, blog featured images) stays untouched. |
| AD-10 | Audit logging uses Wagtail's `log_action` / `LogEntry`, so Wagtail Admin actions and API actions land in one trail. |
| AD-11 | CMS permissions are Django model permissions on `cms_api` models (custom `Meta.permissions` codenames), enforced server-side by the existing permission classes. Wagtail Admin access is additionally gated by `is_staff` (see Q5). |
| AD-12 | Caching: introduce `CACHES` (Redis in deployments, LocMem in dev) with **event-driven invalidation** on publish/unpublish/delete via `transaction.on_commit`. The consistency window after a successful publish is zero by design (keys are dropped in the same commit cycle); TTLs are a safety net only. |
| AD-13 | Scheduling reuses Wagtail's `go_live_at` / `expire_at` machinery, swept by a task on the **existing Celery Beat** (exact entry point verified in Phase 0). |
| AD-14 | E-commerce entities are **referenced, never copied**. Section content holds entity IDs; dynamic collections resolve to ordered product-ID lists at read time through existing `product_api` querysets. Pricing/product payloads come from existing product APIs — the CMS API returns references, not product data. |
| AD-15 | Preview uses short-lived **signed preview tokens** (Django `TimestampSigner`); draft content is reachable only through a token, never through plain public endpoints. |

## 4. Project layout

```text
EcommerceBackend/settings.py      # THIRD_PARTY_APPS += wagtail apps;
                                  # CACHES; TEMPLATES += request ctx
EcommerceBackend/all_urls.py      # += cms_api urls; /cms-admin/ mount
cms_api/
├── models/                       # CmsPage, CmsSection, CmsPageSection,
│   │                             # CmsNavigationMenu, CmsNavigationItem,
│   │                             # CmsMediaConfig
│   └── __init__.py               # re-exports + __all__
├── sections/                     # section-type registry: one StructBlock
│   │                             # per type + get_section_schema()
│   └── __init__.py
├── services/
│   ├── pages.py                  # create-from-template, publish, slug
│   │                             # change + redirect creation, archive
│   ├── sections.py               # section publish fan-out, delete guard
│   ├── composition.py            # composition writes (rows), reorder
│   ├── navigation.py
│   ├── preview.py                # token issue/verify
│   ├── redirects.py              # chain collapse, loop prevention
│   └── __init__.py               # re-exports
├── serializers/                  # one module per resource; list/detail/
│                                 # write split per conventions
├── views/v1/                     # thin; re-exported for urls/v1.py
├── urls/                         # __init__.py wraps v1/ with 'v1/'
├── migrations/
├── admin.py                      # Django admin registrations
├── apps.py
└── tests.py
```

App registration order: Wagtail apps go in `THIRD_PARTY_APPS` per the
Wagtail install checklist (`wagtail.contrib.redirects`, `wagtail.embeds`,
`wagtail.sites`, `wagtail.users`, `wagtail.snippets`, `wagtail.documents`,
`wagtail.images`, `wagtail.search`, `wagtail.admin`, `wagtail`, then
`modelcluster`, `taggit`), `cms_api` appended to `LOCAL_APPS`.

Settings additions (all config from `env.py` where env-specific):

- `CACHES` — Redis URL (new `CMS_CACHE_URL_SETTINGS`, fallback LocMem).
- `TEMPLATES[...]['context_processors']` += `request` (required by
  Wagtail admin templates; harmless for the rest).
- `WAGTAILADMIN_BASE_URL = FRONTEND_BASE_URL_SETTINGS`.
- `WAGTAIL_SITE_NAME`, `WAGTAILIMAGES_SERVE_METHOD = "direct"` (media
  served by the existing media serving, renditions generated on access).
- `CMS_RESERVED_PATHS` — see [§9](#9-urls-seo-redirects-sitemap).

URL mounts in `EcommerceBackend/all_urls.py` / `urls.py`:

- `cms_api.urls` under `/api/v1/` (same pattern as every app).
- `path("cms-admin/", include(wagtail.admin.urls))` — admin only.
- **Not mounted:** `wagtail.urls` (page serving), since Nuxt renders.

## 5. Data model

Wagtail-owned tables (created by Wagtail migrations, not designed here):
`wagtailcore_page` (tree, `url_path`, live/draft/scheduling fields),
`wagtailcore_revision`, `wagtailcore_referenceindex` (reference
tracking incl. StreamField content), `wagtailcore_logentry` (audit),
`wagtailcore_collection` + `wagtailimages_image` + renditions,
`wagtaildocs_document`, `wagtailcontrib_redirects_redirect`.

### 5.1 `CmsPage` (wagtail `Page` subclass)

| Field | Type | Notes |
|---|---|---|
| `template_key` | CharField(choices) | BLANK / LANDING / ABOUT / CONTACT / CAMPAIGN (code registry; seeds initial composition at create) |
| `seo_title` | CharField(255, blank) | |
| `seo_description` | CharField(500, blank) | |
| `meta_keywords` | CharField(255, blank) | optional per spec |
| `og_title`, `og_description` | CharField(blank) | Open Graph |
| `og_image` | FK → `wagtailimages.Image`, null | reference, not duplication |
| `canonical_url` | URLField(blank) | |
| `seo_noindex`, `seo_nofollow` | BooleanField(default=False) | |
| `archived_at` | DateTimeField(null) | archive ≠ delete |

Inherited from `Page`: `title`, `slug` (unique per parent → globally
unique `url_path` — the no-duplicate-URL guarantee), `draft_title`,
`live`, `has_unpublished_changes`, `first_published_at`,
`last_published_at`, `go_live_at`, `expire_at`, `owner`, tree fields.

Hierarchy/URLs: URL = tree path of slugs (`/company/about-us/` = page
`about-us` under `company`). No arbitrary path override (Q2). Reserved
paths validated at create/move/slug-change in the service layer.

Delete semantics (Q3): **archive** (`archived_at`) is the everyday
retire action — archived pages never appear in public APIs or sitemap.
**Delete** is a Wagtail delete (cascades the subtree) behind
`delete_cmspage`, guarded by a service pre-check that raises
`ValidationError` listing referencing navigation items.
This deviates from the repo's soft-delete preference; rationale: soft
deleting tree nodes corrupts `url_path`/sibling-slug uniqueness.

### 5.2 `CmsSection` (snippet — global section instance)

| Field | Type | Notes |
|---|---|---|
| `name` | CharField(255) | admin label |
| `section_type` | CharField(choices) | from code registry, immutable after create |
| `content` | StreamField(single section block) | validated to match `section_type` |

Mixins: `DraftStateMixin` (live / go_live_at / expire_at /
first+last_published_at), `RevisionMixin`, `PreviewableMixin`,
`LockableMixin`, plus `TimeStampedModel, UserStampedModel`.

Delete: service pre-check via `ReferenceIndex.get_grouped_references_to`
→ `ValidationError` while referenced (spec 4.2). Archive via
`archived_at`. Soft-delete fields (`SoftDeleteModel`) back permanent
delete for audit continuity (rows referenced from revisions stay).

References to pages: automatic — `CmsPageSection.global_section` rows
and StreamField FKs are tracked by `wagtailcore_referenceindex`, giving
"track all page references" and "reference-aware deletion" natively.

### 5.3 `CmsPageSection` (`Orderable` — page composition row)

| Field | Type | Notes |
|---|---|---|
| `page` | ParentalKey → `CmsPage`, related_name=`sections` | |
| `global_section` | FK → `CmsSection`, null, `PROTECT` | reference |
| `content` | StreamField, blank | page-specific content |
| `is_visible` | BooleanField(default=True) | show/hide |

`CheckConstraint`: exactly one of (`global_section`, `content`) set.
`PROTECT` is the DB-level backstop for "prevent deletion of referenced
global sections"; the service layer raises a friendly `ValidationError`
first. Composition order = `Orderable.sort_order`; reorder is a service
operation rewriting `sort_order`. Draft semantics: rows are serialized
into the page's revision payload (see §7.3), so a page publish publishes
its composition, and page-specific edits never touch global sections.

### 5.4 Section types (code registry, `cms_api/sections/`)

One `StructBlock` per type; registry is Python code, changed only by
developers (spec 4.1). Initial set: HeroBanner, RichText, Heading,
Paragraph, ImageWithText, ImageGallery, Video, ProductCollection,
ProductSlider, CategoryCollection, BrandCollection, Testimonials, FAQ,
Statistics, CallToAction, PromotionalBanner, Features,
ContactInformation, Embed.

Rules:

- Rich text uses Wagtail `RichTextBlock` with a fixed feature whitelist:
  `h2 h3 h4 bold italic ol ul link blockquote table image` — exactly the
  spec's set. Arbitrary HTML is structurally impossible: rendered HTML is
  produced by Wagtail from whitelisted features only.
- E-commerce blocks hold FKs (Wagtail chooser blocks) to
  `product_api.Product`, `category_api.Category`,
  `product_api.Brand`-equivalent (exact brand model confirmed in Phase 0;
  the repo's brand source of truth is `product_api`/`origin_api`).
- Collection blocks (`ProductCollection`, `ProductSlider`, …) carry
  `mode` (MANUAL / LATEST / BEST_SELLERS / FEATURED / BY_CATEGORY /
  BY_BRAND — Q4), explicit entity lists (ordered), and `limit`.
  Resolution happens at read time through `product_api` querysets.
- `GET /api/v1/cms/section-types/` returns each type's JSON schema
  (name, label, block fields) so Nuxt Admin renders forms without
  hardcoding the registry.

### 5.5 Navigation

`CmsNavigationMenu` (`TimeStampedModel, UserStampedModel,
SoftDeleteModel`): `name`, `key` (unique; HEADER, FOOTER, custom),
`is_active`. Custom permission `manage_cms_navigation` on this model.

`CmsNavigationItem` (`TimeStampedModel` + `sort_order`): `menu` FK
(related_name=`items`), `parent` FK self (null = top level, nesting),
`label`, `link_type` (PAGE / EXTERNAL), `page` FK → `CmsPage`
(null, `PROTECT`), `external_url` URLField (http/https scheme
validation), `is_visible`, `open_in_new_tab`.
`CheckConstraint`: exactly one link target. Ordering: `sort_order`
within (menu, parent). Nav is independent of the page tree (spec 9).

### 5.6 `CmsMediaConfig` (singleton)

Max upload sizes, allowed document extensions (PDF per spec), allowed
image types. Anchors the custom permission `manage_cms_media` (the
acted-on models `wagtailimages.Image`/`wagtaildocs.Document` cannot
declare `Meta.permissions`, so the codename lives on this model and a
small dedicated permission class checks
`user.has_perm("cms_api.manage_cms_media")`).

### 5.7 Preview tokens — no table

`TimestampSigner` payload `{kind, object_id, revision_id}`. Issue via
authenticated management endpoint; verify + expire on the public
preview endpoint. TTL default 30 minutes (Q7).

## 6. API surface

All under `/api/v1/cms/`. Public endpoints return **published** content
only. Management endpoints require authentication + the permissions in
§8. Serializers split list/detail/write; `@extend_schema(tags=["CMS …"])`.

### Public (storefront)

| Endpoint | Purpose |
|---|---|
| `GET /pages/?path=/about-us/` | published page + resolved composition (global sections → published version; entity refs as IDs) |
| `GET /pages/` | published page list (lightweight, for sitemap/nav) |
| `GET /navigation/{key}/` | menu tree (cached) |
| `GET /redirects/resolve/?path=…` | old path → current canonical path (Nuxt redirect middleware) |
| `GET /sitemap/` | published, non-noindex, non-archived URLs + lastmod |
| `GET /preview/{token}/` | signed draft preview (AD-15) |

### Management (JWT + RBAC)

| Endpoint | Purpose |
|---|---|
| `POST/GET/PATCH/DELETE /pages/` | CRUD; create accepts `template_key`; nested `sections` writes via `drf-writable-nested` |
| `POST /pages/{id}/publish/` `…/unpublish/` `…/archive/` `…/restore/` | lifecycle (each behind its own custom permission) |
| `PUT /pages/{id}/sections/reorder/` | composition ordering |
| `GET /pages/{id}/revisions/` `POST /pages/{id}/rollback/` | revision history + rollback |
| `POST /pages/{id}/preview-token/` | issue preview token |
| `POST/GET/PATCH/DELETE /sections/` | global sections CRUD |
| `POST /sections/{id}/publish/` `…/unpublish/` `…/archive/` | section lifecycle |
| `GET /sections/{id}/references/` | pages referencing this section |
| `GET /sections/{id}/revisions/` `POST /sections/{id}/rollback/` | section revisions |
| `GET /section-types/` | code registry schema (read-only) |
| `GET/POST/PATCH/DELETE /navigation/` (+ items) | menu management |
| `GET/POST/PATCH/DELETE /media/` | Wagtail images/documents: upload, metadata, alt text, delete-with-reference-check |
| `GET /redirects/` | redirect list/history |
| `GET /audit-logs/` | CMS activity (actor, action, object, timestamp) |

Errors: standard DRF `ValidationError` (400) for rule violations,
404 for unpublished content on public endpoints (no draft leakage),
409-style `ValidationError` for revision conflicts (§11).

## 7. Content lifecycle

### 7.1 Page

`create (draft) → edit/save (draft revisions) → publish → [scheduled
unpublish via expire_at] → archive | delete`. Publishing is always an
explicit action (`publish_cms_page`); create never implies publish
(same rule as blog). `status`/publish fields are not writable through
CRUD serializers.

### 7.2 Global section

Same lifecycle with its own revision stream. **Publishing a section
updates all referencing pages** because page payloads resolve the
section's live version at read time (AD-7) — no per-page rewrite.
Cache invalidation fans out to referencing pages (§10).

### 7.3 Revisions & concurrency

- Wagtail `Revision` rows for both pages and sections; rollback =
  `revision.as_object()` + `save_revision` + explicit publish.
- Page composition rows are serialized into the page revision content
  (custom serializable payload), so a rollback restores composition too.
- Concurrent edits: `LockableMixin` + optimistic check — management
  writes must carry the `base_revision_id` they edited; a mismatch
  returns a conflict error (never a silent last-write-wins).

## 8. Permission matrix

Codenames follow existing RBAC conventions (Django model permissions,
custom codenames in `Meta.permissions`); spec capability names map as:

| Spec capability | Codename | Declared on | Action(s) |
|---|---|---|---|
| `cms.page.view` | `view_cmspage` | `CmsPage` | list/retrieve |
| `cms.page.create` | `add_cmspage` | `CmsPage` | create |
| `cms.page.edit` | `change_cmspage` | `CmsPage` | update |
| `cms.page.delete` | `delete_cmspage` | `CmsPage` | delete (guarded) |
| `cms.page.publish` | `publish_cms_page` | `CmsPage` | publish/rollback |
| (spec: archive) | `archive_cms_page` | `CmsPage` | archive/restore |
| (publishing needs it) | `unpublish_cms_page` | `CmsPage` | unpublish |
| `cms.section.view` | `view_cmssection` | `CmsSection` | list/retrieve |
| `cms.section.create` | `add_cmssection` | `CmsSection` | create |
| `cms.section.edit` | `change_cmssection` | `CmsSection` | update |
| `cms.section.archive` | `archive_cms_section` | `CmsSection` | archive |
| `cms.section.delete` | `delete_cmssection` | `CmsSection` | delete (guarded) |
| (publishing needs it) | `publish_cms_section` / `unpublish_cms_section` | `CmsSection` | publish/unpublish |
| `cms.navigation.manage` | `manage_cms_navigation` | `CmsNavigationMenu` | all nav ops |
| `cms.media.manage` | `manage_cms_media` | `CmsMediaConfig` | all media ops |

Standard actions map through `ModelPermissionAccess.perms_map`; custom
actions through `custom_permissions` mappings /
`CustomPermissionAccessMixin`, mirroring `blog_api`. Enforcement is
server-side on every management endpoint. Public endpoints are
`AllowAny` but expose only published content.

## 9. URLs, SEO, redirects, sitemap

- **Uniqueness**: Wagtail's unique `url_path` per page guarantees no
  duplicate page URLs.
- **Reserved paths**: service-level validation against
  `CMS_RESERVED_PATHS` (default: `/api/`, `/admin/`, `/cms-admin/`,
  `/docs/`, `/redoc/`, `/schema/`, `/media/`, `/static/`, `/accounts/`,
  plus the Nuxt reserved routes — Q2). Checked on create, move and
  slug change, for the full public path.
- **Slug changes**: on publish, if the published path changed, the
  service creates/updates a `wagtailcontrib_redirects` redirect
  (old → new). **Chains collapse**: a redirect whose target later moves
  is updated to the final target (A→C when B→C is created). **Loops are
  rejected**: a redirect whose target resolves back to its source is a
  `ValidationError`. **History**: every old published path keeps
  redirecting to the current canonical path, and each redirect change
  is a Wagtail log entry (AD-8).
- **SEO**: fields on `CmsPage` (§5.1) — rendered by Nuxt; `canonical_url`,
  robots directives included in the page payload.
- **Sitemap**: `GET /sitemap/` returns live, non-archived,
  `seo_noindex=False` pages with `last_modified`/`last_published_at`.
  The Nuxt sitemap integration consumes this endpoint only.

## 10. Caching

- New `CACHES` setting (AD-12): Redis per deployment
  (`CMS_CACHE_URL_SETTINGS`), LocMem in dev/tests (test settings keep
  the cache off or LocMem to avoid cross-test state).
- Cached payloads: public page payloads (key by page id + revision id),
  navigation trees, sitemap, section-type schema.
- Invalidation, on `transaction.on_commit` of the publishing service
  and via Wagtail signals (`page_published`, `page_unpublished`,
  `snippet_published`): drop the object's keys, the referencing pages'
  keys (`ReferenceIndex` reverse lookups) for global sections, the
  navigation keys on nav changes, sitemap keys on any publish.
- Cache safety net TTLs (e.g. 5 min) exist only for missed events; the
  defined consistency window after a successful publish is **zero**.

## 11. Audit & security

- **Audit** (AD-10): services call `wagtail.log_actions.log_action` for
  create/edit/publish/unpublish/archive/delete/rollback, nav and media
  changes. One trail regardless of interface; exposed read-only via
  `GET /audit-logs/`.
- **Draft safety**: public serializers read published/live state only;
  unpublished → 404 on public endpoints; preview only via signed token
  (AD-15) with expiry.
- **Injection**: rich text limited to the feature whitelist (§5.4);
  external URLs validated (scheme http/https, length); file uploads
  validated by type/size from `CmsMediaConfig`.
- **Reference integrity**: `PROTECT` FKs + service pre-checks + Wagtail
  `ReferenceIndex` — no broken references after delete/move/reorder.
- **Concurrent edits**: §7.3.

## 12. Background processing

- Celery Beat task `cms-publish-scheduled` (cadence: every 5 minutes,
  joins `CELERY_BEAT_SCHEDULE`) driving Wagtail's scheduled
  publish/expire sweeps for pages and snippets
  (`go_live_at` / `expire_at`). **Phase 0 verification**: the exact
  Wagtail entry point for the sweep on the pinned Wagtail version.
- No queues or workers beyond the existing infrastructure.

## 13. Phase 0 verification items

1. Pin the Wagtail release compatible with Django 5.2.x and add to
   `requirements.txt` (`wagtail`, `modelcluster`, `taggit` pinned).
   Version search was unavailable when this document was written.
2. Confirm the scheduled publish/expire sweep entry point for that
   Wagtail version and wire it to the Beat task.
3. Confirm the model that owns "brands" for the BrandCollection block
   (`product_api` vs `origin_api`).
4. `wagtail.sites` needs a `Site` row (hostname = frontend domain) per
   deployment — set via admin/management command, documented in
   `docs/deployment.md` (never env values in data migrations).
5. Run the full existing test suite after the Wagtail install to prove
   zero impact on e-commerce functionality (acceptance criterion).

## 14. Implementation phases

Each phase ends with `flake8`, tests for the new surface, and docs
updates.

| Phase | Scope |
|---|---|
| 0 | Foundation: Wagtail install + settings + URL mounts + empty `cms_api` + verification items (§13) |
| 1 | Section-type registry + `CmsSection` snippet: CRUD, publish/unpublish, revisions/rollback, archive, reference guard, section-type schema API |
| 2 | `CmsPage` + `CmsPageSection`: CRUD from templates, composition writes/reorder, revisions/rollback, publish/unpublish/archive, reserved-path validation |
| 3 | Lifecycle: scheduled publish/unpublish (Beat), redirects service, preview tokens, sitemap endpoint |
| 4 | Navigation + media management + audit-log API |
| 5 | Cache layer + invalidation, Wagtail Admin at `/cms-admin/`, full test pass, docs |

## 15. Testing approach

API tests through `/api/v1/cms/` per repo convention: draft isolation
(public endpoints 404 unpublished), publish visibility, section fan-out,
redirect creation/collapse/loop rejection, reference guard on delete,
permission enforcement per matrix row, preview token expiry, sitemap
filtering. Wagtail model tests only where services own logic.

## 16. Open questions

1. **Wagtail version pin** — confirm the target Wagtail release for
   Django 5.2.x (or approve "latest compatible" for Phase 0 to pin).
2. **URL derivation & reserved routes** — confirm URLs are derived from
   tree position + slugs only (no arbitrary path overrides), and supply
   the Nuxt reserved-route list (or approve the `CMS_RESERVED_PATHS`
   default in §9 as the starting set).
3. **Page delete semantics** — approve hard delete (Wagtail subtree
   cascade) with archive as the retire path (deviation from the repo's
   soft-delete preference, rationale in §5.1)?
4. **Dynamic product sections** — define "best sellers" (e.g. by
   quantity sold within a rolling window from `sale_api`?) and confirm
   "latest" = `created_at` desc and "featured" = product flag. Which
   flag/field is authoritative for "featured"?
5. **Wagtail Admin access** — Wagtail Admin requires `is_staff` (session
   auth); existing RBAC is `role` + model perms. Approve: Wagtail Admin
   access = `is_staff AND (view_cmspage OR change_cmspage)`? And confirm
   Wagtail Admin ships in the initial release (Phase 5) rather than
   engine-only.
6. **Redirect history** — confirm the §9 interpretation: all historical
   paths redirect to the current canonical path (chains collapsed),
   full change history in the audit log — as opposed to keeping
   transitive redirect chains.
7. **Preview tokens** — TTL (proposal: 30 min) and issuing permission
   (proposal: `change_cmspage` / `change_cmssection` respectively).

## 17. Out of scope (per spec §15)

Multi-tenant CMS, cross-store sharing, separate CMS services,
admin-defined section types, visual CSS customization, drag-and-drop
design, replacing product management or auth/RBAC. Also out of scope
for this design: adding CMS content to `content_security_api`'s scan
sources (a follow-up, noted for the decisions log when taken).

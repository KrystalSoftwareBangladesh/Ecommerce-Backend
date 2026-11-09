# CMS — Technical Architecture & Data Model Design

**Version:** 1.1 (approved)
**Status:** Approved 2026-11-06 — the 7 design decisions are recorded
in [§16](#16-approved-decisions-2026-11-06); implementation proceeds
phase by phase.
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
| AD-1 | Wagtail is embedded in this project (new third-party apps + `cms_api`); there is no separate CMS service, frontend or database. Approved stack: **Wagtail 7.4 LTS with Django 5.2.x** (exact patch pinned in Phase 0). |
| AD-2 | Pages are **never served by Django**. The Wagtail page `serve()` view is unused; Nuxt renders pages from the public API. `wagtail.urls` (page serving) is not mounted. |
| AD-3 | One concrete page model, `CmsPage`, with a `template_key`. Templates only seed an initial composition at creation; they never constrain later editing. |
| AD-4 | Global sections are Wagtail **snippets** (`CmsSection`) with `DraftStateMixin`, `RevisionMixin`, `PreviewableMixin`, `LockableMixin` — independent draft/publish/revisions. |
| AD-5 | Section *types* are code-defined StreamField blocks (`cms_api/sections/`). Administrators cannot create new types. A read-only schema API lets Nuxt Admin render editing forms. |
| AD-6 | Page composition = ordered `CmsPageSection` rows (Wagtail `Orderable`, `ParentalKey` to the page), each row being **either** a reference to a global `CmsSection` **or** inline page-specific content. Removing a row never deletes the referenced section. Page-specific content is revisioned with its page. |
| AD-7 | Publishing = Wagtail revision publish. Saving a draft never touches published content; public APIs read only `live` state. A global section's published content is resolved live, so publishing it updates every referencing page at once. |
| AD-8 | Redirects use `wagtail.contrib.redirects`. Slug-change redirects are created by our publish service (the API path, not only the Wagtail admin prompt). All historical paths are collapsed **directly to the latest canonical target** (no transitive chains); loops are rejected; the full change history stays in the audit log. |
| AD-9 | Media for CMS content uses **Wagtail images/documents** (same `MEDIA_ROOT` storage as today — no new storage infrastructure). Existing plain-`ImageField` media (`ProductImage`, blog featured images) stays untouched. |
| AD-10 | Audit logging uses Wagtail's `log_action` / `LogEntry`, so Wagtail Admin actions and API actions land in one trail. |
| AD-11 | CMS permissions are Django model permissions on `cms_api` models (custom `Meta.permissions` codenames), enforced server-side by the existing permission classes. **Wagtail Admin ships in the initial release**: access requires `is_staff` **and** the relevant CMS model permissions, integrated with the existing RBAC (no separate Wagtail-only permission system). |
| AD-12 | Caching: introduce `CACHES` (Redis in deployments, LocMem in dev) with **event-driven invalidation** on publish/unpublish/delete via `transaction.on_commit`. The consistency window after a successful publish is zero by design (keys are dropped in the same commit cycle); TTLs are a safety net only. |
| AD-13 | Scheduling reuses Wagtail's `go_live_at` / `expire_at` machinery, swept by a task on the **existing Celery Beat** (exact entry point verified in Phase 0). |
| AD-14 | E-commerce entities are **referenced, never copied**. Section content holds entity IDs; dynamic collections resolve to ordered product-ID lists at read time through existing `product_api` querysets. Pricing/product payloads come from existing product APIs — the CMS API returns references, not product data. |
| AD-15 | Preview uses **signed preview tokens** (Django `TimestampSigner`, TTL 30 minutes) that are read-only, scoped to one object and content revision, and bound to the authorized user who requested them. Draft content is reachable only through a token, never through plain public endpoints, and is never cached. |
| AD-16 | Retention policy: **archive/unpublish is the default** retirement path for pages and sections. Permanent deletion requires elevated permissions and dependency checks (navigation, references, subtree) and preserves Wagtail tree integrity. |
| AD-17 | Dynamic product collections resolve at read time: LATEST = product `created_at` DESC; BEST_SELLERS = **net quantity sold over a rolling 30-day window**; FEATURED = the existing product-domain featured flag; MANUAL = explicit product IDs with manual ordering. The authoritative fields are confirmed by a Phase 0 audit of the existing product/sale models. |

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
`about-us` under `company`). No arbitrary path overrides (approved).
Reserved paths validated at create/move/slug-change in the service
layer.

Delete semantics (approved): **archive** (`archived_at`) or unpublish is
the default retirement path — archived pages never appear in public
APIs or sitemap. **Permanent deletion** requires elevated permissions
(`delete_cmspage`, held by a minimal set of roles) and passes
dependency checks first — referencing navigation items, any other
references (Wagtail `ReferenceIndex`) and the full subtree must be
acknowledged; the service raises `ValidationError` listing every
dependency otherwise. Deletion runs through Wagtail's own delete so
tree integrity (`url_path`, `numchild`, sibling-slug uniqueness) is
preserved. Soft delete is not used for pages: soft deleting tree nodes
would corrupt `url_path`/sibling-slug uniqueness.

### 5.2 `CmsSection` (snippet — global section instance)

| Field | Type | Notes |
|---|---|---|
| `name` | CharField(255) | admin label |
| `section_type` | CharField(choices) | from code registry, immutable after create |
| `content` | StreamField(single section block) | validated to match `section_type` |

Mixins: `DraftStateMixin` (live / go_live_at / expire_at /
first+last_published_at), `RevisionMixin`, `PreviewableMixin`,
`LockableMixin`, plus `TimeStampedModel, UserStampedModel`.

Delete: **archive/unpublish is the default** (approved). Permanent
deletion requires elevated permissions (`delete_cmssection`) and passes
dependency checks: service pre-check via
`ReferenceIndex.get_grouped_references_to` → `ValidationError` while
referenced (spec 4.2). Archive via `archived_at`. Soft-delete fields
(`SoftDeleteModel`) back permanent delete for audit continuity (rows
referenced from revisions stay).

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
  `mode`, explicit entity lists (ordered), and `limit`. Resolution
  happens at read time through `product_api` querysets. Approved
  definitions (AD-17):
  - **LATEST** — products by `created_at` DESC.
  - **BEST_SELLERS** — net quantity sold (sales minus returns) over a
    rolling 30-day window, ranked DESC.
  - **FEATURED** — the existing product-domain featured flag
    (authoritative field confirmed in the Phase 0 audit).
  - **MANUAL** — selected product IDs with manual ordering.
  - **BY_CATEGORY / BY_BRAND** — products of the selected
    categories/brands (spec 8), ordered per block configuration.
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

`TimestampSigner` payload `{user_id, kind, object_id, revision_id}`.
Issued only to authenticated users holding the matching edit permission
(`change_cmspage` / `change_cmssection`); the token is **read-only** and
bound to that user and the specific content revision. Verification
checks the signature, the user binding (and that the user still holds
the edit permission), the revision and expiry — TTL 30 minutes.
Preview responses send `Cache-Control: no-store`; draft payloads are
never written to any cache.

## 6. API surface

All under `/api/v1/cms/`. Public endpoints return **published** content
only. Management endpoints require authentication + the permissions in
§8. Serializers split list/detail/write; `@extend_schema(tags=["CMS …"])`.

### Public (storefront)

Purely public, management-free resources are mounted under
`cms/public/...` (implementation detail, Phase 2's own local pattern
for `/pages/`, extended in Phase 3 to `/sitemap/` and `/preview/`).
`/redirects/resolve/` stays under the plain `/redirects/` prefix
instead, since it shares that base path with the authenticated
`/redirects/` history list — one resource, per-action permissions,
the same pattern `/pages/{id}/publish/` already uses next to page CRUD.

| Endpoint | Purpose |
|---|---|
| `GET /public/pages/?path=/about-us/` | published page + resolved composition (global sections → published version; entity refs as IDs) |
| `GET /public/pages/` | published page list (lightweight, for sitemap/nav) |
| `GET /navigation/{key}/` | menu tree (cached) — Phase 4 |
| `GET /redirects/resolve/?path=…` | old path → current canonical path (Nuxt redirect middleware) |
| `GET /public/sitemap/` | published, non-noindex, non-archived URLs + lastmod |
| `GET /public/preview/{token}/` | signed draft preview (AD-15) |

### Management (JWT + RBAC)

| Endpoint | Purpose |
|---|---|
| `POST/GET/PATCH/DELETE /pages/` | CRUD; create accepts `template_key`; nested `sections` writes via `drf-writable-nested` |
| `POST /pages/{id}/publish/` `…/unpublish/` `…/archive/` `…/restore/` | lifecycle (each behind its own custom permission); `publish` optionally takes `go_live_at`/`expire_at` to schedule instead of `revision_id` |
| `PUT /pages/{id}/sections/reorder/` | composition ordering |
| `GET /pages/{id}/revisions/` `POST /pages/{id}/rollback/` | revision history + rollback |
| `POST /pages/{id}/preview-token/` | issue preview token |
| `POST/GET/PATCH/DELETE /sections/` | global sections CRUD |
| `POST /sections/{id}/publish/` `…/unpublish/` `…/archive/` | section lifecycle; `publish` optionally takes `go_live_at`/`expire_at` |
| `GET /sections/{id}/references/` | pages referencing this section |
| `GET /sections/{id}/revisions/` `POST /sections/{id}/rollback/` | section revisions |
| `POST /sections/{id}/preview-token/` | issue preview token (Phase 3, extended to sections per §16 item 9) |
| `GET /section-types/` | code registry schema (read-only) |
| `GET/POST/PATCH/DELETE /navigation/` (+ items) | menu management — Phase 4 |
| `GET/POST/PATCH/DELETE /media/` | Wagtail images/documents: upload, metadata, alt text, delete-with-reference-check — Phase 4 |
| `GET /redirects/` | redirect list/history, gated on `view_cmspage` per §16 item 8 |
| `GET /audit-logs/` | CMS activity (actor, action, object, timestamp) — Phase 4 |

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
| `cms.page.delete` | `delete_cmspage` | `CmsPage` | permanent delete (elevated + dependency-guarded) |
| `cms.page.publish` | `publish_cms_page` | `CmsPage` | publish/rollback |
| (spec: archive) | `archive_cms_page` | `CmsPage` | archive/restore |
| (publishing needs it) | `unpublish_cms_page` | `CmsPage` | unpublish |
| `cms.section.view` | `view_cmssection` | `CmsSection` | list/retrieve |
| `cms.section.create` | `add_cmssection` | `CmsSection` | create |
| `cms.section.edit` | `change_cmssection` | `CmsSection` | update |
| `cms.section.archive` | `archive_cms_section` | `CmsSection` | archive |
| `cms.section.delete` | `delete_cmssection` | `CmsSection` | permanent delete (elevated + dependency-guarded) |
| (publishing needs it) | `publish_cms_section` / `unpublish_cms_section` | `CmsSection` | publish/unpublish |
| `cms.navigation.manage` | `manage_cms_navigation` | `CmsNavigationMenu` | all nav ops |
| `cms.media.manage` | `manage_cms_media` | `CmsMediaConfig` | all media ops |

Standard actions map through `ModelPermissionAccess.perms_map`; custom
actions through `custom_permissions` mappings /
`CustomPermissionAccessMixin`, mirroring `blog_api`. Enforcement is
server-side on every management endpoint. Public endpoints are
`AllowAny` but expose only published content.

Wagtail Admin (initial release, approved): access requires `is_staff`
**and** the relevant CMS model permissions above, integrated with the
existing RBAC — Wagtail's own permission panels are not a second
permission system for CMS content.

## 9. URLs, SEO, redirects, sitemap

- **Uniqueness**: Wagtail's unique `url_path` per page guarantees no
  duplicate page URLs.
- **Reserved paths**: service-level validation against
  `CMS_RESERVED_PATHS` (default: `/api/`, `/admin/`, `/cms-admin/`,
  `/docs/`, `/redoc/`, `/schema/`, `/media/`, `/static/`, `/accounts/`,
  plus the Nuxt reserved routes). The existing Nuxt routes are audited
  for conflicts in Phase 0 and folded into the setting (approved).
  Checked on create, move, slug change and rollback (the URL the
  restored revision would generate), for the full public path.
- **Slug changes**: on publish, if the published path changed, the
  service creates/updates a `wagtailcontrib_redirects` redirect
  (old → new). **Direct collapse**: every historical path redirects
  directly to the latest canonical target (A→C when B→C is created) —
  no transitive chains. **Loops are rejected**: a redirect whose target
  resolves back to its source is a `ValidationError`. **History**: the
  full change history stays in the audit log (AD-8).
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
- **Drafts and previews are never cached** (approved): preview responses
  send `Cache-Control: no-store`, and no draft payload is ever written
  to the cache.

## 11. Audit & security

- **Audit** (AD-10): services call `wagtail.log_actions.log_action` for
  create/edit/publish/unpublish/archive/delete/rollback, nav and media
  changes. One trail regardless of interface; exposed read-only via
  `GET /audit-logs/`.
- **Draft safety**: public serializers read published/live state only;
  unpublished → 404 on public endpoints; preview only via signed,
  user-bound, revision-scoped **read-only** tokens (AD-15, 30-minute
  expiry, re-checked permissions) that are never cached.
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

1. Pin **Wagtail 7.4 LTS** with Django 5.2.x: the exact compatible patch
   release goes into `requirements.txt` (`wagtail`, `modelcluster`,
   `taggit` pinned) — approved decision 1.
2. Confirm the scheduled publish/expire sweep entry point for that
   Wagtail version and wire it to the Beat task.
3. Confirm the model that owns "brands" for the BrandCollection block
   (`product_api` vs `origin_api`).
4. **Audit the existing Nuxt routes** for conflicts and fold them into
   `CMS_RESERVED_PATHS` (approved decision 2).
5. **Audit the existing product/sale models** (approved decision 4):
   the authoritative "featured" flag/field and the net-quantity source
   for best sellers (sales minus returns over 30 days, `sale_api`).
6. `wagtail.sites` needs a `Site` row (hostname = frontend domain) per
   deployment — set via admin/management command, documented in
   `docs/deployment.md` (never env values in data migrations).
7. Run the full existing test suite after the Wagtail install to prove
   zero impact on e-commerce functionality (acceptance criterion).

### Phase 0 verification results (2026-11-06)

1. **Done** — `requirements.txt` pins `wagtail==7.4.4`,
   `django-modelcluster==6.5`, `django-taggit==6.1.0`. Wagtail 7.4
   requires Django >= 5.2; the repo's 5.2.x pin is compatible
   (`pip check` clean).
2. **Confirmed** — the sweep entry point is Wagtail's
   `publish_scheduled` management command (covers `go_live_at`
   revisions and `expire_at` for `Page` and every `DraftStateMixin`
   model, so section models and scheduled specs are swept too). The
   `cms-publish-scheduled` Beat task calling it is created in Phase 3.
3. **Confirmed** — brands are owned by `product_api.Brand`
   (`slug`, `logo`, `display_order`, soft delete); `origin_api.Origin`
   is product country-of-origin, a different concept.
4. **Done** — `CMS_RESERVED_PATHS` in `settings.py` holds the API/
   Django/Wagtail mounts plus every static top-level route of the
   three storefront frontends (Nuxt: bikkhato, BestComputerHub;
   Vue/Vite: ZayrahLife), audited 2026-11-06. Notably
   BestComputerHub already serves arbitrary top-level slugs via
   `pages/[slug].vue` — the catch-all CMS pages will populate.
5. **Partially confirmed — gap found.** Best-seller net quantity:
   `sale_api.SaleItem.quantity` joined to `Sale` over a 30-day
   window, excluding `RETURNED`/`CANCELLED` (returns exist only as
   whole-order `SaleStatus.RETURNED` and inventory
   `ReferenceType.RETURN` movements). **No "featured" flag exists on
   the product domain** — `Product` has no featured field today, so
   the FEATURED collection mode (AD-17) needs a new product-domain
   flag; deferred to Phase 2 with a design decision.
6. **Done** — `manage.py setup_cms_site` (idempotent, points the
   default `wagtail.sites.Site` at the `FRONTEND_BASE_URL` hostname,
   `--hostname` override) documented in `docs/deployment.md`.
7. **Done** — full suite after install: 799 tests, 30 failures +
   5 errors + 8 skipped, identical to the clean-HEAD baseline (all
   pre-existing; no regression from the Wagtail install).

## Phase 1 verification results (2026-11-07)

Scope delivered: §14 row 1 — section-type registry, `CmsSection`
snippet with CRUD, publish/unpublish, revisions/rollback, archive,
delete reference guard, and the section-type schema API.

1. **Wagtail snippet + `ReferenceIndex`** — `CmsSection` is a
   `DraftStateMixin`/`RevisionMixin` snippet; the delete guard uses
   `ReferenceIndex.get_grouped_references_to()`. Verified against
   Wagtail 7.4.4 in the venv.
2. **One-block content rule** — enforced in `SectionContentField`
   (`to_python` → `stream_block.clean`) and cross-checked against
   `section_type` in the write serializers; the model `clean()` is the
   second line of defence.
3. **Publish/unpublish/rollback** — Wagtail's internal permission checks
   target the auto-generated `publish_cmssection` codenames, not the
   spec permissions, so services call the Wagtail actions with
   `skip_permission_checks=True`; enforcement is DRF-side
   (`ModelPermissionAccess` + custom permissions). Rollback = restore +
   publish as a new revision (interpretation R1).
4. **Archive** — archive-only per spec; no unarchive in Phase 1. The
   log action `cms_api.archive` is registered via
   `register_log_actions` (Wagtail core has no archive action).
5. **Schema API** — `GET /api/v1/cms/section-types/` is authenticated
   (`IsAuthenticated`) and derived from the code-owned registry
   (per-type-name schemas, approved in review).
6. **Tests + regression** — 35 new API tests (CRUD/validation,
   lifecycle, section types) all pass; the full suite runs 834 tests
   with 30 failures + 5 errors + 8 skipped, identical counts to the
   Phase 0 baseline — no regressions.

**Spec gaps inherited from Phase 1 scope:** no unarchive, `sort_order`
exists on the model but is not exposed by the API, no public storefront
endpoints (Phase 3), and the featured-flag gap on product collections
(open since Phase 0, §13.5 item 5).

## Phase 2 verification results (2026-11-08)

Scope delivered: §14 row 2 — `CmsPage` + `CmsPageSection`: CRUD from
templates, composition writes/reorder/duplicate, revisions/rollback,
publish/unpublish/archive/restore, dependency-guarded delete,
reserved-path validation, and the public page read endpoints with
draft isolation.

1. **Templates** — code-owned `PAGE_TEMPLATES` registry in
   `cms_api/pages/templates.py`; `template_key` seeds the initial
   composition at creation only and `template_key` + explicit
   `sections` together is rejected (400). Resolves the open design
   question: templates are registry entries in code, like section
   types, not DB records.
2. **Reserved paths** — `CMS_RESERVED_PATHS` in settings is the
   storefront route list; every path segment is rejected for CMS page
   slugs on create and update (verified with `/api/`, `/admin/`,
   `/about-us/`).
3. **Composition rows** — XOR rule (global `CmsSection` link **or**
   exactly one local registry block) enforced by model `clean()` and
   the write serializers; add/update/reorder/duplicate/delete under
   `/pages/{id}/sections/`; every write snapshots a page revision and
   is optimistic-locked via `base_revision_id` (409 on stale).
4. **modelcluster commit semantics** — services read and mutate rows
   through `page.sections.get_object_list()` (the page's tracked
   in-memory child list) so `page.save()` commits them. `.all()` on a
   relation that was never initialised returns untracked live-query
   objects whose field changes are silently dropped by
   `ClusterableModel.save()`; this was found and fixed during test
   bring-up (reorder and row-update writes).
5. **Revisions/rollback** — rollback per interpretation R1: restore an
   old revision's fields **and** composition, save as a new revision
   and publish it. Rollback requires the `publish_cms_page` permission;
   publish accepts an optional `revision_id`.
6. **Lifecycle + delete** — publish/unpublish/archive/restore behind
   `publish_cms_page`, `unpublish_cms_page`, `archive_cms_page`;
   delete is dependency-guarded (child pages listed in a 400
   `dependencies` payload) and subtree-deletes only with
   `?acknowledge=true`. Wagtail log actions `cms_api.create`,
   `cms_api.update`, `cms_api.archive` are registered via
   `register_log_actions` (core Wagtail has no such actions).
7. **Public endpoints** — `/api/v1/cms/public/pages/?path=` serves
   published pages only: unpublished/archived pages 404, draft edits
   are never served (content comes from `live_revision`), unpublished
   or archived global sections are omitted from resolved rows.
8. **Tests + lint** — 40 new Phase 2 API tests (75 total in
   `cms_api`, all passing); `flake8` clean.

**Spec gaps inherited from Phase 2 scope:** preview tokens (Phase 3),
scheduled publishing (Phase 3), `page.parent`/nesting is modelled and
tested but the public resolver serves flat paths, and the
featured-flag gap on product collections (open since Phase 0, §13.5
item 5) remains deferred.

**Phase 2 observation outcomes (2026-11-09):**

1. **Rollback reserved-path validation (RESOLVED)** — `rollback_page`
   now validates the *prospective* URL of the restored revision
   (`_prospective_url_path(parent, restored.slug)`) before applying it:
   reserved paths (`CMS_RESERVED_PATHS`) are rejected and a URL
   already held by another page is rejected (400). Previously the
   stale pre-rollback `page.url_path` was checked. Regression tests:
   `test_rollback_rejects_a_reserved_prospective_path`,
   `test_rollback_rejects_a_url_conflict`.
2. **Public path resolution (RESOLVED)** — public lookup and the
   public serializers' `path` resolve through `published_url_path()`
   (live-revision slug chain), never the draft `url_path`. A draft
   slug change no longer serves the unpublished URL (404) and the
   published URL keeps resolving until the change is published.
   Regression tests: `test_draft_slug_path_is_not_served`,
   `test_published_path_resolves_after_a_draft_slug_change`,
   `test_list_reports_published_urls_after_a_draft_slug_change`.
3. **Rollback URL recalculation (RESOLVED, 2026-11-09)** — `rollback_
   page` no longer relies solely on Wagtail's implicit slug-changed
   check to recompute `url_path` (`Page.save()` only recalculates it
   when the restored slug differs from the row currently in the
   database, so a rollback that leaves the page's own slug unchanged
   skipped recalculation even if an ancestor had since been renamed).
   It now always recomputes the restored page's `url_path` from a
   freshly-fetched current parent (`page.get_parent(update=True)`,
   since `get_parent()` caches its result on the instance) via
   `page.set_url_path(parent)`, and explicitly repaths descendants
   (`Page._update_descendant_url_paths`, Wagtail 7.4.4) whenever the
   recomputed path differs from the database's current `url_path` —
   read from the database rather than from the possibly-stale
   in-memory `page.url_path` on the caller's instance. Reserved-path
   and URL-conflict validation (outcome 1 above) and the restore +
   publish semantics are unchanged. Regression tests:
   `test_rollback_repaths_a_page_after_an_ancestor_rename`,
   `test_rollback_repaths_descendants_with_a_stale_cached_parent`.

## Phase 3 verification results (2026-11-09)

Scope delivered: §14 row 3 — scheduled publish/unpublish (Beat),
redirects service, preview tokens, sitemap endpoint.

1. **Scheduling** — `go_live_at`/`expire_at` are accepted only on
   `POST .../publish/` for pages and sections, never on create/update
   (an editor with only `change_cmspage`/`change_cmssection` must not
   be able to schedule an unpublish, which only
   `unpublish_cms_page`/`unpublish_cms_section` should allow; the
   sweep reads `expire_at` straight off the live row). Setting either
   writes the field and snapshots a new revision before publishing it
   through `PublishRevisionAction`/`PublishPageRevisionAction`, which
   already schedules rather than publishes when `go_live_at` is in
   the future (Wagtail-native; no new mechanism). They cannot be
   combined with `revision_id`. A revision whose embedded `expire_at`
   has since fallen into the past (e.g. after one auto-expiry) is
   re-snapshotted with it cleared before a plain republish, or the
   next sweep would expire the object again immediately.
2. **The sweep** is a new Beat task, `cms-publish-scheduled`
   (`cms_api.tasks.run_scheduled_publishing_task`, every 5 minutes),
   wrapping Wagtail's own `publish_scheduled` management command
   (confirmed entry point, Phase 0 §13.2) — no sweep logic is
   reimplemented. The wrapper only adds the one thing that command has
   no hook for: it snapshots the published path of every `CmsPage`
   with a due revision before the command runs, then diffs after, to
   create the same slug-change redirect an explicit API publish would.
3. **Finding: the page-publish path never fired Wagtail's `Page`
   signals (fixed).** `publish_page`/`unpublish_page` called the
   generic `PublishRevisionAction`/`UnpublishAction` directly instead
   of `Page`'s own `publish()`/`unpublish()` (which use
   `PublishPageRevisionAction`/`UnpublishPageAction`). The generic
   actions only send the generic `published`/`unpublished` signals,
   not `page_published`/`page_unpublished` — the scheduled sweep (via
   Wagtail's own `obj.unpublish()`/`revision.publish()`) already sent
   both. Redirect creation needs to run identically regardless of
   which path made a page live, so the services now use the
   Page-specific actions (`skip_permission_checks=True` unchanged).
   This also means Phase 5's planned cache invalidation, which the
   design already assumes reacts to `page_published`/
   `page_unpublished` (§10), will see them fire from every path once
   it is built — previously it would have silently missed API-driven
   publishes.
4. **Redirects** — `services/redirects.py`. A redirect's target is
   always the page itself (`redirect_page`, `site=None`), resolved at
   lookup time through `published_url_path` — not Wagtail's
   `Redirect.link`/`page.url`, which resolve through `Site.root_page`
   and return `None` for every `CmsPage` in this project (verified:
   the default site's `root_page` is Wagtail's seeded placeholder
   page, a sibling of the CMS tree root, not an ancestor of it; this
   is a pre-existing Wagtail-admin-only gap, reported, not fixed,
   since nothing in the headless API path depends on it). Resolving
   through the page itself rather than another redirect's `old_path`
   gives direct collapse for free: every historical path a page has
   held resolves straight to its current canonical URL. A rename back
   to an earlier slug (A→B→A) deletes the now-stale redirect at the
   reclaimed path rather than looping. A parent rename creates one
   redirect per live descendant too.
   **Finding (fixed): Wagtail auto-creates redirects on every slug
   change, including a draft-only edit.**
   `wagtail.contrib.redirects`' own `page_slug_changed` handler
   (`WAGTAILREDIRECTS_AUTO_CREATE`, default `True`) fires on every
   `Page.save()` with a changed slug, committed via
   `transaction.on_commit` — including a draft edit through
   `update_page`, before any publish. Left on, this directly violates
   AD-8 (redirects are a publish-time concern) and would leak draft
   paths through the public resolve endpoint. Set to `False` in
   settings; `services/redirects.py` creates the equivalent redirect
   at publish time instead. Verified with
   `TestCase.captureOnCommitCallbacks` (the signal is otherwise
   invisible inside a rolled-back test transaction).
   `GET /redirects/resolve/?path=` is public (AllowAny); `GET
   /redirects/` (history) is gated on `view_cmspage` (§8 has no
   dedicated row for it — approved in review, §16 item 8 below).
   `Redirect` is not registered with `ReferenceIndex`, so an existing
   redirect does not block a page's dependency-guarded delete
   (verified; unchanged from Phase 2).
5. **Preview tokens** — `services/preview.py`, `django.core.signing.
   dumps`/`loads` (JSON-backed, no pickle), `compress=False` (a
   compressed token's leading `.` would not survive DRF's default
   `[^/.]+` URL lookup pattern). 30-minute TTL, scoped to one object
   and one revision, bound to the issuing user; verification re-checks
   the signature, the revision and that the same user still holds
   `change_cmspage`/`change_cmssection`. `GET /public/preview/{token}/`
   sends `Cache-Control: no-store`. Added for sections as well as
   pages (approved in review, §16 item 9 below) — `CmsSection` already
   had `PreviewableMixin` and a preview template from Phase 1.
   **Finding, addressed in the serializer design:**
   `DraftStateMixin.with_content_json` (called by `revision.
   as_object()`) preserves the *current* `live`/`has_unpublished_
   changes`/`first_published_at` but not `live_revision` — a
   previewed revision's own `live_revision_id` is whatever was live
   when *that revision was saved*, not necessarily today's. The
   existing public serializers resolve composition through `published_
   snapshot()`/`_snapshot()`, which reads `.live_revision`; reusing
   them unmodified on a previewed object would have silently
   re-resolved through that stale pointer instead of showing the
   previewed content. `_resolved_rows` is now built on a new
   `_resolve_composition_rows(source)` that takes an already-resolved
   source directly; the public serializers call it via `published_
   snapshot(value)` as before, and the new `CmsPagePreviewSerializer`
   calls it on the previewed object directly, with no `live_revision`
   indirection.
6. **Sitemap** — `GET /public/sitemap/` filters `seo_noindex` from
   each page's *published* snapshot (`published_snapshot`, hoisted out
   of the serializer module into `services/paths.py` so both the
   serializers and the sitemap view share one implementation), not the
   row — the same draft-isolation fix Phase 2 made for paths, since
   `update_page` writes `seo_noindex` straight to the row before any
   publish.
7. **Tests + lint** — 42 new Phase 3 API tests (124 total in
   `cms_api`, all passing); `flake8` clean; full suite 926 tests,
   30 failures + 5 errors + 8 skipped, identical counts to the Phase 2
   baseline — no regressions. No migrations (`makemigrations --check`
   clean): `go_live_at`/`expire_at` are inherited `DraftStateMixin`
   fields, and `Redirect` is Wagtail's own model.
8. **Pre-existing issue, reported, not fixed:** `EcommerceBackend/
   settings.py` assigns `CACHES` twice — the CMS-specific block
   (±line 243, intended per AD-12) is unconditionally overwritten by
   the general Redis `CACHES` block (±line 389) a little further down
   the file. `CMS_CACHE_URL_SETTINGS` is therefore currently inert;
   both caches happen to be the same Redis instance today, but the
   dedicated setting does nothing. Left alone, as it is Phase 5's
   (cache layer) concern and out of Phase 3 scope.

**Spec gaps inherited from Phase 3 scope:** navigation, media
management and the audit-log read API (Phase 4); the cache layer,
Wagtail Admin and the `CACHES` duplication above (Phase 5); the
featured-flag gap on product collections (open since Phase 0, §13.5
item 5).

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

## 16. Approved decisions (2026-11-06)

The design questions raised in review are resolved as follows:

1. **Wagtail version** — Wagtail 7.4 LTS with Django 5.2.x; the exact
   compatible patch version is pinned in Phase 0 (AD-1, §13.1).
2. **URLs** — derived from page hierarchy and slugs only; no arbitrary
   path overrides. `CMS_RESERVED_PATHS` is used, auditing existing
   Nuxt routes for conflicts (AD-1, §9).
3. **Deletion** — archive/unpublish is the default. Permanent deletion
   requires elevated permissions and dependency checks; Wagtail tree
   integrity is preserved (AD-16, §5.1, §5.2).
4. **Product sections** — LATEST = `created_at` DESC; BEST_SELLERS =
   net quantity sold over a rolling 30-day window; FEATURED = the
   existing product-domain flag; MANUAL = selected product IDs and
   ordering. Existing models are audited before implementation
   (AD-17, §5.4, §13.5).
5. **Wagtail Admin** — included in the initial release. Access requires
   `is_staff` and the appropriate CMS model permissions, integrated
   with the existing RBAC (AD-11, §8).
6. **Redirects** — historical redirects collapse directly to the latest
   canonical URL; loops are rejected; audit history is retained
   (AD-8, §9).
7. **Preview** — 30-minute, scoped, read-only tokens tied to authorized
   users and specific content revisions; drafts are never exposed
   through public endpoints nor cached (AD-15, §5.7, §10, §11).

Phase 3 implementation-time decisions (approved in review, 2026-11-09):

8. **Redirect history permission** — §8's permission matrix has no row
   for `GET /redirects/`; it is gated on `view_cmspage` rather than
   introducing a new `cms_api` codename or using the Wagtail-native
   `wagtailredirects.view_redirect` (which would break the convention
   that every CMS permission is a `cms_api` codename).
9. **Preview tokens cover sections too** — §6 lists the preview-token
   endpoint for pages only, but §5.7/AD-15 describe the mechanism
   generically (`kind`: page/section) and `CmsSection` already carries
   `PreviewableMixin` and a preview template from Phase 1, so `POST
   /sections/{id}/preview-token/` is added alongside the page one.

## 17. Out of scope (per spec §15)

Multi-tenant CMS, cross-store sharing, separate CMS services,
admin-defined section types, visual CSS customization, drag-and-drop
design, replacing product management or auth/RBAC. Also out of scope
for this design: adding CMS content to `content_security_api`'s scan
sources (a follow-up, noted for the decisions log when taken).

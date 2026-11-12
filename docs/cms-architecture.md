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
| `GET /public/navigation/{key}/` | resolved menu tree for an active menu; 404 for an unknown/inactive key. **Not cached** — the cache layer is Phase 5; this follows the Phase 2/3 precedent of leaving public reads uncached until then |
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
| `GET/POST/PATCH/DELETE /navigation/` | menu CRUD, gated on `manage_cms_navigation` |
| `POST /navigation/{id}/items/` `GET/PATCH/DELETE /navigation/{id}/items/{item_id}/` `PUT /navigation/{id}/items/reorder/` | nested item management (same sub-resource shape as page composition rows); same permission |
| `GET/PATCH /media-config/` | the `CmsMediaConfig` singleton, gated on `manage_cms_media` |
| `GET/POST/PATCH/DELETE /media/images/` | Wagtail `Image` CRUD: upload, title, `alt_text` (`Image.description`), delete-with-reference-check |
| `GET/POST/PATCH/DELETE /media/documents/` | Wagtail `Document` CRUD: upload, title, delete-with-reference-check |
| `GET /redirects/` | redirect list/history, gated on `view_cmspage` per §16 item 8 |
| `GET /audit-logs/` | CMS activity (actor, action, object, timestamp), gated on `view_cmspage`; `start_date`/`end_date`/`action`/`content_type` query params |

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

Implemented Phase 5C (2026-11-12) — see [Phase 5C verification
results](#phase-5c-verification-results-2026-11-12) for the full
report. Summary, correcting two details this section originally got
wrong (noted inline):

- `CACHES` (AD-12): the `"cms"` alias, Redis when
  `CMS_CACHE_URL_SETTINGS` is set, `LocMemCache` otherwise. Test
  settings use `DummyCache` for `"cms"` (every get/set is a no-op, so
  caching never leaks across tests); cache-behaviour tests opt into
  `LocMemCache` with `override_settings`.
- Cached payloads: the public page list, the public page detail *by
  page id* (not "page id + revision id" as originally written here —
  see the Phase 5C report for why), the sitemap, navigation trees,
  and the section-type schema.
- Invalidation is registry-based (`cms_api/services/cache.py`, the
  same pattern as `category_api/services/cache.py`, not
  `delete_pattern()`), driven by `transaction.on_commit` from two
  sources:
  - Wagtail's generic `published`/`unpublished` signals (filtered to
    `sender=CmsSection`) and the Page-specific `page_published`/
    `page_unpublished`/`post_page_move` signals (filtered to
    `sender=CmsPage`). There is no `snippet_published` signal in the
    installed Wagtail version — the original text above naming one
    was wrong; the generic `published`/`unpublished` pair is what
    `CmsSection` (and every other `DraftStateMixin` model) actually
    sends.
  - Explicit calls inside `services/pages.py` (archive/restore/
    delete), `services/cms_section.py` (archive) and
    `services/navigation.py` (every menu/item write) — none of these
    fire any Wagtail signal.
  - A global section's referencing pages are found via
    `ReferenceIndex.get_grouped_references_to`, filtered to
    `isinstance(source, Page)` (the index groups by the referencing
    object, which is an instance of the *base* `Page` model from
    multi-table inheritance — not the `CmsPage` class, which is what
    this section originally implied).
- Cache safety net TTL (`CMS_PUBLIC_CACHE_TTL`, 5 min) exists only for
  missed events; the defined consistency window after a successful,
  committed publish is **zero** (confirmed by tests that assert fresh
  content immediately after invalidation, no TTL wait).
- **Drafts and previews are never cached** (approved): preview responses
  send `Cache-Control: no-store`, and no draft payload is ever written
  to the cache. A 404 (unknown page path, inactive navigation key) is
  also never cached.

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
8. **Pre-existing issue, reported in this phase, fixed as a follow-up
   (2026-11-09):** `EcommerceBackend/settings.py` assigned `CACHES`
   twice — the CMS-specific block (intended per AD-12) was
   unconditionally overwritten by the general Redis `CACHES` block
   further down the file, making `CMS_CACHE_URL_SETTINGS` inert.
   Consolidated into one `CACHES` setting: `"default"` is the
   existing, unchanged Redis config every other app cache consumer
   already uses; `"cms"` is a new alias carrying the original
   Redis-when-configured/LocMem-otherwise fallback behaviour, reserved
   for Phase 5 (no code reads it yet). Verified: the effective
   `settings.CACHES` matches the pre-fix `"default"` exactly, the full
   suite (927 tests) shows the same 30 failures/5 errors/8 skipped as
   baseline, and `flake8` is clean. This is a settings fix only — no
   CMS cache *logic* was added, so Phase 5 is not started by it.

**Spec gaps inherited from Phase 3 scope:** navigation, media
management and the audit-log read API (Phase 4); the cache layer,
Wagtail Admin and the `CACHES` duplication above (Phase 5); the
featured-flag gap on product collections (open since Phase 0, §13.5
item 5).

## Phase 4A verification results (2026-11-09)

Scope delivered: the navigation half of §14 row 4 — `CmsNavigationMenu`
and `CmsNavigationItem` models, nested/ordered item management, the
`delete_page` navigation-reference guard, and the public menu-tree
read. Media management and the audit-log read API are **not** part of
this phase (Phase 4B).

1. **Models** (`cms_api/models/cms_navigation.py`) — `CmsNavigationMenu`
   (`TimeStampedModel, UserStampedModel, SoftDeleteModel`; `name`,
   `key` unique; `manage_cms_navigation` in `Meta.permissions`) and
   `CmsNavigationItem` (`TimeStampedModel`; `menu`, self-FK `parent`
   `on_delete=CASCADE`, `label`, `link_type` (`NavigationLinkType`:
   PAGE/EXTERNAL), `page` FK → `CmsPage` `on_delete=PROTECT`,
   `external_url` validated to `http`/`https` only via
   `URLValidator(schemes=[...])`, `is_visible`, `open_in_new_tab`,
   `sort_order`). A `CheckConstraint`
   (`cms_navigationitem_exactly_one_link_target`) enforces the XOR at
   the database level; `clean()` re-checks it and rejects an item
   being its own parent (self-FK cycles of length >1 are a
   service-layer check — see item 2). One migration,
   `0003_cmsnavigationmenu_cmsnavigationitem.py`
   (`makemigrations --check` clean afterwards).
2. **Services** (`cms_api/services/navigation.py`) — menu CRUD
   (`create_menu`/`update_menu`/`delete_menu`, the last calling
   `soft_delete()` per the repo's preferred-soft-delete convention);
   item CRUD (`add_navigation_item`/`update_navigation_item`/
   `remove_navigation_item`) and `reorder_navigation_items` (siblings
   under one `(menu, parent)`, same "order must list every sibling id
   exactly once" check as `reorder_page_sections`). `_validate_parent`
   rejects a `parent` from a different menu and walks the proposed
   parent's ancestor chain to reject a cycle (a descendant becoming
   an ancestor of itself) — tested explicitly
   (`test_a_descendant_cannot_become_an_ancestor`).
   `resolve_navigation_tree` builds the public tree: an invisible item
   prunes its whole subtree (not just itself), and a PAGE item whose
   target is not live or is archived is omitted — the same draft-
   isolation rule every other public CMS endpoint already enforces.
3. **`is_active` is the soft-delete flag, not a separate toggle.**
   `CmsNavigationMenu` inherits `is_active` from `SoftDeleteModel`;
   per §5.5 it is also the menu's only "enabled" field, so there is
   deliberately no second flag. To avoid two inconsistent paths to
   the same state, the write serializers never expose `is_active` —
   only `DELETE` (→ `soft_delete()`) changes it. Verified: `PATCH
   {"is_active": false}` is accepted (200) but has no effect
   (`test_is_active_is_not_writable_directly`); there is no restore
   endpoint, matching §6's table, which gives navigation no
   archive/restore row the way pages and sections have.
4. **Permission** — `manage_cms_navigation` is checked by one small
   `CmsNavigationPermission` class for every action on
   `CmsNavigationMenuViewSet` (menus and the nested item actions
   alike), not the usual `ModelPermissionAccess` add/view/change/
   delete split, matching §8's "all nav ops" row. Verified that the
   model's own auto-generated `add_cmsnavigationmenu`/
   `view_cmsnavigationmenu` codenames do *not* grant access on their
   own (`test_standard_model_permissions_are_not_sufficient`) — only
   `manage_cms_navigation` does.
5. **API** (`cms_api/views/v1/cms_navigation.py`,
   `cms_api/urls/v1.py`) — management:
   `GET/POST/PATCH/DELETE /api/v1/cms/navigation/`,
   `POST /navigation/{id}/items/`,
   `GET/PATCH/DELETE /navigation/{id}/items/{item_id}/`,
   `PUT /navigation/{id}/items/reorder/` (mirrors the
   `CmsPageViewSet` sections sub-resource pattern). Public:
   `GET /api/v1/cms/public/navigation/{key}/`, mounted under
   `cms/public/...` per the Phase 2/3 local convention, looked up by
   `key` (not `pk`); 404 for an unknown or inactive key. **No caching**
   — §6's original table annotated this endpoint "(cached)", but the
   cache layer is Phase 5 scope and Phase 2/3 deliberately left every
   other public read uncached for the same reason; this phase follows
   that precedent rather than building ahead of Phase 5. §6's table
   above is updated to reflect this.
6. **`delete_page` navigation guard (docs §5.1, 11)** — a
   `CmsNavigationItem` referencing the page is now listed in the
   structured `dependencies` response instead of surfacing as a raw
   `ProtectedError` once `page.delete()` actually runs. Because the
   FK is `PROTECT`, this dependency is **not** acknowledgeable the
   way child pages and `ReferenceIndex` references are:
   `?acknowledge=true` still returns 400 while any navigation item
   points at the page (`test_acknowledge_true_does_not_bypass_the_
   nav_guard`); removing or repointing the item allows the delete to
   proceed (`test_page_deletes_once_the_nav_item_is_removed`). Every
   existing Phase 2 delete-guard test (child pages, `acknowledge`)
   still passes unchanged.
7. **Admin** — `CmsNavigationMenu`/`CmsNavigationItem` registered in
   Django's plain `cms_api/admin.py` (previously empty), mirroring
   `category_api`'s `ModelAdmin` style. Not registered as a Wagtail
   snippet/in the Wagtail Admin — that surface is Phase 5 scope.
8. **Tests + lint** — 39 new tests in
   `cms_api/tests/test_api_cms_navigation.py` (163 total in `cms_api`,
   all passing); `flake8` clean; full suite 966 tests, 30 failures +
   5 errors + 8 skipped — identical to the Phase 3 baseline, no
   regressions.
9. **Docs scope note**: per this phase's instructions, only this
   architecture document was updated at the time. `docs/business-
   rules.md`, `docs/project-structure.md` and the `AGENTS.md`
   decisions log were synchronised once Phase 4B (media) was also
   complete — see the dated documentation-synchronisation note at the
   end of the Phase 4B section below.

**Spec gaps inherited from Phase 4A scope:** media management (Phase
4B, now complete — see below) and the audit-log read API (Phase 4C);
the cache layer, Wagtail Admin and the pre-existing `CACHES`
duplication (already fixed separately, see the Phase 3 section above)
remain Phase 5 concerns; the featured-flag gap on product collections
(open since Phase 0, §13.5 item 5).

## Phase 4B verification results (2026-11-09)

Scope delivered: the media half of §14 row 4 — `CmsMediaConfig`
singleton, upload validation, `GET/POST/PATCH/DELETE` for Wagtail
`Image`/`Document`, and reference-aware deletion. The audit-log read
API (Phase 4C) is **not** part of this phase.

1. **`CmsMediaConfig`** (`cms_api/models/cms_media.py`) —
   `max_image_upload_size` (default 10 MiB), `max_image_pixels`
   (default 128,000,000), `allowed_image_extensions` (`JSONField`,
   default `["jpg", "jpeg", "png", "webp"]` — matching this project's
   own `product_api.ProductImage` convention rather than Wagtail's
   own, broader default list), `max_document_upload_size` (default 20
   MiB), `allowed_document_extensions` (`JSONField`, default
   `["pdf"]`, per spec §5.6). `TimeStampedModel, UserStampedModel`
   base classes (no soft delete — a singleton config row is never
   deleted). `manage_cms_media` in `Meta.permissions`.
2. **Singleton enforcement, two layers** — `save()` always writes
   `pk=SINGLETON_PK` (`1`), and a `CheckConstraint(pk=1)` is the
   database-level backstop (a raw insert bypassing `save()`, e.g.
   `bulk_create`, still cannot create a second row). Verified directly:
   `bulk_create([CmsMediaConfig(pk=2, ...)])` raises `IntegrityError`.
   `get_solo()` (`classmethod`, `get_or_create(pk=SINGLETON_PK)`) is
   the one way callers read it, so the row always exists with sane
   defaults from the first access — no "config not yet created" state
   to handle anywhere else.
3. **Finding (confirmed, drove the validation design): Wagtail's own
   upload limits do not apply outside its admin forms.** Traced the
   installed package directly: image size/pixel/format checks live
   only in `wagtail.images.fields.WagtailImageField`, a Django **form**
   field wired in by Wagtail's admin views, never by `Image.full_clean()`
   (`Image` has no `clean()` method at all) or by a plain DRF
   serializer. `Document.clean()` does check `WAGTAILDOCS_EXTENSIONS`,
   but that setting is unset in this project, so it is a no-op today
   either way. Every limit `CmsMediaConfig` provides is therefore
   enforced entirely in `cms_api/services/media.py`, read from
   `CmsMediaConfig.get_solo()` — never from `WAGTAILIMAGES_*`/
   `WAGTAILDOCS_*` settings (none of which are set).
4. **Upload validation** (`cms_api/services/media.py`) — images: size
   → extension allowlist → a real Pillow decode (`PIL.Image.open(...)
   .verify()`, adapting the existing pattern in
   `product_api/serializers/product_image.py` instead of adding a
   dependency) → decoded format must match the claimed extension →
   pixel-count limit. Documents: size → extension allowlist (no Pillow
   decode attempted; documents are not necessarily an image format).
   The browser-supplied `content_type` is never trusted — verified
   with a renamed non-image file (rejected on content) and a real JPEG
   renamed to `.png` (decodes, but format/extension mismatch is
   rejected).
5. **Metadata** — `alt_text` is exposed as a renamed view of Wagtail's
   own `Image.description` (`source="description"` in both read and
   write serializers) rather than a new field or a custom `Image`
   model, resolving the naming mismatch the Phase 4B audit flagged
   against `product_api.ProductImage.alt_text`. `title` is Wagtail's
   native field on both models, defaulting to the uploaded filename
   when omitted. `Document` has no description/alt-text equivalent in
   Wagtail core and none was added (no custom model, per this phase's
   constraints).
6. **Reference-aware deletion** — `ReferenceIndex.get_grouped_
   references_to(obj)`, the exact call `delete_section` already uses;
   `Image`/`Document` are registered as `ReferenceIndex` targets by
   Wagtail's own `wagtail.images`/`wagtail.documents` app configs, so
   no new registration was needed. A referenced image or document is
   never deletable (no `acknowledge` override, matching `delete_
   section`, not the page delete-guard's acknowledgeable dependencies)
   and returns the same structured `dependencies` response every
   other CMS delete guard uses. Verified with synthetic
   `ReferenceIndex` rows (`factories.reference_to()`, the same helper
   the section-lifecycle tests already use) for both images and
   documents — no content type in this project links to a `Document`
   yet (no block uses `DocumentChooserBlock`), so the document guard,
   while correct, has nothing real to find outside this synthetic
   test today. Several section blocks already use `ImageChooserBlock`
   (`HeroBannerBlock`, `ImageWithTextBlock`, `GalleryImageBlock`, the
   video block's thumbnail) and `CmsPage.og_image` is a plain FK, so
   the image guard is exercised by real content references too.
7. **API** (`cms_api/views/v1/cms_media.py`,
   `cms_api/urls/v1.py`) — `GET/PATCH /api/v1/cms/media-config/`
   (singleton); `GET/POST/PATCH/DELETE /api/v1/cms/media/images/` and
   `.../media/documents/` (two resources, not one combined `/media/`
   endpoint — resolved from the Phase 4B audit's open question in
   favour of the two Wagtail models' different fields). One
   permission, `manage_cms_media`, for every action on all three
   (`CmsMediaPermission`, the same one-permission-for-everything shape
   `CmsNavigationPermission` uses). No public read — media is
   management-only per §6.
8. **Admin** — `CmsMediaConfig` registered in `cms_api/admin.py`
   (`has_add_permission` refuses "Add" once the row exists;
   `has_delete_permission` always refuses). `Image`/`Document`
   themselves are not separately admin-registered (Wagtail Admin
   integration is Phase 5 scope; nothing in this phase needed a plain
   Django-admin view for them).
9. **Tests + lint** — 30 new tests in
   `cms_api/tests/test_api_cms_media.py` (193 total in `cms_api`, all
   passing); `flake8` clean; full suite 996 tests, 30 failures + 5
   errors + 8 skipped — identical to the Phase 4A baseline, no
   regressions. One migration, `0004_cmsmediaconfig.py`
   (`makemigrations --check` clean afterwards).

**Spec gaps inherited from Phase 4B scope:** the audit-log read API
(Phase 4C); the cache layer, Wagtail Admin and the `CACHES`
duplication (already fixed, Phase 3 section) remain Phase 5 concerns;
the featured-flag gap on product collections (open since Phase 0,
§13.5 item 5).

**Documentation synchronisation (2026-11-09):** this architecture
document, `docs/business-rules.md`, `docs/project-structure.md` and
the `AGENTS.md` decisions log were updated together once Phase 4A and
4B were both implemented and verified, so navigation and media are
documented in one consistent pass rather than twice. No code,
settings, migrations or tests were changed as part of this
documentation update.

## Phase 4C verification results (2026-11-09)

Scope delivered: the audit-log half of §14 row 4 — complete, correct
audit-event coverage for every CMS write path, and the read-only
`GET /api/v1/cms/audit-logs/`. This closes out Phase 4 in full (4A
navigation, 4B media, 4C audit-log).

1. **No new storage.** Reuses Wagtail's own `PageLogEntry` (pages)
   and `ModelLogEntry` (everything else — registered by Wagtail core
   itself, `wagtail/wagtail_hooks.py`, as the catch-all logger for
   *any* Django model, confirmed by reading the installed package).
   No new model, no migration.
2. **Gaps found by the Phase 4C audit, fixed and verified
   empirically** (ran the real service functions against a scratch
   database and inspected the resulting log rows, not just read the
   code):
   - `archive_page`/`restore_page` previously logged nothing; now log
     `cms_api.archive`/`cms_api.restore` (new action names,
     registered via `register_log_actions`), mirroring
     `archive_section`'s existing pattern.
   - `delete_page` called `page.delete()` with no `user`, so the
     resulting `wagtail.delete` entry was always attributed to
     "system". Fixed to `page.delete(user=user,
     skip_permission_checks=True)` — passing `user` turns on
     `DeletePageAction`'s own internal permission check (against
     Wagtail's auto-generated delete permission, not
     `cms_api.delete_cmspage`, already enforced in DRF), so
     `skip_permission_checks=True` was required alongside it; caught
     by rerunning the full `cms_api` suite after the change, not by
     inspection.
   - `rollback_page`/`rollback_section` were logged, but as a plain
     `wagtail.publish`/indistinguishable from an ordinary publish.
     Both now pass `log_action="cms_api.rollback"` (new action name)
     into the final `PublishPageRevisionAction`/`PublishRevisionAction`
     call.
3. **Navigation and media now log every write.** `cms_api/services/
   navigation.py`: menu create/update/delete use `wagtail.create`/
   `wagtail.edit`/`wagtail.delete` (core actions, semantically exact
   fits, no new names needed); item create/update/delete the same,
   logged against the item itself, not the menu; `reorder_navigation_
   items` logs exactly **one** entry per call, against the menu, with
   a new `cms_api.navigation.reorder` action and `data={"parent_id":
   ..., "order": [...]}`  — reordering many siblings in one request
   is one audit event, not one per item touched. `cms_api/services/
   media.py`: image/document create/update/delete use the same core
   actions; `CmsMediaConfig` updates log `wagtail.edit`. A delete is
   always logged *before* the row is actually removed (`image.delete()`/
   `item.delete()` clear the in-memory pk afterward, and
   `log_action()` requires a pk) — the one ordering detail that would
   otherwise raise `ValueError` or silently log nothing.
4. **Read API** (`cms_api/services/audit_log.py`,
   `cms_api/serializers/cms_audit_log.py`,
   `cms_api/views/v1/cms_audit_log.py`) — `GET /api/v1/cms/
   audit-logs/`, gated on `view_cmspage` (§16 item 8's reuse pattern,
   extended here rather than inventing a new codename). `PageLogEntry`
   and `ModelLogEntry` cannot be combined with a single queryset
   (`PageLogEntry.object_id` is a Python `@cached_property`
   — `page_id` — not a database column, confirmed by reading the
   installed package), so each is queried and filtered separately —
   by the resolved date window, and by `action`/`content_type` when
   given — and only the two filtered, already-bounded results are
   merged and sorted by timestamp in Python before pagination (the
   project's existing `EcommerceBackend.core.pagination.Pagination`,
   which works unmodified on a plain list). The content-type allowlist
   (`CMS_AUDIT_CONTENT_TYPES`: `CmsPage`, `CmsSection`,
   `CmsNavigationMenu`, `CmsNavigationItem`, `Image`, `Document`,
   `CmsMediaConfig`) is explicit, not "every `ModelLogEntry` row":
   `Product`/`Category`/`Brand` are registered as Wagtail snippets for
   chooser-block support and would log to the same table if ever
   edited through Wagtail Admin, which must never surface as "CMS
   activity". Verified with a synthetic log entry on an unrelated
   model (`user_api.User`, standing in for exactly this risk) —
   confirmed absent from the response.
5. **Query bounds** — default window is the most recent 90 days
   (`resolve_audit_log_window`); an explicit `start_date`/`end_date`
   wider than 365 days is clamped, not rejected (silently keeping the
   safety property regardless of what a caller asks for, rather than
   erroring on an honest mistake); `start_date` after `end_date` is a
   400. The date filter is applied at the queryset level on both
   sources *before* the Python merge, so memory use is bounded by the
   filtered window, never by either table's full history.
6. **Response shape** — `actor` (username, `null` for a system-
   attributed entry such as the scheduled sweep's `wagtail.publish.
   scheduled`/`wagtail.unpublish.scheduled`), `actor_id`, `action`,
   `model` (`app_label.ModelName`, matching the existing dependency-
   response convention in `delete_page`/`delete_section`, not the
   lowercase `content_type.model` string), `object_id`, `object`
   (the logged title), `timestamp`, `data`.
7. **Tests + lint** — 27 new tests in
   `cms_api/tests/test_api_cms_audit_log.py` (220 total in `cms_api`,
   all passing); `flake8` clean; full suite 1023 tests, 30 failures +
   5 errors + 8 skipped — identical to the Phase 4B baseline, no
   regressions. No migrations (nothing new to migrate).

**Spec gaps inherited from Phase 4C scope:** none within Phase 4 —
navigation, media and audit-log are all complete. The cache layer,
Wagtail Admin and the `CACHES` duplication (already fixed, Phase 3
section) remain Phase 5 concerns; the featured-flag gap on product
collections (open since Phase 0, §13.5 item 5).

**Docs scope note**: per this phase's instructions, only this
architecture document was updated with verified implementation
details. `docs/business-rules.md`, `docs/project-structure.md` and
the `AGENTS.md` decisions log still need their Phase 4C entries —
the final cross-document Phase 4 synchronisation is a separate,
explicitly deferred step.

## Phase 5B verification results (2026-11-12)

Scope delivered: the Wagtail Admin (`/cms-admin/`) now enforces the
same business rules as the DRF CMS API — reserved paths,
navigation-referenced deletes, slug-change redirects, audit parity
and dependency-guarded section deletion. Phase 5A (admin RBAC) is
documented in `docs/reports/cms-phase5a-verification.md`.

1. **Reserved paths (`CMS_RESERVED_PATHS`) cannot be published via
   the admin.** Two layers, because not every path to live passes
   through a form: `CmsPageForm.clean_slug` (`cms_api/forms.py`,
   installed as `CmsPage.base_form_class` in `wagtail_hooks.py`,
   mirroring Wagtail's own `Page.base_form_class` assignment) rejects
   a slug change whose prospective path is reserved, exactly like
   `services/pages.py` (checked only when the slug changes, never on
   an untouched save); and a `before_publish_page` hook re-checks
   `page.url_path` at publish time, covering bulk publish, workflow
   approval and pages moved under a reserved parent. The hook vetoes
   with an error message + redirect (Wagtail's own hook contract:
   return an `HttpResponse` to veto).
2. **Navigation-referenced pages cannot be deleted from the admin,
   and never surface a raw `ProtectedError`.** `CmsNavigationItem.
   page` is a `PROTECT` FK, so deleting a *parent* whose *descendant*
   was referenced raised a raw `ProtectedError` (a 500) in the DRF
   path too — a pre-existing hole, now fixed: the shared
   `nav_item_dependencies(page)` helper covers the whole subtree and
   `delete_page` returns the structured `dependencies` response for
   it (message updated to "Page or one of its descendant pages…"). A
   `before_delete_page` hook mirrors the guard for the admin (it runs
   on both the confirmation page and the POST). Like the DRF guard,
   this dependency is never acknowledgeable.
3. **Slug-change redirects on admin publishes match the DRF
   services exactly once.** Wagtail Admin, bulk publish and workflow
   approval never call `create_redirects_for_published_change`
   explicitly, so redirects for those are created from signals: a
   `pre_save` receiver snapshots the published paths at the moment a
   publish flips `live_revision` (the database row is still
   pre-publish there — the same snapshot `services/pages.py` takes
   explicitly) and a `page_published` receiver turns that snapshot
   into redirects via the same `create_slug_redirect` helper (so
   rename-back drops the stale redirect on this path too). The DRF
   services and the scheduled sweep keep creating their redirects
   explicitly *with the acting user* and wrap the Wagtail publish in
   the nestable thread-local `suppress_signal_redirects()`, so
   exactly one redirect row and one `cms_api.redirect.create` log
   entry exist per moved path however the page goes live. Receivers
   connect in `apps.py:ready()` with `dispatch_uid`s. Wagtail's own
   `WAGTAILREDIRECTS_AUTO_CREATE` stays disabled (Phase 3).
4. **Section delete via the admin goes through `delete_section`.**
   `CmsSectionDeleteView` (installed as `delete_view_class` on the
   Phase 5A `CmsSectionSnippetViewSet`) replaces Wagtail's stock
   hard delete with the same service the DRF API uses: ReferenceIndex
   dependency guard (a referenced section's delete is refused with an
   error message instead of a 500), `soft_delete()`, and a
   `wagtail.delete` log entry attributed to the acting user — closing
   the audit gap where admin deletes logged with the LogContext user
   or not at all.
5. **Tests.** `cms_api/tests/test_wagtail_admin_business_rules.py`
   (11 tests): reserved-path form rejection + publish-hook veto +
   normal publish unaffected; admin slug-change publish creates
   exactly one redirect + one log entry, rename-back drops the stale
   redirect, and a DRF publish with a slug change yields exactly one
   of each (the suppression proof); nav-referenced page/subtree
   delete refused via admin and the DRF structured error (not
   `ProtectedError`); admin section delete soft-deletes with a
   user-attributed log, referenced section delete refused.

**Residual gaps (deliberate, out of Phase 5B scope):**
- An admin *revert to a previous revision* logs `wagtail.edit`/
  `wagtail.publish`, not `cms_api.rollback` — no Wagtail hook exposes
  the revision context needed to tell a revert from an ordinary
  publish. DRF rollbacks log `cms_api.rollback` as before.
- Redirects created through the signal path log the acting user via
  Wagtail's LogContext fallback (correct during a normal admin
  request) rather than an explicit `user=`; only the DRF/sweep paths
  pass the acting user explicitly.
- A page moved under a reserved parent is still blocked at publish
  time (the `before_publish_page` hook), but the move itself is
  accepted; the move action never passes through a page form.

## Phase 5C verification results (2026-11-12)

Scope delivered: the cache layer (§10, AD-12) — Redis-backed public
response caching with dependency-aware, event-driven invalidation.
Follows the read-only Phase 5C audit (same date), which found no CMS
caching code existed yet despite the `"cms"` alias already being
configured.

1. **Cache service** (`cms_api/services/cache.py`) — a registry-key
   pattern copied from `category_api/services/cache.py`: a group
   (`page:<id>`, `navigation:<key>`, `pages-list`, `sitemap`) tracks
   the literal cache keys tagged under it, so invalidation never
   depends on `delete_pattern()` (unavailable on `LocMemCache`/
   `DummyCache`, and explicitly excluded by this phase's brief). The
   cache object is resolved fresh on every call (never bound at
   module import), so `override_settings(CACHES=...)` in tests takes
   effect immediately.
2. **Cache key design deliberately has no path-keyed entries.** The
   audit flagged that a page's rendered `path` depends on its
   ancestors' published slugs (`services/paths.py:
   published_url_path`), so a cache keyed on `(page_id, revision_id)`
   alone — as this section originally specified — would leave a
   descendant's cached detail stale after a parent rename, without
   the write path ever knowing the descendant needs invalidating.
   Instead, `?path=` resolution reads the cached page **list** (itself
   keyed with no parameters) to find the matching `id`, then reads/
   writes a per-id detail cache. A path lookup miss (unknown path,
   archived page) is never cached, so a later cache-key scheme needs
   no stale-404 handling either.
3. **Test settings default `"cms"` to `DummyCache`**
   (`EcommerceBackend/test_settings.py`), not `LocMemCache`: every
   get() misses and every set() is a no-op, so the ~1,060 pre-existing
   tests run the real caching code path with zero behavioural
   difference and no risk of one test's cached response leaking into
   another's. `cms_api/tests/test_api_cms_cache.py` opts into
   `LocMemCache` via `override_settings` and clears it in `setUp`
   (`LocMemCache` with no explicit `LOCATION` shares one process-wide
   store). `transaction.on_commit` never fires inside `TestCase` (the
   whole test runs in one transaction that is rolled back, never
   committed), so every write under test is wrapped in
   `self.captureOnCommitCallbacks(...)`.
4. **Signals, verified against the installed Wagtail 7.4.4 source,
   not assumed.** `PublishRevisionAction`/`UnpublishAction` (sections)
   send only the generic `wagtail.signals.published`/`unpublished`;
   `PublishPageRevisionAction`/`UnpublishPageAction` (pages) send
   *both* the generic pair **and** `page_published`/`page_unpublished`
   — so the cache's generic-signal receiver is connected with
   `sender=CmsSection` only, and pages are covered separately via the
   page-specific signals, with no double invalidation. `post_page_move`
   covers a Wagtail Admin tree move/reorder, which can change a page's
   (and its descendants') published path with no publish/unpublish at
   all (§5B residual gap: "the move itself is accepted"). One receiver
   per signal, filtered by `sender`, covers every pathway that fires
   it — DRF, Wagtail Admin, the Phase 3 scheduled sweep (`publish_
   scheduled`, confirmed to resolve the specific object/class before
   sending even though it queries the base `Page` table), and rollback
   (reuses the same publish action). No pathway-specific invalidation
   call was needed in `services/pages.py` or `services/scheduling.py`.
5. **Explicit, signal-free invalidation** where no Wagtail signal
   exists: page archive/restore/permanent delete (`services/
   pages.py`), section archive (`services/cms_section.py` — soft
   delete needs none, since its own `ReferenceIndex` guard already
   proved nothing references the section), and every navigation menu/
   item create/update/delete/reorder (`services/navigation.py` — plain
   Django models, no Wagtail revisions at all). `update_menu` captures
   the menu's `key` before a rename and invalidates both the old and
   new key.
6. **Global section fan-out: a real bug found and fixed by the new
   tests, not by inspection.** `ReferenceIndex.get_grouped_references_
   to(section)` groups by the *referencing object itself*
   (`ReferenceGroups.__iter__` loads it via `content_type.
   get_object_for_this_type(...)`), which is an instance of the
   *base* Wagtail `Page` model (multi-table inheritance) — never a
   `CmsPage` instance or the `CmsPage` class. An initial
   implementation filtering `source is CmsPage` silently matched
   nothing; `cms_api/tests/test_api_cms_cache.py`'s
   `test_global_section_publish_invalidates_every_referencing_page`
   caught this (fresh content never appeared after invalidation) and
   the fix is `isinstance(source, Page)` (`CmsPage` is the only
   concrete page model, AD-3, so every match is a `CmsPage` row). The
   page list, sitemap and navigation never embed section content, so
   a section change invalidates only the referencing pages' own
   detail cache.
7. **A known, bounded fan-out gap, not closed in this phase.**
   `ReferenceIndex` is rebuilt from a page's *current* (possibly
   draft) composition rows on every `save()`, not from its published
   revision's frozen content. A page whose *live* revision still
   embeds section S, but whose unpublished draft has since dropped S,
   would be missed by the fan-out when S next changes — closing this
   would mean scanning live revision content directly, a heavier
   mechanism this phase's brief did not call for. The safety-net TTL
   bounds the resulting staleness window to `CMS_PUBLIC_CACHE_TTL`
   (5 minutes); this is the one case where this phase's "zero stale"
   claim does not hold.
8. **Page move, delete and the pre-existing `pre_delete_page_unpublish`
   hook.** Wagtail unpublishes any live page before deleting it
   (`wagtail/signal_handlers.py`, unconditional on every page delete,
   admin or DRF), which already invalidates through the
   `page_unpublished` receiver; `delete_page` additionally captures
   the page and its live descendants' ids *before* calling
   `page.delete()` (after which `get_descendants()` can no longer be
   queried) and invalidates them explicitly, as defense in depth
   rather than relying solely on that side effect.
9. **Section-type schema caching is a single shared entry, not
   per-user.** Verified by reading `cms_api/sections/registry.py`:
   `section_type_schemas()` takes no arguments and derives its output
   entirely from the code-defined `SECTION_TYPES` registry, with no
   per-user or per-permission branching. The endpoint stays
   `IsAuthenticated`; the cache read happens only after that check.
   Nothing invalidates this cache (it has no group) — it expires only
   via its TTL, which bounds how long a post-deploy registry change
   can take to appear.
10. **Tests + lint.** 24 new tests in `cms_api/tests/
    test_api_cms_cache.py` (demonstrating, for the flagship cases,
    stale-then-fresh without a TTL wait via `captureOnCommitCallbacks
    (execute=False)` followed by manually running the captured
    callbacks); full `cms_api` suite 285 tests, all passing (up from
    261); `flake8` clean; full project suite 1,090 tests, 30 failures
    + 5 errors + 8 skipped — identical counts to the Phase 4B/4C/5B
    baseline, no regressions; `makemigrations --check` clean (no
    model changes this phase).

**Spec corrections made while implementing (not followed as written,
with reasons — see §10 above for the fixed text):**
- §10 named a `snippet_published` signal that does not exist in the
  installed Wagtail version.
- §10 specified caching page payloads by "page id + revision id,"
  which cannot be invalidated correctly for a descendant whose own
  revision never changed when an ancestor's slug does.

**Spec gaps inherited from Phase 5C scope:** the known
`ReferenceIndex` draft/published fan-out gap (item 7 above) and the
redirect-resolution endpoint, which stays uncached per this phase's
brief ("do not introduce caching for redirect resolution unless the
existing architecture demonstrates a specific need" — it does not:
§10 never listed it among the payloads to cache).

## 14. Implementation phases

Each phase ends with `flake8`, tests for the new surface, and docs
updates.

| Phase | Scope |
|---|---|
| 0 | Foundation: Wagtail install + settings + URL mounts + empty `cms_api` + verification items (§13) |
| 1 | Section-type registry + `CmsSection` snippet: CRUD, publish/unpublish, revisions/rollback, archive, reference guard, section-type schema API |
| 2 | `CmsPage` + `CmsPageSection`: CRUD from templates, composition writes/reorder, revisions/rollback, publish/unpublish/archive, reserved-path validation |
| 3 | Lifecycle: scheduled publish/unpublish (Beat), redirects service, preview tokens, sitemap endpoint |
| 4 | Navigation + media management + audit-log API — delivered as three sub-phases, all complete: **4A** navigation (`CmsNavigationMenu`/`CmsNavigationItem`), **4B** media (`CmsMediaConfig`, images/documents), **4C** audit-log read API |
| 5 | Cache layer + invalidation (complete, **5C**), Wagtail Admin at `/cms-admin/` (complete, **5A**/**5B**), full test pass, docs |

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

Phase 4A implementation-time decision (approved in review, 2026-11-09):

10. **Navigation history/management has one permission, not four** —
    `manage_cms_navigation` gates every action on both
    `CmsNavigationMenu` and `CmsNavigationItem` (menu and item CRUD
    alike), not the usual `ModelPermissionAccess` add/view/change/
    delete split, matching §8's "all nav ops" row literally. There is
    deliberately no restore action for a soft-deleted menu (§6's table
    gives navigation none, unlike pages/sections).

Phase 4B implementation-time decisions (approved in review, 2026-11-09):

11. **Media is two resources, not one** — `/media/images/` and
    `/media/documents/` (not a single combined `/media/` endpoint):
    `Image` and `Document` have different fields, and this matches the
    two-ViewSet shape the rest of the API already uses for
    structurally different resources, resolving the Phase 4B audit's
    open question in favour of the split.
12. **`CmsMediaConfig` is exposed via its own endpoint** —
    `GET/PATCH /media-config/`, gated on `manage_cms_media`, even
    though the original spec table (before this phase) listed only
    `/media/` for images/documents and no config endpoint at all. A
    DB-backed config that nothing can read or edit through the API
    would be no more useful than a static setting; this was the Phase
    4B audit's other open question, resolved the same way.
13. **`alt_text` is `Image.description`, renamed** — not a new field
    and not a custom `Image` model subclass (both were explicitly
    ruled out for this phase); `source="description"` in the
    serializer reconciles Wagtail's own naming with this project's
    `ProductImage.alt_text` convention without a schema change.

Phase 4C implementation-time decision (approved in review, 2026-11-09):

14. **Audit-log read permission reuses `view_cmspage`** — same reuse
    already approved for `GET /redirects/` (item 8 above) rather than
    a new codename, even though audit history spans every CMS-owned
    content type, not just pages. A wide date-range request is
    clamped to 365 days rather than rejected with a 400, keeping the
    "never load the full history" property regardless of what a
    caller asks for.

## 17. Out of scope (per spec §15)

Multi-tenant CMS, cross-store sharing, separate CMS services,
admin-defined section types, visual CSS customization, drag-and-drop
design, replacing product management or auth/RBAC. Also out of scope
for this design: adding CMS content to `content_security_api`'s scan
sources (a follow-up, noted for the decisions log when taken).

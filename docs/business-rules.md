# Business Rules

Describes the **current implementation**, verified against the code.
Entities are in [domain-model.md](domain-model.md); coding conventions are in
[conventions.md](conventions.md).


## Products

### Product Images

Product images are managed independently from product records and support a reusable gallery workflow.

- A product may have many images.
- Images are uploaded after product creation.
- The first active image becomes the default image.
- Exactly one active image is expected to be marked as default.
- This rule is enforced at the database level via a partial unique constraint and at the service layer for all create, update, and set-default operations.
- Image ordering is managed server-side and remains sequential.
- Soft deletion is used for image removal.
- Replacement updates the stored file while preserving metadata and image identity.

### Brand

Brand represents a product manufacturer or brand name.

- Brand name must be unique
- Slug is auto-generated and cannot be updated (SEO safety)
- Brand can be soft-deleted (is_active flag)
- Search available by name and description
- Publicly readable, authenticated create/update/delete

---

## Authentication

Public registration endpoint (`POST /api/v1/auth/register/`) allows website customers to sign up.

Registration creates:
- User account with email and hashed password
- CustomerProfile with default type "WEBSITE"

Email must be unique.

---

## Inventory

Inventory changes must be traceable.

Inventory should only change through:

- Purchase
- Sale
- Return
- Adjustment

Never silently modify stock.

---

## Purchases

Purchases may:

- Increase inventory
- Create accounting transactions

Inventory and accounting must remain synchronized.

---

## Sales

Sales may:

- Reduce inventory
- Create accounting transactions

Stock must be validated before sale completion.

`GET /api/v1/sales/summary/` and `GET /api/v1/sales/amount-summary/`
return read-only sales counts and `total_amount` sums grouped by status
for every status (absent statuses report `0` / `0.00`). Both honour the
list endpoint's filters; they are not paginated.

`GET /api/v1/sales/pending-count/` returns the count of active sales in
`PENDING` status as `data.pending_orders`. It is not paginated and does
not honour list filters; soft-deleted (`is_active=False`) sales are
excluded.

`GET /api/v1/sales/reports/performance/` returns order and revenue
totals for a reporting period ending today (`days`, default `90`, max
`365`), compared against the immediately preceding period of equal
duration, plus a day-by-day trend that is zero-filled for dates with no
orders. It honours the `channel`, `customer` and `status` sale filters
(applied identically to both periods) but not `start_date`/`end_date`,
`search` or `ordering`, since `days` already defines the window. A growth
percentage is `null` when the corresponding previous-period value is
zero. Like `amount-summary`, revenue totals every matched status
(including `CANCELLED` and `RETURNED`) unless `status` narrows it; it is
not paginated.

Available stock is active inventory movements minus active, unexpired
storefront reservations. POS confirmation and storefront reservation both
lock the product variant rows (in primary-key order) before checking it, so
a POS sale cannot take stock reserved for a storefront order and concurrent
sales cannot oversell.

### Storefront orders

API contract: [checkout-api.md](checkout-api.md).

- A product with no active variant is sold through a **default variant**
  created at its first storefront sale (SKU `P-<product id>`, no colour or
  size; `product_api.services.get_or_create_default_variant`). A product
  with several active variants cannot be ordered from the cart (approved
  2026-10-25).
- A variant is **stock-tracked** once it has an active inventory movement
  (`inventory_api.services.is_stock_tracked`). Untracked variants are sold
  without a reservation, never expire and record no movement when
  confirmed; recording opening stock switches the product to the normal
  rules below (approved 2026-10-25).
- Placing an order reserves stock for `CHECKOUT_RESERVATION_MINUTES`
  (30) for every stock-tracked variant. Staff confirmation consumes the
  reservation and deducts stock; an unreserved item whose variant became
  tracked after the order was placed is stock-checked and deducted at
  confirmation.
- An order whose reservation expires while it is still PENDING is
  **cancelled automatically** by the `expire-pending-orders` Celery Beat
  task (approved 2026-10-13): stock is released, status becomes
  `CANCELLED`, and the customer is emailed to place a new order. An expired
  order can never be confirmed.
- Customers may cancel only their own PENDING orders. Status changes lock
  the Sale row, so a cancellation cannot overwrite a confirmation.
- Discounts and taxes are not supported on storefront orders: confirmation
  is refused unless total = subtotal + shipping.
- The shipping zone of an order is resolved from the delivery address in
  this order of precedence (approved 2026-10-25): the zone the customer
  chose for the address (`CustomerAddress.shipping_zone`, when still
  active) → postcode rule → city rule → the default zone. Shipping charges
  are always the zone's `ShippingRate` for the chosen method, computed on
  the backend; the storefront never sends a charge.
- Confirmation debits Accounts Receivable and credits product and shipping
  revenue. COD collection (`collect_sale_payment` permission, DELIVERED
  orders only, once) debits the COD payment method's asset account and
  credits Accounts Receivable by the amount posted at confirmation; it is
  refused if that differs from the order total. The collection entry is
  linked as `Sale.collection_transaction`.

### Emails

Order emails are queued after the order commits; a mail failure never
affects the order. An email stuck in PENDING for 15 minutes is
re-dispatched (at most 3 times) only if its template context was stored,
which is done for order emails but not for emails carrying tokens. An email
stuck in PROCESSING is marked FAILED and never resent automatically, since
it may already have been delivered.

### Order notifications

Internal recipients (`OrderNotificationRecipient`, managed at
`/api/v1/email/order-notification-recipients/` behind the model's
view/add/change/delete permissions) are alerted when:

- any sale is created — POS (`create_sale`) or storefront checkout
  (`create_order`), every channel;
- an order is cancelled by the customer (`cancel_order`) or by staff
  (`update_sale_status` to `CANCELLED`).

Automatic cancellation of an expired reservation does **not** notify.
The alert is a short notice (invoice, channel, customer name, item count,
total, admin link) — not a copy of the order; it carries no line items,
address or phone. Each active, non-deleted recipient gets its own email,
idempotent per sale, event and recipient. Like customer order emails it is
queued after commit and never affects the order.

---

## Accounting

Financial records are historical records.

Avoid modifying posted transactions.

Prefer adjustment entries.

---

## Customers

Customer balances must reflect:

- Sales
- Payments
- Adjustments

### Customer address creation

Creating an address (`POST /api/v1/customer-addresses/`) provisions a
`CustomerProfile` for the requesting user if none exists
(`customer_type="WEBSITE"`), inside the same transaction as the address.
Any authenticated user is eligible; role is not checked.

An existing inactive profile is never reactivated or replaced: creation
fails with `400`. Listing addresses (`GET /api/v1/customer-addresses/`)
never provisions a profile — a user without one gets an empty list.

---

## Content Security

Rules approved 2026-08-25 for the Content Security Scanner
(`content_security_api`). These are the security-sensitive values the
scanner depends on; do not change them without a matching decision entry.

### Detection is configurable, not hardcoded

Every detection rule is a database row. Seven rule models back the seven
detectors. A rule is evaluated only when it is enabled (`is_enabled`),
active and not soft deleted. `is_enabled` is the administrator's detection
toggle and is deliberately separate from the `is_active` / `deleted_at`
pair that records deletion.

Rules are global: a rule applies to every scanned field of every content
type. There is no content-type scoping column.

Administrators never supply a regular expression. Keyword rules match
`WORD` (word boundaries) or `SUBSTRING`; domain rules match `EXACT` or
`SUBDOMAIN`. Patterns are built by the application from the literal rule
value, so there is no catastrophic-backtracking surface.

### Severity weights and risk score

| Severity | Weight |
|---|---|
| `INFO` | 0 |
| `LOW` | 10 |
| `MEDIUM` | 25 |
| `HIGH` | 50 |
| `CRITICAL` | 80 |

`risk_score` is the sum of the weights of the **distinct** findings, capped
at 100. Findings are deduplicated by (detector, rule, matched value) before
scoring, so the same match repeated within one field counts once; the
repetition count is recorded in the finding's `metadata["occurrences"]`.

### Status thresholds

| Score | Status |
|---|---|
| 0 | `CLEAN` |
| 1 - 24 | `LOW_RISK` |
| 25 - 49 | `REVIEW` |
| 50 - 79 | `HIGH_RISK` |
| 80 - 100 | `CRITICAL` |

### Seeded rule severities

Severity is graded by execution capability. `CRITICAL` is reserved for rules
that mean arbitrary script execution: the `script` tag, the `javascript:`
scheme and the `data:text/html` scheme. Remote-content embedding
(`iframe`, `object`, `embed`), `form`, inline event handlers and every
redirect mechanism including meta refresh are `HIGH`. Hidden-content
patterns are `MEDIUM`.

The seed migration installs **no keyword rules and no domain rules**. The
repository defines no suspicious keyword or domain list, and none is
invented; those tables start empty and are populated by authorised users.

The `BASE64` obfuscation indicator ships **disabled**, because migrated
WordPress content commonly carries legitimate `data:` image URIs.

### A finding is not a verdict

A rule match means content warrants a look, not that it is malicious.
Review states:

```text
PENDING -> FALSE_POSITIVE            (terminal)
PENDING -> CONFIRMED -> RESOLVED     (terminal)
```

Any other transition is rejected with a `ValidationError`. Review never
changes `risk_score` or `status`: the score states what was detected, not
what was concluded.

A re-scan replaces a scan's findings but carries forward the review state of
any finding that reappears identically, matched on (detector, rule, matched
value), so triage survives a rule change.

### What one scan run covers

`POST /api/v1/content-security/scans/` takes a `scan_type` that selects the
coverage. It defaults to `OBJECT`, so a request that names only a
`content_type` and an `object_id` means what it always did.

| `scan_type` | Covers | Required | Rejected |
|---|---|---|---|
| `OBJECT` (default) | One object | `content_type`, `object_id` | - |
| `CONTENT_TYPE` | Every object of one content type | `content_type` | `object_id` |
| `ALL` | Every supported content type | - | `content_type`, `object_id`, `field_names` |

`field_names` stays optional for `OBJECT` and `CONTENT_TYPE` and narrows the
scan to a subset of that content type's scannable fields.

The list of supported content types belongs to the backend
(`services/content_sources.py`); an `ALL` request never sends it, so a
content type added there is covered without a client change. A field that
has no meaning for the requested `scan_type` is rejected with a
`ValidationError` rather than ignored.

An `OBJECT` run embeds its results in the response's `scans`. A
`CONTENT_TYPE` or `ALL` run is unbounded, so it answers with its counters
and an empty `scans`; its results are read back from the paginated scan
list. All three run inside the request; a catalogue large enough to outlast
a request timeout is still the `scan_content` management command's job.
Scan records, findings, statuses and re-scan behaviour are identical
whichever coverage produced them.

### The scanner never modifies content

The scanner detects and reports. It does not delete, rewrite, sanitise,
strip HTML, replace URLs, unpublish, or deactivate any product or category,
and it makes no network request for any URL it finds. Domain rules are
evaluated against locally configured rows only. Sanitisation and
remediation are a separate future feature.

### Scanner version

`content_security_api.constants.SCANNER_VERSION` (currently `1.0`) is stored
on every scan. Increment it deliberately when detection behaviour changes,
so stale results can be identified and re-scanned.

## API Request Logging

Owned by `request_log_api`. Full specification:
[api-request-logging-plan.md](api-request-logging-plan.md).

### Every request is one record

`RequestLogMiddleware` writes exactly one `RequestLog` per HTTP request.
Requests are never deduplicated: ten calls to the same endpoint produce ten
records. Successful requests, validation failures, authentication failures,
permission failures, 404s, 5xx responses and unhandled exceptions are all
logged.

`REQUEST_LOG_EXCLUDED_PATH_PREFIXES` (default `/static/`, `/media/`) is the
only exemption, and `REQUEST_LOG_ENABLED=False` switches logging off
entirely.

### Logging never affects the API

Request logging is a best-effort secondary operation. Capture, build and
persistence are each wrapped; a failure is written to the
`request_log_api` logger and swallowed. A logging failure never changes a
status code, a response body or a business outcome, and no business logic
reads a request log.

### Logs are immutable

Records are created by the middleware only. `POST`, `PUT`, `PATCH` and
`DELETE` on `/api/v1/request-logs/` answer 405, and the Django admin
disables add, change and delete. Retention and cleanup are a controlled
operational process, not an API action.

### Sensitive data is never stored

Sanitization is centralised in
`request_log_api/services/sanitizer.py` and applied automatically to request
payloads, response payloads, query parameters, multipart form fields,
captured headers, structured error details and tracebacks. It is recursive,
so a secret nested inside a list inside an object is still redacted, and a
redacted value is replaced with `***REDACTED***` rather than removed.

Individual endpoints are never responsible for declaring what is sensitive.

`Authorization`, `Cookie` and API key headers are not on the captured header
allow-list, so they are never read into a log record at all. Uploaded file
contents are never stored: a multipart request is recorded by field name,
filename, content type and size only.

### Request logs and audit logs are separate

API request logs answer "who called which API, with what request, and what
happened". They are not entity audit logs and do not record before/after
field values. The two systems stay separate and may later be correlated
through `request_id`.

### The forwarded address is not trusted by default

`REQUEST_LOG_TRUSTED_PROXY_COUNT` defaults to `0`: `X-Forwarded-For` is
recorded as reported but `REMOTE_ADDR` is the client address. A deployment
behind a load balancer or reverse proxy must set the count to the number of
proxies it actually runs, and the client address is then read that many
entries from the right of the chain.

### Outcome classification

The HTTP status code is the source of truth; `outcome` is derived from it
for filtering and aggregation:

| Condition | `outcome` |
|---|---|
| status < 400 | `SUCCESS` |
| 400 ≤ status < 500 | `CLIENT_ERROR` |
| status ≥ 500 | `SERVER_ERROR` |
| unhandled exception reached the middleware | `EXCEPTION` |

`EXCEPTION` is narrower than `SERVER_ERROR`: it means an exception type and
traceback were captured alongside the 500.

---

## Blog

### Publication lifecycle

- A blog post is **always created as `DRAFT`**, whatever the request body
  says. `status` and `published_at` are not writable through the create or
  update serializers.
- Going live is a domain operation, not a field write:
  `POST /api/v1/blog/posts/{id}/publish/` sets `status` to `PUBLISHED` and
  stamps `published_at`; `POST /api/v1/blog/posts/{id}/unpublish/` returns
  the post to `DRAFT` and clears `published_at`. Republishing stamps a new
  date.
- Publishing an already-published post, or unpublishing a draft, is
  rejected with a 400.
- Editing a post never changes its publication state — a published post
  stays published and keeps its original `published_at`.
- A database check constraint keeps the two fields consistent: `PUBLISHED`
  implies a `published_at`, `DRAFT` implies none.

### Public visibility

Blog reading is public. An anonymous caller — and any authenticated caller
without `blog_api.view_blogpost` — sees **published, non-deleted posts
only**, on both list and detail. The restriction is applied to the queryset
before filtering, so `?status=DRAFT` and every other filter search within
the published set and can never surface a draft or a soft-deleted post.

### Content

- `content` holds HTML and is stored verbatim; the blog owns no markup
  format.
- The slug is generated from the title on creation and is immutable
  afterwards, matching `Product`, `Category` and `Brand` (SEO safety). A
  client-supplied slug is ignored.
- The featured image is optional.
- SEO metadata (`seo_title`, `seo_description`, `seo_focus_keyword`,
  `seo_noindex`, `seo_nofollow`) lives on the post; there is no separate
  SEO record.
- Categories reuse the shared `Category` tree; a post may have several
  categories and several tags.
- Deleting a post or a tag is a soft delete.

### Blog tags

- A tag name is unique, case-insensitively, across tags.
- The slug is generated from the name on creation and immutable
  afterwards; renaming a tag does not move its slug.
- `legacy_id` is migration-owned and is not accepted by the API.

## Sitemap

`GET /api/v1/seo/sitemap-urls/` (`meta_api`) is public, read-only and
unpaginated. It returns `products`, `categories`, `brands` and `blogs`,
each always present as a list of `{slug, lastmod}`:

- **Products** — active and not soft-deleted; `lastmod` is `updated_at`.
- **Categories** — active, not soft-deleted, non-empty slug; `lastmod` is
  `updated_at`.
- **Brands** — active, not soft-deleted, non-empty slug; `lastmod` is
  `updated_at`.
- **Blog posts** — active, published, not soft-deleted, `seo_noindex`
  false, non-empty slug; `lastmod` is `published_at`.

"Not soft-deleted" means `deleted_at` is null. Timestamps are ISO 8601 in
UTC. The storefront builds the URLs from the slugs.

## CMS (Phase 1 — global sections)

`cms_api.CmsSection` is a Wagtail snippet holding one content block whose
type matches its immutable `section_type`. Architecture:
[cms-architecture.md](cms-architecture.md).

- **Create never implies publish.** A new section is a draft
  (`live=False`); `status` is not writable through CRUD. Publishing is
  `POST /api/v1/cms/sections/{id}/publish/` behind
  `publish_cms_section`.
- **`section_type` is immutable** after creation. `content` must hold
  exactly one block of that type; unknown types and multi-block content
  are rejected with 400.
- **Optimistic locking.** A write carrying `base_revision_id` that is not
  the section's latest revision is rejected with 409
  (`revision_conflict`).
- **Unpublish** (`unpublish_cms_section`) hides the section without
  deleting it; unpublishing a draft is a 400.
- **Archive** (`archive_cms_section`) sets `archived_at` and excludes the
  section from the default listing (`?archived=true` lists archived
  ones). There is no unarchive in Phase 1. Archiving twice is a 400.
- **Delete is soft** (`delete_cmssection`) and dependency-guarded: while
  any other object references the section (Wagtail `ReferenceIndex`),
  deletion is refused with 400. The references are listed at
  `.../{id}/references/`.
- **Rollback** restores an older revision's content as a *new* revision
  and publishes it (audit trail stays intact). It is gated by
  `publish_cms_section`, matching its publish effect.
- **Section-type schemas** are read from
  `GET /api/v1/cms/section-types/` (authenticated, no model permission);
  the type registry is code-owned, not admin-defined.

## CMS (Phase 2 — pages)

`cms_api.CmsPage` is a Wagtail page composed of ordered
`CmsPageSection` rows. Architecture:
[cms-architecture.md](cms-architecture.md).

- **Create never implies publish.** A new page is a draft
  (`live=False`). Publishing is `POST /api/v1/cms/pages/{id}/publish/`
  behind `publish_cms_page`; unpublish and archive/restore have their
  own permissions. Rollback restores an old revision and publishes it
  as a new one, gated by `publish_cms_page`.
- **Templates seed, never constrain.** `template_key` is code-owned
  (`cms_api/pages/templates.py`) and only seeds the initial
  composition; sending both `template_key` and `sections` is a 400.
- **Reserved paths.** A slug that would land on a `CMS_RESERVED_PATHS`
  storefront route is rejected with 400 on create and update.
- **Composition XOR.** Each row is either a link to a global
  `CmsSection` or exactly one local content block — never both, never
  neither. Removing a row never deletes the referenced section, and
  every composition write snapshots a page revision.
- **Optimistic locking.** A write carrying `base_revision_id` that is
  not the page's latest revision is rejected with 409
  (`revision_conflict`).
- **Dependency-guarded delete** (`delete_cmspage`): a page with child
  pages is refused with 400 listing them; deleting the subtree requires
  `?acknowledge=true`.
- **Public reads are draft-isolated.**
  `GET /api/v1/cms/public/pages/?path=` serves published pages only:
  content comes from the published revision, and rows referencing
  unpublished or archived global sections are omitted.

## CMS (Phase 3 — scheduling, redirects, preview, sitemap)

Architecture: [cms-architecture.md](cms-architecture.md), §12 (scheduling),
§9 (redirects/sitemap), §5.7/AD-15 (preview).

- **Scheduling is publish-only.** `go_live_at`/`expire_at` are accepted
  only on `POST .../publish/` (pages and sections), never on
  create/update — `expire_at` is read straight off the live row by the
  sweep, so exposing it on an update endpoint would let a
  `change_cmspage`/`change_cmssection` holder silently schedule an
  unpublish without the `unpublish_cms_page`/`unpublish_cms_section`
  permission. Setting either writes the field and snapshots a new
  revision before publishing it; they cannot be combined with
  `revision_id`. `expire_at` must be in the future and after
  `go_live_at` when both are given.
- **The sweep** is the `cms-publish-scheduled` Celery Beat task (every
  5 minutes; see [deployment.md](deployment.md)), which runs Wagtail's
  own `publish_scheduled` command: it publishes due `go_live_at`
  revisions and unpublishes live content whose `expire_at` has passed,
  for both `CmsPage` and `CmsSection`.
- **A stale past `expire_at` is cleared on republish.** A revision
  whose embedded `expire_at` has since fallen into the past (e.g. the
  object already auto-expired once) is re-snapshotted with `expire_at`
  cleared before it is republished, so the very next sweep does not
  expire it again immediately.
- **Slug-change redirects** are created only at publish time —
  `publish_page`, `rollback_page` and the scheduled sweep all create
  one when a page's published path changes, and the same is done for
  every live descendant whose published path moves with it. A redirect
  always targets the page itself, resolved at lookup time, so every
  historical path collapses directly to the page's *current* canonical
  URL with no transitive chains; renaming back to an earlier slug
  drops the now-stale redirect instead of creating a loop. Wagtail's
  own `WAGTAILREDIRECTS_AUTO_CREATE` signal handler, which would
  otherwise create a redirect on every draft-only slug edit, is
  disabled in settings for exactly this reason.
  `GET /api/v1/cms/redirects/resolve/?path=` (public) resolves an old
  path to the current one, 404 if there is none or the target page is
  no longer live/archived. `GET /api/v1/cms/redirects/` (history) is
  gated on `view_cmspage` — `Redirect` belongs to
  `wagtail.contrib.redirects`, not `cms_api`, so it has no custom
  codename of its own, and redirects only ever exist as a byproduct of
  a CMS page's slug changing. An existing redirect is not a tracked
  `ReferenceIndex` reference, so it never blocks a page's
  dependency-guarded delete.
- **Preview tokens** (pages and sections): `POST
  .../{id}/preview-token/` (gated by `change_cmspage`/
  `change_cmssection`) issues a signed, 30-minute token scoped to one
  object and one specific revision, bound to the issuing user.
  `GET /api/v1/cms/public/preview/{token}/` (public — the token itself
  carries the binding) resolves it, re-checking the signature, the
  revision and that the same user still holds the edit permission, and
  returns the *previewed revision's* content — draft or not — with
  `Cache-Control: no-store`. Nested global sections inside a
  previewed page still resolve to their own published content; preview
  is scoped to the one previewed object, not to drafts of anything it
  references.
- **Sitemap** (`GET /api/v1/cms/public/sitemap/`, public) lists live,
  non-archived pages whose *published* `seo_noindex` is false. The
  published value, not the row's, is used for exactly the same reason
  public reads use the published revision for composition: a draft
  edit writes the field straight to the row before any publish.

## CMS (Phase 4A — navigation)

`cms_api.CmsNavigationMenu`/`CmsNavigationItem` are plain Django
models (no Wagtail revisions). Architecture:
[cms-architecture.md](cms-architecture.md).

- **One permission for everything.** `manage_cms_navigation` gates
  every menu and item operation — create, read, update, delete,
  reorder — not the usual add/view/change/delete split. The model's
  own auto-generated codenames (`add_cmsnavigationmenu`, etc.) grant
  nothing on their own.
- **`is_active` is the soft-delete flag, not a separate toggle.**
  `DELETE /api/v1/cms/navigation/{id}/` soft-deletes a menu
  (`is_active=False`), which also removes it from every read —
  management or public. The write serializers never expose
  `is_active` directly (a `PATCH` setting it is accepted but has no
  effect), so there is exactly one path that deactivates a menu.
  There is no restore action.
- **Items are an ordered, nestable tree per menu.** `label`,
  `link_type` (`PAGE`/`EXTERNAL`), and exactly one of `page`/
  `external_url` matching it (database `CheckConstraint`, re-checked
  in `clean()` and the write serializers). `parent` must belong to
  the same menu and cannot create a cycle (a descendant cannot become
  an ancestor of itself). `external_url` only accepts `http`/`https`.
  Switching `link_type` on an update requires explicitly providing the
  new target *and* clearing the old one in the same request — a
  partial update never silently clears a field it no longer needs.
  Deleting a parent item cascades to its children.
- **Public reads are draft-isolated and prune by subtree.**
  `GET /api/v1/cms/public/navigation/{key}/` 404s for an unknown or
  inactive menu key. An invisible item (`is_visible=False`) prunes
  its *entire* subtree (not just itself), and a `PAGE` item whose
  target is not live or is archived is omitted — the same rule every
  other public CMS endpoint enforces. Not cached (Phase 5).
- **`delete_page` is guarded against navigation references.** A
  `CmsPage` referenced by a `CmsNavigationItem` can never be deleted
  (the FK is `PROTECT`): unlike child pages and `ReferenceIndex`
  references, this dependency is **not** acknowledgeable —
  `?acknowledge=true` still returns 400 while any navigation item
  points at the page. The item must be removed or repointed first.

## CMS (Phase 4B — media)

`cms_api.CmsMediaConfig` is a singleton controlling upload limits for
Wagtail's own `Image`/`Document` models (no custom model). Architecture:
[cms-architecture.md](cms-architecture.md).

- **Exactly one `CmsMediaConfig` row can ever exist.** `save()` always
  writes to a fixed primary key, and a database `CheckConstraint`
  rejects any other row even if something bypasses `save()`.
  `get_solo()` is the only way code should read it — it creates the
  row with its defaults on first access.
- **One permission for everything.** `manage_cms_media` gates the
  config endpoint and both media resources alike.
- **Wagtail's own upload limits do not apply here.** They live only in
  Wagtail's admin *form fields*, never in `Image`/`Document.
  full_clean()` or a DRF serializer. Every limit is read from
  `CmsMediaConfig.get_solo()` instead, never from `WAGTAILIMAGES_*`/
  `WAGTAILDOCS_*` settings (none of which this project sets).
- **Upload validation never trusts the browser.** Images: size →
  allowed-extension check → a real Pillow decode (not just the
  filename) → the decoded format must match the claimed extension →
  pixel-count limit. Documents: size → allowed-extension check (no
  decode attempted). The `content_type` the browser sends is never
  the basis for a decision.
- **`alt_text` is `Image.description`, renamed, not a new field.**
  `title` is Wagtail's native field on both `Image` and `Document`,
  defaulting to the uploaded filename when omitted. `Document` has no
  description/alt-text equivalent.
- **Media is two resources.** `GET/POST/PATCH/DELETE
  /api/v1/cms/media/images/` and `.../media/documents/` — not one
  combined endpoint. There is no public read for either; media
  management is authenticated-only.
- **Delete is reference-guarded, never acknowledgeable.** A referenced
  image or document (via Wagtail's `ReferenceIndex`, the same
  mechanism `delete_section` uses) cannot be deleted; there is no
  `acknowledge` override, unlike the page delete guard.

## Permissions

Protected endpoints require authentication.

Existing permission patterns should be reused.

### Custom model permissions

Some actions require a dedicated permission on top of authentication.

User (`user_api.User`):

- `change_user_email`
- `change_user_username`
- `change_user_password`
- `assign_user_role`
- `remove_user_role`

Category (`category_api.Category`):

- `mark_category_as_menu` - required by `POST /api/v1/categories/{id}/mark-as-menu/`
- `remove_category_from_menu` - required by `POST /api/v1/categories/{id}/remove-from-menu/`

Menu visibility of a single category can only be changed by a user holding
the matching permission. Holding one of the two permissions does not grant
the other. Superusers hold every permission implicitly.

The remaining category endpoints, including `bulk-menu-update`, keep
requiring authentication only.

Content Security (`content_security_api`):

- `run_content_scan` (on `ContentScan`) - required by
  `POST /api/v1/content-security/scans/` and
  `POST /api/v1/content-security/scans/{id}/rescan/`
- `review_content_scan_finding` (on `ContentScanFinding`) - required by
  `POST /api/v1/content-security/findings/{id}/review/`
- `resolve_content_scan_finding` (on `ContentScanFinding`) - required by
  `POST /api/v1/content-security/findings/{id}/resolve/`

Request Logs (`request_log_api.RequestLog`):

- `view_requestlog` (Django's own) - required by
  `GET /api/v1/request-logs/` and `GET /api/v1/request-logs/{id}/`
- `view_request_log_request_payload` - reveals `request_body` and
  `form_fields` on the detail response
- `view_request_log_response_payload` - reveals `response_body`
- `view_request_log_error_details` - reveals `error_details`
- `view_request_log_traceback` - reveals `traceback`

The four payload permissions are additive on top of `view_requestlog`.
Basic access shows the technical picture - endpoint, route pattern, status,
duration, timestamp, user, error message and exception type - and omits the
payload fields entirely rather than blanking them, so a withheld payload
cannot be mistaken for an empty one.

Blog (`blog_api.BlogPost`):

- `publish_blog_post` - required by
  `POST /api/v1/blog/posts/{id}/publish/`
- `unpublish_blog_post` - required by
  `POST /api/v1/blog/posts/{id}/unpublish/`

The blog is driven by Django model permissions through
`ModelPermissionAccess`, so view, add, change and delete are granted
independently, and the two publication permissions are independent of all of
them and of each other. A user holding `add_blogpost` can therefore write
posts without being able to put them live — which is why creating always
produces a draft. Publishing does not require `view_blogpost`: a publisher
reaches the draft through the publish endpoint itself, while `view_blogpost`
is what lets a caller *browse* drafts. Reading published posts and blog tags
needs no permission at all.

The rule-management endpoints (`keyword-rules`, `domain-rules`,
`html-tag-rules`, `html-attribute-rules`, `redirect-rules`,
`hidden-content-rules`, `obfuscation-rules`) are driven entirely by Django
model permissions through `ModelPermissionAccess`, so a role can be given
control of one rule type without the others. Reading scans and findings
requires authentication only. Nothing in this app is publicly readable.

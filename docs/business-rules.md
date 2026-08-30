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

The rule-management endpoints (`keyword-rules`, `domain-rules`,
`html-tag-rules`, `html-attribute-rules`, `redirect-rules`,
`hidden-content-rules`, `obfuscation-rules`) are driven entirely by Django
model permissions through `ModelPermissionAccess`, so a role can be given
control of one rule type without the others. Reading scans and findings
requires authentication only. Nothing in this app is publicly readable.

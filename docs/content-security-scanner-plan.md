# Content Security Scanner — Implementation Plan

## 1. Purpose

The Content Security Scanner is intended to detect potentially suspicious, malicious, injected, inappropriate, or SEO-spam content that may exist in data migrated from the previous WordPress platform.

The initial WordPress platform was exposed to attacks that could inject content or redirect visitors to inappropriate websites such as gambling or adult platforms. The scanner is therefore primarily a **migration-security and content-integrity system**, but it should be designed so it can become a reusable security layer for the ecommerce platform.

The scanner must not rely on a fixed hardcoded definition of "suspicious content."

Instead:

> **Detection rules must be configurable so authorized users can add, modify, enable, disable, and remove rules without changing application code.**

---

# 2. Current Scope

The current system does not have SEO content or blogs.

Therefore, the initial scanner scope is limited to:

## Product

Scan:

- `description`
- `short_description`
- `specifications`

## Category

Scan:

- `description`

Do not implement SEO/blog-specific scanning until those content types actually exist.

However, the architecture must allow additional content types and fields to be added later without redesigning the scanner.

---

# 3. High-Level Architecture

```text
                    Content
                       |
                       v
                Normalization
                       |
                       v
               Detection Engine
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
     Keywords       Domains        HTML/etc.
        |              |              |
        +--------------+--------------+
                       |
                       v
                   Findings
                       |
                       v
                  Risk Scoring
                       |
          +------------+------------+
          |            |            |
          v            v            v
        Clean        Review      High Risk
                       |
                       v
                  Admin Review
```

The backend is responsible for all scanning, detection, scoring, persistence, APIs, permissions, and batch processing.

The frontend is responsible for the admin dashboard, result visualization, rule management UI, and human review actions.

---

# 4. Backend Responsibilities

The backend should provide:

- Content scanning engine.
- Content normalization.
- Detection rules.
- Detection rule management.
- Individual detectors.
- Risk scoring.
- Scan-result persistence.
- Finding persistence.
- Batch/full scanning.
- Scan APIs.
- Finding APIs.
- Rule-management APIs.
- Review/resolution APIs.
- Permissions.
- Audit/history where appropriate.
- Tests and performance safeguards.

The backend must remain the source of truth for whether content has findings and how those findings are classified.

The frontend must not independently decide whether content is suspicious.

---

# 5. Frontend Responsibilities

The admin frontend should provide:

- Content Security dashboard.
- Scan-result listing.
- Filtering and sorting.
- Finding details.
- Content preview.
- Matched-content highlighting.
- Review actions.
- Rescan actions.
- Rule management UI.
- Permission-based visibility/actions.
- Scan progress/status UI when asynchronous scanning is introduced.

The frontend should consume the backend scanner APIs rather than implementing its own detection logic.

---

# 6. What Does "Suspicious" Mean?

Suspicious content should be treated as content containing patterns that may indicate:

- Malicious injection.
- Inappropriate content.
- Gambling/adult/drug-related spam.
- SEO spam.
- Malicious external links.
- Redirect injections.
- Dangerous HTML.
- Dangerous HTML attributes.
- Hidden content.
- Obfuscated content.
- Script injection.
- Other content-integrity anomalies.

A finding is **not automatically proof of malicious content**.

For example, a legitimate sentence may contain a word that is also present in a suspicious-keyword rule.

Therefore:

```text
Detection
    |
    v
Finding
    |
    v
Risk Assessment
    |
    v
Human Review when necessary
```

The initial system must favor detection and review over destructive automatic remediation.

---

# 7. Detection System

The scanner should be modular.

Conceptually:

```text
Scanner
├── Keyword Detector
├── Domain Detector
├── Dangerous HTML Detector
├── Dangerous Attribute Detector
├── Redirect Detector
├── Hidden Content Detector
└── Obfuscation Detector
```

Each detector should return structured findings.

The scanner should not become one large function containing all detection logic.

---

# 8. Detector: Suspicious Keywords

The system should support configurable keyword and phrase rules.

Examples of possible categories:

- Gambling
- Adult
- Drugs
- Scam
- Malware
- Spam
- Phishing
- Other inappropriate categories

These are initial examples, not a final mandatory list.

A keyword rule should conceptually contain:

```text
Keyword Rule
├── keyword/pattern
├── category
├── severity
├── enabled
└── description
```

Example:

```text
Keyword: casino
Category: Gambling
Severity: HIGH
Enabled: true
```

Authorized users should be able to add new keywords without code changes.

The system should eventually support both:

- Individual words.
- Phrases/patterns.

Regex support may be considered, but must be implemented carefully because poorly designed regular expressions can cause performance problems.

---

# 9. Detector: Suspicious Domains

The scanner should extract URLs/domains from content and compare them against configurable domain rules.

Examples:

```html
<a href="https://example.com">
```

or:

```text
https://example.com/path
```

A domain rule should conceptually contain:

```text
Domain Rule
├── domain/pattern
├── category
├── severity
├── enabled
└── description
```

The system should eventually support:

- Exact domain matching.
- Subdomain matching.
- Domain patterns/wildcards where appropriate.

Authorized users should be able to add, modify, enable, disable, and remove domain rules.

---

# 10. Detector: Dangerous HTML

The scanner should detect potentially dangerous HTML elements.

Initial candidates include:

```html
<script>
<iframe>
<object>
<embed>
<form>
```

Additional tags may be added later.

The system should distinguish between:

- Allowed HTML.
- Suspicious HTML.
- Dangerous HTML.

The scanner should not automatically classify every HTML element as malicious.

HTML tag rules should be configurable where practical.

---

# 11. Detector: Dangerous HTML Attributes

Detect potentially dangerous attributes such as:

```text
onclick
onload
onerror
onmouseover
onfocus
onmouseenter
```

Also detect dangerous values/patterns such as:

```text
javascript:
data:text/html
```

A configurable rule should allow authorized users to add or disable dangerous attributes/patterns.

---

# 12. Detector: Redirect Mechanisms

Because the previous WordPress platform experienced redirect attacks, redirect detection is a high-priority detector.

Potential mechanisms include:

```javascript
window.location
location.href
location.replace()
location.assign()
window.open()
```

and HTML-based redirects such as:

```html
<meta http-equiv="refresh">
```

Additional redirect patterns may be added later.

These findings should generally have high severity, subject to the approved severity configuration.

---

# 13. Detector: Hidden Content

The scanner should detect suspicious techniques used to hide injected content.

Examples include:

```text
display:none
visibility:hidden
font-size:0
```

and potentially:

```text
position:absolute
left:-9999px
```

Hidden content is not automatically malicious.

The detector should generate a finding and allow risk assessment/human review.

---

# 14. Detector: Obfuscation

The scanner should detect suspicious attempts to hide content or code.

Potential areas include:

- HTML entities.
- Encoded URLs.
- Unicode obfuscation.
- Escaped JavaScript.
- Base64-like payloads.
- Encoded script fragments.

A normalization pipeline should be considered:

```text
Raw Content
    |
    v
HTML Normalization
    |
    v
Entity Decoding
    |
    v
URL Normalization
    |
    v
Unicode Normalization
    |
    v
Detection
```

Normalization must be carefully controlled to avoid excessive false positives or processing overhead.

---

# 15. Structured Findings

Every detector should produce structured findings.

Conceptually:

```text
Finding
├── detector
├── rule
├── severity
├── matched_value
├── message
└── metadata
```

Example:

```json
{
  "detector": "keyword",
  "rule": "gambling-casino",
  "severity": "high",
  "matched_value": "casino",
  "message": "Suspicious keyword detected."
}
```

This information will be consumed by the admin UI.

---

# 16. Risk Scoring

The system should have two separate concepts:

## Finding Severity

Potential levels:

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

## Overall Content Risk

Potential statuses:

```text
CLEAN
LOW_RISK
REVIEW
HIGH_RISK
CRITICAL
```

The overall risk score should be calculated from the findings.

Example scoring concept:

```text
Low severity       +10
Medium severity    +25
High severity      +50
Critical           +80
```

These values are examples only.

The final scoring formula and thresholds must be explicitly decided before implementation and should not be silently invented by an implementation agent.

The final score should be capped at an appropriate maximum, such as 100, if that model is selected.

---

# 17. False Positive Handling

False positives are expected.

Example:

```text
"This product has a casino-style design."
```

A keyword rule may detect:

```text
casino
```

but the content may still be legitimate.

Therefore the system must support:

```text
Detected
    |
    v
Review
    |
    +--> Safe / False Positive
    |
    +--> Confirmed Suspicious
```

The scanner should not automatically delete or rewrite content merely because a rule matched.

---

# 18. Persistence

The scanner should persist scan results.

## ContentScan

Conceptually:

```text
ContentScan
├── content_type
├── object_id
├── field_name
├── status
├── risk_score
├── scanner_version
├── scanned_at
└── ...
```

Example:

```text
content_type = product
object_id = 1250
field_name = description
risk_score = 87
status = HIGH_RISK
```

## ContentScanFinding

Conceptually:

```text
ContentScanFinding
├── scan
├── detector
├── rule
├── severity
├── matched_value
├── message
├── metadata
└── ...
```

One scan may have multiple findings.

---

# 19. Configurable Rule Management

Detection rules must be manageable as data rather than only as Python constants.

Potential logical rule types:

```text
Keyword Rule
Domain Rule
HTML Tag Rule
HTML Attribute Rule
Redirect Rule
Hidden Content Rule
Obfuscation Rule
```

Common rule properties may include:

```text
enabled
severity
category
description
```

The exact database design should be determined after inspecting existing project conventions.

The implementation should avoid creating an unnecessarily generic rule engine if separate rule types provide clearer behavior.

---

# 20. Rule Categories

Rules should be categorized to make them easier to manage and report.

Potential categories:

```text
GAMBLING
ADULT
DRUG
MALWARE
SCAM
SPAM
PHISHING
REDIRECT
INJECTION
OBFUSCATION
```

The final category list should be approved before implementation.

---

# 21. Initial Rule Set

The initial deployment should include a baseline set of rules for:

- Common suspicious keywords.
- Common suspicious domains/patterns where known.
- Dangerous HTML elements.
- Dangerous HTML attributes.
- Common redirect mechanisms.
- Common hidden-content patterns.
- Initial obfuscation indicators.

The baseline should be treated as configurable initial data rather than immutable application logic.

---

# 22. Scan Modes

The system should support multiple scanning scopes.

## Full Scan

Scan all currently supported content:

```text
Products
Categories
```

## Entity Scan

Scan a specific object:

```text
Product #123
Category #45
```

## Field Scan

Scan a specific field:

```text
Product #123 → description
```

## Future: Changed Content Scan

Only scan content that changed since its previous successful scan.

---

# 23. Migration Scan

The primary initial use case is scanning migrated WordPress data.

Recommended workflow:

```text
WordPress Data
      |
      v
Migration
      |
      v
New Database
      |
      v
Full Content Scan
      |
      +--> Clean
      |
      +--> Review
      |
      +--> High Risk
      |
      v
Admin Review
      |
      v
Resolution
      |
      v
Re-scan
```

The backend should support batch scanning.

A management command is a suitable initial mechanism if the project does not already have background processing infrastructure.

Example conceptual command:

```text
python manage.py scan_content
```

Future options may include:

```text
scan_content --type product
scan_content --type category
scan_content --all
```

Exact command design should follow project conventions.

---

# 24. Background Processing — Future

If full scanning becomes expensive as the platform grows, introduce asynchronous processing using the platform's established task infrastructure.

Future workflow:

```text
Admin
  |
  v
Start Scan
  |
  v
Background Job
  |
  v
Progress
  |
  v
Results
```

Do not introduce a task queue solely for this feature if the current dataset and infrastructure do not justify it.

---

# 25. Backend API

The backend should eventually expose APIs for:

## Scan Results

```text
GET /api/v1/content-security/scans/
GET /api/v1/content-security/scans/{id}/
```

## Findings

```text
GET /api/v1/content-security/findings/
```

## Start Scan

Conceptually:

```text
POST /api/v1/content-security/scans/
```

## Review

Conceptually:

```text
POST /api/v1/content-security/findings/{id}/review/
```

## Rule Management

Conceptually:

```text
/api/v1/content-security/keyword-rules/
/api/v1/content-security/domain-rules/
/api/v1/content-security/html-tag-rules/
/api/v1/content-security/html-attribute-rules/
```

Exact URLs, HTTP methods, serializers, and API structure must follow the existing backend conventions.

---

# 26. Permissions

Because this is a security-related administrative feature, access must be permission-controlled.

Potential permissions:

```text
content_security.view_scan
content_security.run_scan
content_security.review_scan
content_security.manage_rules
content_security.resolve_finding
```

These are examples.

The final permission names and structure must follow the existing permission system.

---

# 27. Frontend — Content Security Dashboard

Create an admin section conceptually like:

```text
Admin
└── Content Security
```

Dashboard should provide a high-level overview:

```text
Total Scanned
Clean
Needs Review
High Risk
Critical
```

This should make the state of migrated content immediately visible.

---

# 28. Frontend — Scan Results

Provide a searchable/filterable table.

Example:

```text
Type       Object       Field             Risk      Status
Product    #1250       description         92       High Risk
Product    #1820       specifications      68       Review
Category   #52         description          81       High Risk
```

Potential filters:

```text
Content Type
Status
Severity
Detector
Rule Category
Risk Score
Scan Date
```

Use existing admin table/filter/pagination patterns.

---

# 29. Frontend — Finding Details

Finding details should open in a modal or detail view following the existing admin UI pattern.

Show:

- Content type.
- Object identifier/name.
- Field.
- Risk score.
- Overall status.
- Detector.
- Rule.
- Severity.
- Matched value.
- Explanation.
- Relevant metadata.
- Scan timestamp.

Example:

```text
Product #1250
Description

Risk Score: 92
Status: High Risk

Findings
────────────────────────

Redirect mechanism
window.location.replace(...)

Suspicious domain
example.com

Suspicious keyword
casino
```

---

# 30. Frontend — Content Preview and Highlighting

The UI should show the content that triggered the finding.

Where practical:

```text
Original Content

This product description contains
[casino]
and an external URL:
[suspicious-domain.com]
```

The backend must provide the finding/match information.

The frontend should not implement its own security detection engine.

---

# 31. Frontend — Rule Management

Provide an administrative configuration area conceptually like:

```text
Content Security
├── Scan Results
├── Keywords
├── Domains
├── Dangerous HTML
├── Dangerous Attributes
├── Redirect Rules
└── ...
```

For example:

```text
Keyword        Category       Severity     Enabled
casino         Gambling       High         Yes
betting        Gambling       High         Yes
example.com    Gambling       Critical     Yes
```

Authorized users should be able to:

- Add.
- Edit.
- Enable/disable.
- Delete.

The exact capabilities should follow backend permissions.

---

# 32. Frontend — Review Actions

Authorized users should be able to:

- Mark as safe.
- Confirm suspicious.
- Resolve.
- Rescan.

Do not automatically delete or rewrite content as part of the initial scanner UI.

---

# 33. Scanner vs Sanitizer

Scanning and sanitization must remain separate concerns.

## Scanner

Answers:

> "Does this content contain something suspicious?"

## Sanitizer

Answers:

> "What unsafe markup/content should be removed or transformed?"

Initial architecture:

```text
Content
  |
  v
Scanner
  |
  v
Finding
  |
  v
Human Review
  |
  v
Manual Edit / Future Sanitizer
```

Automatic sanitization can be introduced later.

---

# 34. Testing Strategy

The backend should have tests for:

## Keyword Detection

- Keyword found.
- Keyword not found.
- Case handling.
- Phrase detection.
- Disabled rule.
- Multiple matches.

## Domain Detection

- Suspicious domain found.
- Allowed domain.
- Subdomain behavior.
- Multiple URLs.
- Disabled rule.

## HTML Detection

- Dangerous tag found.
- Safe tag ignored.
- Multiple dangerous tags.

## Attribute Detection

- Dangerous attribute found.
- Safe attribute ignored.

## Redirect Detection

- JavaScript redirect detected.
- Meta refresh detected.
- Safe content not flagged.

## Hidden Content

- Hidden pattern detected.
- Legitimate content does not generate excessive false positives.

## Obfuscation

- Supported encoded pattern detected.
- Normal content remains unaffected.

## Scoring

- Correct finding severity.
- Correct cumulative score.
- Correct status threshold.
- Maximum score behavior.

## API

- Authentication.
- Permissions.
- Filtering.
- Pagination.
- Review actions.
- Rule management.

## Batch Scan

- Product scan.
- Category scan.
- Full scan.
- Re-scan behavior.

---

# 35. Performance Requirements

The scanner must be designed with potentially large ecommerce datasets in mind.

Avoid:

- N+1 queries.
- Loading unnecessary model fields.
- Repeatedly compiling the same patterns.
- Running expensive operations unnecessarily.
- Scanning the same unchanged content repeatedly.

Use:

- Efficient queryset access.
- Batch processing.
- Reusable compiled patterns where appropriate.
- Incremental/changed-content scanning in the future.

The scanner should be measurable so performance can be evaluated before enabling full production scans.

---

# 36. Scanner Versioning

Store a scanner version with scan results.

Example:

```text
scanner_version = 1.0
```

This is important because rules and detectors will evolve.

If a new detector or rule set is introduced:

```text
Scanner v1
    |
    v2
    |
    v3
```

we can identify which results were generated by which scanner version and decide when old content needs to be rescanned.

---

# 37. Audit History — Future/Recommended

For security-related administrative actions, maintain an audit trail.

Track:

- Who reviewed a finding.
- When it was reviewed.
- Previous status.
- New status.
- Which rule triggered it.
- What action was taken.
- Who modified a rule.
- When a rule was enabled/disabled/deleted.

This is particularly useful for a reusable multi-business ecommerce platform.

---

# 38. Future Content Types

When the platform introduces these features, extend the scanner to:

```text
Blogs
SEO metadata
Static pages
Landing pages
Brands
Collections
Reviews
Product attributes
Product variants
Comments
User-generated content
```

The scanner architecture should allow these to be registered without changing the core detection engine.

---

# 39. Future Detection Capabilities

Potential future detectors include:

- Suspicious image URLs.
- Malicious file URLs.
- External JavaScript.
- External CSS.
- Tracking injections.
- Hidden links.
- SEO poisoning.
- Phishing patterns.
- Malware indicators.
- More advanced encoded payload detection.
- Suspicious Unicode.
- Base64 payload detection.
- Suspicious iframe sources.
- External resource injection.

---

# 40. Future Domain Intelligence

The configurable domain system can eventually support:

- Allowlist.
- Blocklist.
- Wildcard domains.
- Subdomain matching.
- Suspicious TLD rules.
- Domain reputation.
- External threat-intelligence providers.
- Domain-age/reputation checks where appropriate.

External threat-intelligence integration should be treated as an optional future capability rather than a requirement for the initial implementation.

---

# 41. Future Automatic Scanning

Eventually, content can be scanned automatically whenever it changes:

```text
Product Updated
      |
      v
Content Scanner
      |
      v
Risk Assessment
      |
      +--> Clean
      |
      +--> Review
      |
      +--> High Risk
```

The same pattern can be applied to categories, blogs, SEO, and future content types.

---

# 42. Future API Protection

The scanner can eventually become part of content-write workflows.

Example:

```text
Admin/API submits content
        |
        v
Validation
        |
        v
Content Security Scanner
        |
        +--> Accept
        |
        +--> Flag
        |
        +--> Reject (only for clearly defined critical cases)
```

Automatic rejection should only be introduced for highly deterministic rules with an acceptable false-positive rate.

---

# 43. Future Sanitization

A separate sanitization subsystem can eventually provide:

- HTML sanitization.
- Dangerous tag removal.
- Dangerous attribute removal.
- Script removal.
- Unsafe URL removal.
- Safe HTML normalization.

Potential workflow:

```text
Finding
   |
   v
Recommended Remediation
   |
   v
Admin Approval
   |
   v
Sanitizer
   |
   v
Updated Content
   |
   v
Re-scan
```

---

# 44. Future CI/CD and Migration Validation

The scanner can eventually be used before deployment or migration completion.

Potential workflow:

```text
Migration Data
      |
      v
Scanner
      |
      v
Security Report
      |
      v
Approval
      |
      v
Production Deployment
```

This can help prevent known suspicious content from reaching production.

---

# 45. Recommended Implementation Order

## Phase 1 — Discovery and decisions

- [ ] Confirm current content fields.
- [ ] Confirm detector categories.
- [ ] Define severity levels.
- [ ] Define risk statuses.
- [ ] Define scoring model.
- [ ] Define review workflow.
- [ ] Define rule-management permissions.

## Phase 2 — Backend foundation

- [ ] Create scanner module/app following existing project conventions.
- [ ] Create `ContentScan`.
- [ ] Create `ContentScanFinding`.
- [ ] Design configurable rule storage.
- [ ] Implement normalization pipeline.
- [ ] Implement scanner service.

## Phase 3 — Detection

- [ ] Keyword detector.
- [ ] Domain detector.
- [ ] Dangerous HTML detector.
- [ ] Dangerous attribute detector.
- [ ] Redirect detector.
- [ ] Hidden-content detector.
- [ ] Obfuscation detector.

## Phase 4 — Risk assessment

- [ ] Finding severity.
- [ ] Risk scoring.
- [ ] Overall status.
- [ ] False-positive/review workflow.

## Phase 5 — Migration scanning

- [ ] Product scanning.
- [ ] Category scanning.
- [ ] Full scan.
- [ ] Batch processing.
- [ ] Scan report.
- [ ] Re-scan capability.

## Phase 6 — Backend APIs

- [ ] Scan-result API.
- [ ] Finding API.
- [ ] Rule APIs.
- [ ] Review APIs.
- [ ] Permissions.
- [ ] API tests.

## Phase 7 — Admin frontend

- [ ] Content Security dashboard.
- [ ] Scan-result table.
- [ ] Filters.
- [ ] Finding details.
- [ ] Content preview.
- [ ] Match highlighting.
- [ ] Review actions.
- [ ] Rescan action.
- [ ] Rule management.
- [ ] Permission-based UI.

## Phase 8 — Hardening

- [ ] Complete detector tests.
- [ ] API tests.
- [ ] Performance tests.
- [ ] False-positive review.
- [ ] Scanner versioning.
- [ ] Audit history.

## Phase 9 — Future expansion

- [ ] SEO scanning.
- [ ] Blog scanning.
- [ ] Additional content types.
- [ ] Automatic scanning on content changes.
- [ ] Background scanning.
- [ ] Sanitization.
- [ ] Threat intelligence.
- [ ] CI/CD/migration scanning.

---

# 46. Core Design Principles

The implementation should follow these principles:

1. **Configurable rules over hardcoded rules.**
2. **Detection is not the same as maliciousness.**
3. **Scanner and sanitizer are separate systems.**
4. **Backend is the security source of truth.**
5. **Frontend is for visibility and human review.**
6. **Do not automatically destroy suspicious content initially.**
7. **Every finding should explain why it was detected.**
8. **Rules must be manageable without code deployment.**
9. **The scanner must be extensible to new content types.**
10. **The system must support re-scanning when rules or scanner versions change.**
11. **Performance must be considered from the beginning.**
12. **Security-related administrative actions should eventually be auditable.**

---

# 47. Final Target Architecture

```text
                         CONTENT
                            |
                            v
                     NORMALIZATION
                            |
                            v
                    CONTENT SCANNER
                            |
       +--------------------+--------------------+
       |          |         |         |          |
       v          v         v         v          v
   Keywords    Domains    HTML     Redirect   Obfuscation
       |          |         |         |          |
       +----------+---------+---------+----------+
                            |
                            v
                         FINDINGS
                            |
                            v
                      RISK SCORING
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
            CLEAN         REVIEW      HIGH RISK
                            |
                            v
                     ADMIN DASHBOARD
                            |
                 +----------+----------+
                 |                     |
                 v                     v
             Review                  Rules
                 |                     |
                 v                     v
             Resolve              Configure
                 |                     |
                 +----------+----------+
                            |
                            v
                         RE-SCAN
```

This design gives the platform a **small, useful first version for the current Product/Category migration data**, while providing a clear path toward a general-purpose content-security layer for the entire reusable ecommerce platform.

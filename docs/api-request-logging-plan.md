# API Request Logging, Analytics & Observability System

## 1. Overview

This document defines the plan for implementing a comprehensive API Request Logging, Analytics, and Observability system for the e-commerce platform.

The purpose of this system is to record the lifecycle of **every HTTP request** received by the backend application.

Each API request should generate an independent log record containing relevant information about:

* Who made the request
* Whether the requester was authenticated
* Anonymous/client identity
* IP address
* User-Agent
* Browser, operating system, and device information
* Request method and URL
* API route pattern
* Query parameters
* Request payload
* Multipart/form-data information
* Uploaded file metadata
* Response status
* Response payload
* Request and response size
* Response time
* Errors
* Exceptions
* Tracebacks
* Future IP-based location information
* Future bot/client analysis

The system should support multiple use cases simultaneously:

1. API debugging
2. Error investigation
3. Performance monitoring
4. Security investigation
5. User activity analysis
6. API usage analytics
7. Bot detection
8. Operational monitoring
9. Admin reporting
10. Future observability and analytics infrastructure

This system is conceptually similar to a combination of:

* API access logging
* Application observability
* Error monitoring
* Performance monitoring
* Activity analytics

It is **not intended to replace entity/database audit logging**. API request logs and entity audit logs should remain separate systems.

---

# 2. Primary Objective

The primary objective is:

> Create one immutable log record for every HTTP request without affecting the normal API request/response lifecycle.

The system should observe the request but must not interfere with it.

If logging fails:

```text
Actual API Request
        │
        ▼
Business Logic Executes
        │
        ▼
API Response Returns Successfully
        │
        ▼
Logging Fails
        │
        ▼
API Response Must NOT Be Affected
```

Logging must always be considered a best-effort secondary operation.

---

# 3. Scope

The system should log all HTTP requests, including:

* Successful requests
* Validation failures
* Authentication failures
* Permission failures
* Not Found responses
* Rate-limited requests
* Client errors
* Server errors
* Unhandled exceptions
* Multipart requests
* Anonymous requests
* Authenticated requests
* Repeated requests to the same endpoint

For example, if the same user calls:

```text
GET /api/products/10/
```

ten times, ten independent request log records must be created.

Logs should represent individual request events.

The system should not deduplicate requests.

---

# 4. Request Lifecycle

The conceptual request lifecycle should be:

```text
                         HTTP REQUEST
                              │
                              ▼
                  Request Logging Middleware
                              │
                              ▼
                    Generate Request ID
                    or Reuse Existing ID
                              │
                              ▼
                   Capture Request Context
                              │
                              ├── User
                              ├── IP
                              ├── User-Agent
                              ├── Request Metadata
                              ├── Query Parameters
                              ├── Request Payload
                              └── Start Timer
                              │
                              ▼
                      Application Processing
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
                 Response            Exception
                    │                   │
                    └─────────┬─────────┘
                              │
                              ▼
                    Capture Final Context
                              │
                              ├── Status Code
                              ├── Response Payload
                              ├── Response Size
                              ├── Duration
                              ├── Error Information
                              └── Traceback
                              │
                              ▼
                  Sensitive Data Sanitization
                              │
                              ▼
                      Build Log Event
                              │
                              ▼
                  Non-Blocking Persistence
                              │
                              ▼
                       Request Log Storage
```

---

# 5. Core Principles

The system must follow the following principles.

## 5.1 Every Request Is Logged

Every HTTP request should create an independent event.

No deduplication should occur.

---

## 5.2 Logging Must Not Affect API Performance

The request log persistence process should not block the actual API response.

The API must not fail because:

* The request logging system fails
* The log database is temporarily unavailable
* Payload parsing fails
* User-Agent parsing fails
* Location enrichment fails
* Any analytics-related process fails

---

## 5.3 Logs Are Immutable

After creation, request logs should not be editable through normal APIs.

Normal operations should not support:

```text
PATCH RequestLog
PUT RequestLog
```

Deletion should not normally be available either.

Future retention or cleanup operations can be handled through controlled processes.

---

## 5.4 Sensitive Data Must Never Be Stored

The logging system must sanitize sensitive information before persistence.

This must be centralized and automatic.

Individual API endpoints should not be responsible for remembering which values to remove.

---

## 5.5 API Request Logging and Audit Logging Are Separate

API Request Logging answers:

> Who called which API, with what request, and what happened?

Audit Logging answers:

> What data changed, and what were the values before and after the change?

Example API request:

```text
PATCH /api/products/10/
```

Request body:

```json
{
    "price": 1200
}
```

A future audit record may contain:

```json
{
    "field": "price",
    "before": 1000,
    "after": 1200
}
```

These should remain separate systems.

They may later be connected through `request_id`.

---

# 6. Request Identity and Correlation

Every request should have a globally unique request identifier.

Recommended field:

```text
request_id
```

Request ID behavior:

```text
Client sends X-Request-ID
          │
          ▼
    Is it valid?
          │
     ┌────┴────┐
     │         │
    Yes        No
     │         │
     ▼         ▼
Reuse ID   Generate New ID
```

The request ID should also be returned to the client:

```text
X-Request-ID: <request_id>
```

The request ID can later support:

* Support investigations
* Error debugging
* Correlation with internal logs
* Correlation with background tasks
* Correlation with future services
* Distributed tracing

---

# 7. User and Identity Information

The request log should support both authenticated and anonymous requests.

Recommended information:

```text
user
is_authenticated
anonymous_id
```

## Authenticated Request

Example:

```text
user_id = 123
is_authenticated = true
anonymous_id = optional client identifier
```

## Anonymous Request

Example:

```text
user_id = null
is_authenticated = false
anonymous_id = frontend/client identifier
```

The relationship with the user model should be nullable.

The request logging process must not fail if:

* Authentication fails
* No user is available
* A user has been deleted
* A user relation cannot be resolved

The recommended relationship behavior is conceptually:

```text
ForeignKey(User)
nullable
on_delete = SET_NULL
```

The actual request log must remain valid even if the associated user no longer exists.

---

# 8. Anonymous Client Identity

IP address and User-Agent alone are not sufficient to reliably identify an anonymous visitor.

The system should support:

```text
anonymous_id
```

The frontend can generate and persist a UUID-like identifier.

Example:

```text
Browser Installation
        │
        ▼
Generate Anonymous Identifier
        │
        ▼
Persist Locally
        │
        ▼
Send With API Requests
```

For example:

```text
X-Anonymous-ID: <identifier>
```

This enables analytics such as:

```text
Anonymous Visitor
        │
        ├── Browse Products
        ├── Search
        ├── View Product
        ├── Add to Cart
        │
        ▼
       Login
        │
        ▼
Authenticated User
```

The anonymous identifier and authenticated user relationship can coexist in the request log.

---

# 9. Network Information

Initially, store:

```text
ip_address
```

Potentially preserve relevant forwarded address information if required by the deployment architecture.

The implementation must correctly consider:

```text
Client
   │
   ▼
Load Balancer
   │
   ▼
Reverse Proxy
   │
   ▼
Application
```

The application must not blindly trust spoofable forwarded headers.

A trusted proxy strategy should be defined according to the production infrastructure.

---

# 10. Future Location Enrichment

Location should not be resolved during the API request lifecycle.

Instead:

```text
Request
   │
   ▼
Store IP Address
   │
   ▼
Return API Response
   │
   ▼
Future Background Enrichment
   │
   ▼
Resolve Approximate Location
```

Future enrichment fields may include:

```text
country
country_code
region
city
area
timezone
latitude
longitude
```

IP geolocation should be considered approximate.

The enrichment process must not affect normal API performance.

---

# 11. Client and Device Information

The system should store both raw and parsed User-Agent information.

## Raw

```text
user_agent
```

## Parsed

```text
browser
browser_version

operating_system
operating_system_version

device_type
device_brand
device_model

is_mobile

is_bot
bot_name
bot_category
bot_confidence
```

The raw User-Agent must remain available because parsing technology may improve later.

Historical User-Agent values can then be reprocessed.

---

# 12. Bot Detection

The system should support future bot detection.

Recommended fields:

```text
is_bot
bot_name
bot_category
bot_confidence
```

Initially, some of these values may remain unknown.

The system should preserve raw request information so bot detection can be improved or reprocessed later.

---

# 13. Client Application Information

The system should support identifying the client consuming the API.

Potential values:

```text
WEB
MOBILE
ADMIN
EXTERNAL
UNKNOWN
```

Recommended field:

```text
client_type
```

This information should preferably come from an explicit client identifier/header rather than unreliable automatic inference.

If no information is available:

```text
client_type = UNKNOWN
```

---

# 14. Frontend Page and Source Tracking

To support analytics-like behavior, the system should support:

```text
origin
referer
frontend_route
```

The frontend may explicitly provide:

```text
X-Client-Route
```

Example:

```text
/products/nike-shoes
```

This can later answer questions such as:

* Which frontend pages generate the most API traffic?
* Which frontend pages generate the most errors?
* Which pages trigger slow API requests?

Frontend route information should remain optional.

---

# 15. Request Routing Information

The system should store both the actual request path and the API route pattern.

Recommended fields:

```text
request_method
request_path
route_pattern
```

Example:

```text
request_method:

GET
```

Actual path:

```text
/api/products/123/
```

Route pattern:

```text
/api/products/{id}/
```

Both are important.

The actual path is useful for investigating a specific request.

The route pattern is useful for analytics and aggregation.

---

# 16. Query Parameters

Query parameters should be recorded.

Recommended storage:

```text
query_parameters
query_string
```

Structured storage should be preferred for analysis.

Example:

```json
{
    "category": "10",
    "page": "2",
    "search": "iphone"
}
```

Query parameters must pass through sensitive-data sanitization.

---

# 17. Request Headers

The system should not blindly store every HTTP header.

Only selected useful headers should be captured.

Potential examples:

```text
Content-Type
Accept
Accept-Language
Origin
Referer
```

The following must never be stored:

```text
Authorization
Cookie
Set-Cookie
API Keys
Tokens
Secrets
```

The raw User-Agent should remain in its own dedicated field.

---

# 18. JSON Request Payload

For JSON requests, the request payload should be stored after sanitization.

Example:

```json
{
    "name": "Product",
    "price": 100
}
```

Sensitive values must be redacted.

Example input:

```json
{
    "email": "user@example.com",
    "password": "secret"
}
```

Stored value:

```json
{
    "email": "user@example.com",
    "password": "***REDACTED***"
}
```

Sanitization must work recursively.

Example:

```json
{
    "user": {
        "password": "secret"
    }
}
```

Must also be sanitized.

---

# 19. Multipart/Form-Data Requests

Actual uploaded file contents must never be stored in request logs.

For multipart requests, store:

## Form Fields

Example:

```json
{
    "name": "Nike Shoe",
    "brand_id": "10"
}
```

## File Metadata

Example:

```json
[
    {
        "field_name": "image",
        "filename": "shoe.jpg",
        "content_type": "image/jpeg",
        "size_bytes": 245678
    }
]
```

Additional fields:

```text
is_multipart
file_count
total_file_size_bytes
```

This provides useful observability without storing binary files.

---

# 20. Request Size

Store:

```text
request_size_bytes
```

This can later support analysis of:

* Large requests
* Bandwidth-heavy endpoints
* Unusual client behavior
* Excessive payload sizes

---

# 21. Response Information

Store:

```text
status_code
response_body
response_size_bytes
```

The complete response should be stored whenever possible.

Response payloads must also pass through sensitive-data sanitization.

The architecture should support a configurable maximum response size as a safety mechanism, even if the initial configuration allows large responses.

This avoids permanently coupling the system to unlimited database storage.

---

# 22. Response Headers

Response headers are not required in Version 1.

They should not be stored unless a future use case requires selected response header tracking.

---

# 23. Performance Information

Each request should capture:

```text
started_at
completed_at
duration_ms
```

This enables future analysis of:

* Slow requests
* Slow endpoints
* Average response time
* Performance trends
* P95 response time
* P99 response time

The system should record the total application request lifecycle duration.

---

# 24. Request Outcome

The request log should contain both the HTTP status code and a derived outcome classification.

Recommended fields:

```text
status_code
is_success
outcome
```

Recommended outcomes:

```text
SUCCESS
CLIENT_ERROR
SERVER_ERROR
EXCEPTION
```

Future outcomes may include:

```text
TIMEOUT
CANCELLED
RATE_LIMITED
```

The HTTP status code remains the source of truth.

Derived outcomes make filtering and analytics easier.

---

# 25. Error Information

When an error occurs, store:

```text
error_message
exception_type
traceback
error_details
```

`error_details` may contain structured information such as validation errors.

Example:

```json
{
    "email": [
        "This field is required."
    ]
}
```

Tracebacks should be:

* Sanitized
* Stored separately
* Subject to configurable size limits

Successful requests should contain null error fields.

Example:

```text
error_message = null
exception_type = null
traceback = null
error_details = null
```

Each request should remain represented by one primary lifecycle record.

---

# 26. Sensitive Data Sanitization

Sensitive data sanitization is a critical centralized component.

The logging middleware must not directly persist raw request or response data.

Instead:

```text
Raw Data
   │
   ▼
Sanitization Layer
   │
   ▼
Safe Log Payload
   │
   ▼
Persistence
```

Sensitive keys should be configurable.

Examples:

```text
password
password_confirmation
current_password
new_password

access_token
refresh_token
token

authorization

api_key
secret
secret_key

card_number
cvv
```

Sanitization should apply to:

* Request payload
* Response payload
* Query parameters
* Multipart fields
* Error context
* Structured exception data

Sanitization should work recursively.

---

# 27. Recommended Internal Architecture

The logging system should be separated into logical components.

Conceptually:

```text
Middleware
    │
    ▼
Request Context Collector
    │
    ▼
Request Log Builder
    │
    ▼
Sensitive Data Sanitizer
    │
    ▼
Request Log Publisher
    │
    ▼
Request Log Storage
```

This separation is important because the storage backend will likely change in the future.

---

# 28. Middleware Responsibility

Middleware should be responsible for observing the request lifecycle.

It should:

1. Generate or read the request ID
2. Record the start time
3. Capture request metadata
4. Allow the request to proceed normally
5. Capture the response
6. Capture exceptions where possible
7. Calculate duration
8. Build a request log event
9. Send the event to the logging pipeline
10. Return the original API response

Middleware should not contain complex database logic.

---

# 29. Request Log Builder

A dedicated builder should construct a structured request log event.

Conceptually:

```text
Request
   │
   ▼
Extract Context
   │
   ├── Identity
   ├── Network
   ├── Client
   ├── Request
   ├── Performance
   └── Correlation
```

After processing:

```text
Response / Exception
   │
   ▼
Extract Final Context
   │
   ├── Status
   ├── Response
   ├── Error
   └── Duration
```

The builder should create one structured log event.

---

# 30. Non-Blocking Persistence

Logging should not block the API response.

Conceptually:

```text
API Request
    │
    ▼
Application Processing
    │
    ▼
API Response Ready
    │
    ├──────────────► Return Response
    │
    ▼
Logging Pipeline
    │
    ▼
Persist Request Log
```

The exact technical implementation may depend on the existing Django deployment architecture.

The design should allow multiple future persistence strategies.

---

# 31. Storage Abstraction

The application should avoid tightly coupling the middleware directly to PostgreSQL.

Conceptually:

```text
RequestLogStorage
       │
       ├── PostgreSQL Storage
       │
       ├── Future Queue Storage
       │
       └── Future ClickHouse Storage
```

Initial architecture:

```text
Application
    │
    ▼
PostgreSQL
```

Future architecture:

```text
Application
    │
    ▼
Queue / Event Stream
    │
    ▼
Worker
    │
    ▼
ClickHouse
```

The middleware and log-building system should require minimal changes when storage infrastructure evolves.

---

# 32. Logging Failure Strategy

The initial system should use best-effort persistence.

```text
Try Save Log
    │
    ├── Success
    │
    ▼
   Done
    │
    └── Failure
          │
          ▼
  Internal Handling
          │
          ▼
 Never Affect API Response
```

Future improvements may introduce:

* Retry logic
* Queues
* Background workers
* Dead-letter handling
* Dedicated observability infrastructure

---

# 33. Initial Database Strategy

Initially, request logs will be stored in the main PostgreSQL database.

```text
PostgreSQL
    │
    ├── Users
    ├── Products
    ├── Orders
    ├── Payments
    │
    └── Request Logs
```

The implementation must anticipate significant data growth.

Future migration to ClickHouse is expected.

The architecture should therefore avoid:

* Business logic depending directly on PostgreSQL-specific logging behavior
* Middleware containing database-specific logic
* Difficult-to-migrate tightly coupled storage structures

---

# 34. Recommended Logical Request Log Structure

The primary request log record should conceptually contain the following sections.

```text
RequestLog
│
├── Identity
│   ├── request_id
│   ├── user
│   ├── is_authenticated
│   └── anonymous_id
│
├── Network
│   ├── ip_address
│   └── forwarded information if required
│
├── Client
│   ├── user_agent
│   ├── browser
│   ├── browser_version
│   ├── operating_system
│   ├── operating_system_version
│   ├── device_type
│   ├── device_brand
│   ├── device_model
│   ├── is_mobile
│   ├── is_bot
│   ├── bot_name
│   ├── bot_category
│   └── bot_confidence
│
├── Client Source
│   ├── client_type
│   ├── origin
│   ├── referer
│   └── frontend_route
│
├── Request
│   ├── request_method
│   ├── request_path
│   ├── route_pattern
│   ├── query_parameters
│   ├── query_string
│   ├── selected_headers
│   ├── request_body
│   ├── multipart information
│   ├── file metadata
│   └── request_size_bytes
│
├── Response
│   ├── status_code
│   ├── response_body
│   └── response_size_bytes
│
├── Performance
│   ├── started_at
│   ├── completed_at
│   └── duration_ms
│
├── Outcome
│   ├── is_success
│   └── outcome
│
├── Error
│   ├── error_message
│   ├── exception_type
│   ├── traceback
│   └── error_details
│
└── Future Enrichment
    ├── country
    ├── country_code
    ├── region
    ├── city
    ├── area
    ├── timezone
    ├── latitude
    └── longitude
```

---

# 35. Filtering Requirements

The admin/frontend list should eventually support filtering by all relevant categories.

## Identity

```text
User
Authenticated
Anonymous
Anonymous ID
```

## Network

```text
IP Address
Country
Region
City
Timezone
```

## Client

```text
Browser
Operating System
Device Type
Device Brand
Is Mobile
Is Bot
Bot Name
Client Type
```

## Request

```text
HTTP Method
Actual Path
Route Pattern
Frontend Route
Origin
Query Parameters
```

## Response

```text
Status Code
Status Code Range
Success
Failure
Outcome
```

## Performance

```text
Minimum Response Time
Maximum Response Time
Slow Requests
```

## Error

```text
Has Error
Exception Type
Error Message
```

## Time

```text
Specific Date
Date Range
Hour
Created Time
```

---

# 36. Sorting

The request log list should support sorting.

Potential sorting fields:

```text
Newest
Oldest

Slowest Requests
Fastest Requests

Largest Request
Largest Response

Errors First
```

Default sorting should normally be:

```text
Newest First
```

---

# 37. Pagination

Because request logs can become extremely large, pagination is mandatory.

The system should be designed to support cursor-based pagination.

Conceptually:

```text
GET /request-logs/?cursor=<cursor>
```

Cursor pagination is preferred over deep offset pagination for large datasets.

---

# 38. Database Indexing Strategy

Indexes should be added based on real filtering and sorting requirements.

Likely important initial fields include:

```text
created_at
request_id
user
ip_address
route_pattern
status_code
outcome
duration_ms
is_authenticated
anonymous_id
```

Potential composite indexes may later include:

```text
(route_pattern, created_at)

(status_code, created_at)

(user, created_at)

(outcome, created_at)
```

The system should avoid indexing every field because excessive indexes will negatively affect write performance and database size.

Indexing should be reviewed as real usage patterns become available.

---

# 39. Permissions

Access to request logs should be permission-controlled.

Future permissions may include:

```text
Can View Request Logs

Can View Request Payload

Can View Response Payload

Can View Error Details

Can View Traceback

Can Export Request Logs
```

The API should be designed so sensitive fields can be omitted based on permission.

For example:

Basic access:

```text
Endpoint
Status
Duration
Timestamp
User
```

Technical administrator:

```text
Full Request Payload
Full Response Payload
Error Details
Traceback
```

---

# 40. Admin API

The initial frontend/admin integration should eventually support:

```text
Request Log List
        │
        ├── Pagination
        ├── Filtering
        ├── Sorting
        └── Search
```

A request log detail endpoint should provide the complete permitted information for a selected request.

Normal APIs should not allow:

```text
Create Request Log Manually
Update Request Log
Delete Request Log
```

Logs are generated by the application itself.

---

# 41. Exporting

The system should eventually support exporting filtered request logs.

Potential formats:

```text
CSV
Excel
JSON
```

Large exports should not load all records into API memory.

Future architecture:

```text
User Requests Export
        │
        ▼
Create Export Job
        │
        ▼
Background Processing
        │
        ▼
Generate File
        │
        ▼
Provide Download
```

Small exports may be handled synchronously if appropriate.

---

# 42. Reporting

Future reporting may include:

## API Usage

* Most frequently used endpoints
* Most active users
* Most active anonymous clients
* Most active IP addresses

## Performance

* Slowest endpoints
* Average response time
* Response time trends
* P95 response time
* P99 response time

## Errors

* Most common errors
* Most frequent exception types
* Endpoints generating the most errors
* Error trends over time

## Client Analytics

* Browser distribution
* Operating system distribution
* Device type distribution
* Mobile versus desktop usage
* Bot activity

## Location

After enrichment:

* Country distribution
* City distribution
* Regional traffic

---

# 43. Future ClickHouse Migration

The current PostgreSQL implementation should be treated as the initial storage layer.

As traffic and request volume increase, the architecture should support migration toward ClickHouse.

Potential future architecture:

```text
Application
    │
    ▼
Request Log Event
    │
    ▼
Queue / Event Pipeline
    │
    ▼
Worker / Consumer
    │
    ▼
ClickHouse
```

ClickHouse can later be optimized for:

* High-volume inserts
* Time-based queries
* Analytics
* Aggregations
* Large-scale reporting

The middleware should not require a major rewrite when this migration occurs.

---

# 44. Recommended Implementation Phases

## Phase 1: Foundation

Implement:

1. Request log application/module
2. Primary request log model
3. Request ID generation
4. Middleware integration
5. Request timing
6. Basic request metadata
7. User/anonymous identification
8. IP and User-Agent collection

---

## Phase 2: Payload Collection

Implement:

1. JSON request payload collection
2. Query parameter collection
3. Multipart field collection
4. File metadata collection
5. Request size calculation
6. Response payload collection
7. Response size calculation

---

## Phase 3: Security and Sanitization

Implement:

1. Centralized sensitive-data sanitization
2. Recursive JSON sanitization
3. Query parameter sanitization
4. Multipart field sanitization
5. Response sanitization
6. Sensitive header exclusion
7. Traceback sanitization

This phase should be considered critical before production usage.

---

## Phase 4: Error and Exception Tracking

Implement:

1. Status code tracking
2. Outcome classification
3. Error messages
4. Exception types
5. Structured error details
6. Tracebacks

---

## Phase 5: Client Analysis

Implement:

1. User-Agent parsing
2. Browser detection
3. Operating system detection
4. Device detection
5. Mobile detection
6. Bot detection fields

---

## Phase 6: Non-Blocking Storage

Implement the persistence abstraction and best-effort logging behavior.

The exact implementation should be selected based on the current Django deployment architecture.

Logging failures must never affect API responses.

---

## Phase 7: API Access

Implement:

1. Request log list API
2. Request log detail API
3. Filtering
4. Sorting
5. Cursor pagination
6. Search
7. Permission-based field visibility

---

## Phase 8: Exporting

Implement:

1. CSV export
2. Excel export
3. JSON export
4. Filter-aware exports
5. Future asynchronous export jobs

---

## Phase 9: Enrichment

Introduce future background processing for:

1. IP geolocation
2. Bot detection improvements
3. Client reclassification
4. Historical enrichment

---

## Phase 10: Analytics Storage Migration

When request volume becomes sufficiently large:

1. Introduce queue/event infrastructure
2. Introduce ClickHouse
3. Implement event consumers
4. Migrate analytics queries
5. Define PostgreSQL retention strategy
6. Move long-term observability data to ClickHouse

---

# 45. Important Non-Goals for the Initial System

The initial implementation should not attempt to become a complete distributed tracing system.

The following should remain future scope:

* Microservice tracing
* Full distributed tracing
* Internal service dependency graphs
* Real-time streaming analytics
* Complex event pipelines
* Real-time IP enrichment
* Real-time fraud detection

The initial system should be designed to support these possibilities without over-engineering the first version.

---

# 46. Final Architecture Principle

The most important architectural principle is:

> Capture everything useful, sanitize everything sensitive, persist without affecting the API, and design the logging pipeline so that the storage infrastructure can evolve independently.

The desired architecture is:

```text
                    HTTP Request
                         │
                         ▼
                  Logging Middleware
                         │
                         ▼
                Request Context Collection
                         │
                         ▼
                  Application Processing
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
           Response              Exception
              │                     │
              └──────────┬──────────┘
                         ▼
                 Final Context Collection
                         │
                         ▼
                 Sensitive Data Sanitization
                         │
                         ▼
                    Request Log Event
                         │
                         ▼
                  Logging Abstraction
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        PostgreSQL Now       ClickHouse Later
```

The implementation should prioritize correctness, safety, and minimal impact on the existing API architecture.

The request logging system must remain an observability layer around the application, not a dependency that the application's business logic relies upon.

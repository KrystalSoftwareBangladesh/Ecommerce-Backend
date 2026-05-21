# Architecture

## Pattern

Request

→ URL

→ View

→ Service

→ Model

→ Database

---

## Responsibilities

### Views

Responsible for:

- Request handling
- Serializer invocation
- Response generation

Should NOT contain complex business logic.

---

### Services

Responsible for:

- Business rules
- Domain operations
- Transaction management

Examples:

- Sale processing
- Purchase processing
- Inventory movement
- Accounting posting

---

### Models

Responsible for:

- Data representation
- Relationships
- Database constraints

---

### Serializers

Responsible for:

- Validation
- Data transformation

---

# Shared Core Components

Location:

ZayrahLifeBackend/core/

These components should be reused throughout the project instead of creating new implementations.

---

## Base Models

Location:

ZayrahLifeBackend/core/models.py

### TimeStampedModel

Provides:

- created_at
- updated_at

Use this model whenever timestamp tracking is required.

---

### UserStampedModel

Provides:

- created_by
- updated_by

Use this model whenever user audit tracking is required.

---

### SoftDeleteModel

Provides:

- is_active
- deleted_at

Use this model whenever soft deletion is required.

Avoid hard deletion unless explicitly requested.

---

## Search Filter

Location:

ZayrahLifeBackend/core/filter.py

Class:

SearchFilter

Use this filter for searchable list APIs.

Do not create duplicate search implementations.

---

## Pagination

Location:

ZayrahLifeBackend/core/pagination.py

Class:

Pagination

Use this pagination class for all paginated endpoints.

Do not introduce additional pagination classes unless necessary.

---

## Permissions

Location:

ZayrahLifeBackend/core/permission.py

Class:

PublicListPermissionMixin

Use this mixin for endpoints that support public listing access.

Reuse existing permission patterns before creating new permission classes.

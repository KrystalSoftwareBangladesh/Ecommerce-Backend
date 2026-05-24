# Architecture

## Pattern

Request

→ URL

→ View

→ Service

→ Model

→ Database

---

## Authentication Flow

### Public Registration (POST /auth/register/)

Request

→ RegisterView

→ CustomerSignupSerializer

→ Creates User + CustomerProfile atomically

→ Returns JWT tokens + customer data

---

## Product Domain

### Brand Management

Location:

`product_api`

Brand provides product categorization by manufacturer/brand name.

Operations:
- List Brands (public, paginated, searchable)
- Retrieve Brand detail
- Create Brand (authenticated)
- Update Brand (authenticated)
- Delete Brand (authenticated, soft delete)

Features:
- Search by name and description
- Filter by active status
- Automatic slug generation
- User audit trail (created_by, updated_by)
- Soft delete with is_active flag

---

## Category Domain

### Category Management

Location:

`category_api`

Category provides hierarchical product categorization.

Operations:
- List Categories (public, paginated, searchable)
- Retrieve Category detail
- Create Category (authenticated)
- Update Category (authenticated)
- Delete Category (authenticated, soft delete)

### Category Import Service

Location:

`category_api/services.py`

Supports bulk import from multiple file formats:

**Supported Formats:**
- JSON (`import_from_json()`)
- CSV (`import_from_csv()`)
- XLSX (`import_from_xlsx()`)

**Features:**
- Atomic transactions (all-or-nothing)
- Row-level error tracking
- Parent category resolution by ID or name
- Automatic slug generation
- User audit trail (created_by, updated_by)
- Soft delete support via is_active flag

**Endpoints:**
- `POST /categories/import-json/` - JSON file import
- `POST /categories/import-csv/` - CSV file import
- `POST /categories/import-xlsx/` - XLSX file import

**Response:**
```json
{
    "success": boolean,
    "created": integer,
    "errors": []
}
```

See [Category Import API Documentation](category-import-api.md) for detailed usage.

---

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
- Category import processing

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

EcommerceBackend/core/

These components should be reused throughout the project instead of creating new implementations.

---

## Base Models

Location:

EcommerceBackend/core/models.py

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

EcommerceBackend/core/filter.py

Class:

SearchFilter

Use this filter for searchable list APIs.

Do not create duplicate search implementations.

---

## Pagination

Location:

EcommerceBackend/core/pagination.py

Class:

Pagination

Use this pagination class for all paginated endpoints.

Do not introduce additional pagination classes unless necessary.

---

## Permissions

Location:

EcommerceBackend/core/permission.py

Class:

PublicListPermissionMixin

Use this mixin for endpoints that support public listing access.

Reuse existing permission patterns before creating new permission classes.

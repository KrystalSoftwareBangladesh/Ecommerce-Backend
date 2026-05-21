# AGENTS.md

## Project Overview

This is a Django + Django REST Framework based e-commerce backend.

Current domains:

- Users
- Products
- Categories
- Inventory
- Suppliers
- Purchases
- Sales
- Customers
- Accounting
- Transactions

The system must remain reusable and business-agnostic.

Do not introduce store-specific logic.

---

## Documentation

Before making changes, review:

- docs/architecture.md
- docs/business-rules.md
- docs/project-structure.md

These files are considered project source-of-truth documentation.

---

## Existing Architecture

Each business domain is implemented as a separate Django app.

Examples:

- product_api
- category_api
- inventory_api
- sale_api
- purchase_api
- supplier_api
- customer_api
- account_api
- transaction_api
- user_api

Reuse existing patterns before creating new ones.

---

## Application Structure

Each app should follow:

app_name/

├── models/
├── serializers/
├── views/
│   └── v1/
├── urls/
├── migrations/
├── admin.py
├── apps.py
└── tests.py

Keep consistency with neighboring apps.

---

## Development Rules

### Models

- Place models inside models/
- Add indexes where appropriate
- Use meaningful related_name values

### Serializers

- Validation belongs in serializers
- Reuse serializer patterns

### Views

- Keep views thin
- Avoid business logic in views
- Move complex logic into services.py

### URLs

- Register endpoints in urls/v1.py
- Maintain API versioning

### Services

Business logic belongs in services.py.

Examples:

- Sale processing
- Purchase processing
- Inventory updates
- Accounting operations

---

## Database Rules

- Never edit applied migrations
- Create new migrations
- Review generated migrations before committing

---

## Query Optimization

Avoid N+1 queries.

Use:

- select_related()
- prefetch_related()

---

## Testing

Every new feature should include tests.

At minimum:

- API tests
- Serializer tests
- Permission tests

---

## Documentation Maintenance

Documentation is part of development.

Whenever creating, deleting, renaming, or moving files:

1. Update docs/project-structure.md
2. Update docs/architecture.md if architecture changes
3. Update docs/business-rules.md if business rules change

A task is not complete until documentation is updated.

---

## Completion Checklist

Before finishing any task:

- [ ] Code implemented
- [ ] Tests updated
- [ ] Migrations created if needed
- [ ] URLs registered
- [ ] Admin updated if needed
- [ ] Documentation updated
- [ ] Project structure updated

---

## Search Before Creating

Before creating any new:

- model
- serializer
- view
- service
- filter
- permission
- utility

the agent must search the repository for an existing implementation.

Prefer extending existing code over creating duplicate functionality.

## Existing Shared Components

Before implementing models, filters, permissions, or pagination, review:

- EcommerceBackend/core/models.py
- EcommerceBackend/core/filter.py
- EcommerceBackend/core/pagination.py
- EcommerceBackend/core/permission.py

Prefer existing shared components over creating new implementations.

## Code Quality

flake8 is the project's source of truth for linting.

Before completing any code change:

1. Run flake8 on modified files.
2. Fix all reported issues.
3. Do not ignore linting errors unless explicitly approved.
4. Ensure newly added code follows existing project style conventions.

Example:
```bash
flake8
```
or
```bash
flake8 path/to/modified_file.py
```

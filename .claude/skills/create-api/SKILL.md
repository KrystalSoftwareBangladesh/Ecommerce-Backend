# Create API

## Checklist

1. Create serializer.
2. Create ViewSet.
3. Register URL.
4. Add SearchFilter if searching is required.
5. Add Pagination for list endpoints.
6. Apply permissions.
7. Add tests.
8. Update documentation.

## Rules

Reuse existing shared components:

Search:

- EcommerceBackend/core/filter.py
- SearchFilter

Pagination:

- EcommerceBackend/core/pagination.py
- Pagination

Permissions:

- EcommerceBackend/core/permission.py
- PublicReadPermissionMixin

Do not create duplicate implementations unless explicitly required.

## Final Verification

Before finishing:

- Run flake8
- Fix linting issues
- Execute relevant tests
- Update documentation

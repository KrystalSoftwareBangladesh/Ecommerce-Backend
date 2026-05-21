# Create Django Model

## Checklist

1. Search existing models first.
2. Determine whether model should inherit:

   - TimeStampedModel
   - UserStampedModel
   - SoftDeleteModel

3. Add indexes where appropriate.
4. Create migration.
5. Register admin.
6. Create serializer.
7. Add tests.
8. Update documentation.

## Rules

Prefer existing abstract models from:

ZayrahLifeBackend/core/models.py

Avoid duplicating:

- created_at
- updated_at
- created_by
- updated_by
- is_active
- deleted_at
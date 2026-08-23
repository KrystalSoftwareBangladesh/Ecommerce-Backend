---
name: create-model
description: Add a new Django model to an existing *_api app in this repository — choosing the right core abstract bases, Meta options, constraints, custom permissions, migration and admin registration. Use when creating any new model or adding a custom model permission.
---

# Create a model

Project conventions: [docs/conventions.md](../../../docs/conventions.md#models).
Entities and relationships: [docs/domain-model.md](../../../docs/domain-model.md).

## 1. Check it does not already exist

```bash
grep -rn "class <Name>" --include='*.py' */models*
```

15 apps already exist. Prefer extending an existing model or app over
creating a new one. A new *app* is an architectural change — ask first.

## 2. Place the file

`<app>/models/<resource>.py`, then re-export in `<app>/models/__init__.py`:

```python
from .brand import Brand

__all__ = ['Brand']
```

`customer_api` and `meta_api` use a flat `models.py`; if you are working in
those, follow their layout rather than converting them.

## 3. Choose the abstract bases

From `EcommerceBackend/core/models.py` — never redeclare these fields:

| Base | Gives you | Use when |
|---|---|---|
| `TimeStampedModel` | `created_at`, `updated_at` (indexed) | almost always |
| `UserStampedModel` | `created_by`, `updated_by` | the record is user-authored or user-owned |
| `SoftDeleteModel` | `is_active`, `deleted_at`, `soft_delete()`, `restore()` | the record is deletable through the API |
| `ModerationModel` | `status`, `approved_at`, `approved_by`, `approve()`, `reject()`, `reset_to_pending()` | the record needs approval (as `Review` does) |

The standard triple for a domain model:

```python
class Brand(TimeStampedModel, UserStampedModel, SoftDeleteModel):
```

Line-item models that only exist inside a parent (`SaleItem`,
`PurchaseItem`, `AccountingTransactionLine`) inherit `TimeStampedModel` or
nothing.

Note `Cart` and `Wishlist` express ownership through `created_by` from
`UserStampedModel` — there is no separate `user` field. Follow that if the
new model is per-user.

## 4. Fields

- Money: `DecimalField(max_digits=12, decimal_places=2)` — never `FloatField`.
- Choices: a `models.TextChoices` class in the same module, or
  `IntegerChoices` in `EcommerceBackend/core/choices.py` if more than one app
  needs it. If the enum will surface in more than one serializer, add it to
  `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]` in
  `EcommerceBackend/settings.py`.
- Every FK gets an explicit `related_name`. Use `PROTECT` for ledger
  references (`InventoryMovement.product_variant`), `CASCADE` for
  parent-owned lines, `SET_NULL` for optional lookups.
- Slug: `SlugField(max_length=255, unique=True)` plus the repository's
  generate-on-create pattern:

```python
def save(self, *args, **kwargs):
    if not self.pk and not self.slug:
        self.slug = self._generate_unique_slug()
    super().save(*args, **kwargs)
```

  Copy `_generate_unique_slug()` from `product_api/models/product.py`.
  Slugs are not regenerated on rename — that is deliberate (SEO safety).
- Uploads: `upload_to="<plural>/<kind>/"`, matching `brands/logos/` and
  `products/images/`.

## 5. Meta

Always set `verbose_name`, `verbose_name_plural`, `ordering`, and `indexes`
for anything filtered or ordered on. Add `constraints` for real invariants —
the repo uses partial unique constraints, e.g. one default image per product
and one active cart per user:

```python
class Meta:
    verbose_name = 'Brand'
    verbose_name_plural = 'Brands'
    ordering = ['display_order', 'name']
    indexes = [models.Index(fields=['name'])]
    constraints = [
        models.UniqueConstraint(
            fields=['product'],
            condition=models.Q(is_default=True, is_active=True),
            name='product_image_single_default_per_product',
        ),
    ]
```

`db_table` is set explicitly on only four models. Match the app you are in.

## 6. Custom model permissions

If an action needs its own permission beyond add/change/delete/view:

```python
class Meta:
    permissions = [
        ("mark_category_as_menu", "Can mark category as menu"),
    ]
```

This requires its own migration, and is consumed via `custom_permissions` —
see the `add-viewset-action` skill.

## 7. Migration

```bash
python manage.py makemigrations <app>
```

Read the generated file before committing. **Never edit an applied
migration** — add a new one.

## 8. Register in admin

```python
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
```

## 9. Finish

```bash
flake8 <app>
python manage.py test <app> --settings=EcommerceBackend.test_settings
```

Then update [docs/project-structure.md](../../../docs/project-structure.md)
and [docs/domain-model.md](../../../docs/domain-model.md).

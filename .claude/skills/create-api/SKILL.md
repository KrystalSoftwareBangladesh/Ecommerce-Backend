---
name: create-api
description: Add a new REST resource to this repository — serializers, ViewSet, router registration under /api/v1/, permissions, filtering and OpenAPI tags, following the conventions already used across the 15 *_api apps. Use when exposing a model over the API or creating a new endpoint set.
---

# Create an API resource

Conventions: [docs/api-conventions.md](../../../docs/api-conventions.md) ·
[docs/conventions.md](../../../docs/conventions.md).
Workflow order is mandatory for new features — see
[AGENTS.md](../../../AGENTS.md#implementation-workflow).

Before writing anything, open the equivalent files in a neighbouring app.
`product_api/views/v1/brand.py` is the cleanest small example;
`account_api/views/v1/chart_of_account.py` is the cleanest example that uses
a service.

## 1. Service first (new features)

Put the domain operation in `<app>/services.py` (or `<app>/services/<x>.py`
if the app uses a package). Module-level function, `@transaction.atomic` on
the public entry point, raise
`rest_framework.exceptions.ValidationError` for rule violations, return the
instance. See the `accounting-operation` skill for money/stock operations.

Thin CRUD in an app that has no service module (`origin_api`,
`supplier_api`) can stay as-is — match the app you are in.

## 2. Serializers

`<app>/serializers/<resource>.py`, re-exported from `__init__.py` with
`__all__`. Three classes is the norm:

```python
class BrandListSerializer(serializers.ModelSerializer):     # lean, for list
class BrandDetailSerializer(serializers.ModelSerializer):   # expanded, for retrieve
class BrandCreateUpdateSerializer(serializers.ModelSerializer):  # writes
```

- Nested reads use a summary serializer (`UserSummarySerializer`,
  `CategorySummarySerializer`), not the full detail serializer.
- `read_only_fields` for `created_by`, `updated_by`, timestamps, slug and
  any generated identifier.
- Field rules in `validate_<field>()`, cross-field rules in `validate()`.
  Rules that depend on persisted state belong in the service.
- For an action that does not return a model, write a response-only
  `serializers.Serializer` so the schema stays accurate — see
  `CategoryStatisticsSerializer`.

## 3. ViewSet

`<app>/views/v1/<resource>.py`, re-exported from `views/v1/__init__.py`.

```python
@extend_schema(tags=["Brands"])
class BrandViewSet(PublicReadPermissionMixin, viewsets.ModelViewSet):
    queryset = Brand.objects.filter(deleted_at__isnull=True)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['display_order', 'name', 'created_at', 'id']
    ordering = ['display_order', 'id']

    def get_serializer_class(self):
        if self.action == 'list':
            return BrandListSerializer
        elif self.action == 'retrieve':
            return BrandDetailSerializer
        return BrandCreateUpdateSerializer
```

- `SearchFilter` and `OrderingFilter` come from `rest_framework.filters`.
  `EcommerceBackend/core/filter.py` is **empty** — there is no shared filter
  class.
- Pagination is global (`EcommerceBackend.core.pagination.Pagination`); do
  not set `pagination_class` unless you are opting out with `None`.
- Narrow the queryset per action in `get_queryset()` and add
  `select_related` / `prefetch_related` there — not in the serializer.
- File uploads: add
  `parser_classes = [MultiPartParser, FormParser]`.

## 4. Permissions

Preferred for new endpoints
([why](../../../docs/conventions.md#permissions)):

- Storefront-readable → `PublicReadPermissionMixin`; extend
  `public_actions` for extra public actions.
- Everything else → `IsAuthenticated` (also the global default).
- Per-action permission → `CustomPermissionAccessMixin` (see the
  `add-viewset-action` skill).

Do not define a new permission class inside a view module.

## 5. Soft delete

If the model inherits `SoftDeleteModel`, override `destroy()`:

```python
def destroy(self, request, *args, **kwargs):
    instance = self.get_object()
    instance.updated_by = request.user
    instance.save(update_fields=['updated_by', 'updated_at'])
    instance.soft_delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
```

Then filter the queryset with `deleted_at__isnull=True`.

## 6. Register the route

`<app>/urls/v1.py`:

```python
router = DefaultRouter()
router.register(r'brands', v1.BrandViewSet, basename='brand')

urlpatterns = []
urlpatterns += router.urls
```

`<app>/urls/__init__.py` already mounts `v1/`. If this is a brand-new app,
also add it to `LOCAL_APPS` in `EcommerceBackend/settings.py` and to
`EcommerceBackend/all_urls.py` — a new app is an architectural change, so
confirm it first.

Paths are plural and kebab-cased. The endpoint lands at `/api/v1/brands/`.

## 7. OpenAPI

Every view module in this repo carries `@extend_schema(tags=[...])` — keep it
at 100%. Reuse an existing tag from
[docs/api-conventions.md](../../../docs/api-conventions.md#openapi--drf-spectacular)
rather than inventing a near-duplicate.

## 8. Tests

Best effort ([docs/testing.md](../../../docs/testing.md)). If you add them,
match the existing style: `APITestCase`, `force_authenticate`, hardcoded
`/api/v1/...` URLs, fixtures built in `setUp()`.

## 9. Finish

```bash
flake8
python manage.py test <app> --settings=EcommerceBackend.test_settings
```

Verify the route and schema:

```bash
python manage.py spectacular --file /tmp/schema.yaml --settings=EcommerceBackend.test_settings
```

Then update [docs/project-structure.md](../../../docs/project-structure.md),
and [docs/domain-model.md](../../../docs/domain-model.md) if models changed.

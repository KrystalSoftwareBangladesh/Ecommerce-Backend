---
name: add-viewset-action
description: Add a custom @action endpoint to an existing ViewSet in this repository — url_path, drf-spectacular schema, pagination opt-out, and an optional dedicated model permission wired through CustomPermissionAccessMixin. Use when adding a non-CRUD endpoint such as mark-as-menu, confirm, post, set-default or a bulk update.
---

# Add a custom ViewSet action

This is the most common unit of work in this repository — most recent issues
were exactly this shape (`mark-as-menu`, `remove-from-menu`,
`bulk-menu-update`, `reorder`, `path`, `summary`, `confirm`, `cancel`,
`post`, `set-default`, `replace-image`).

Reference implementations:
`category_api/views/v1/category.py`, `purchase_api/views/v1/purchase.py`,
`product_api/views/v1/product_image.py`.

## 1. Decide where the logic goes

For a **new feature**, the operation belongs in the app's service module and
the action calls it — see
[AGENTS.md](../../../AGENTS.md#implementation-workflow). Existing
`category_api` actions hold their logic inline; that is grandfathered, not a
pattern to copy into a new app.

## 2. Write the action

```python
@extend_schema(
    tags=["Categories"],
    parameters=[CATEGORY_LOOKUP_PARAMETER],
    request=None,
    responses={200: CategoryDetailsSerializer},
    description="Mark a category to be shown in the navigation menu.",
)
@action(
    detail=True,
    methods=["post"],
    url_path="mark-as-menu",
)
def mark_as_menu(self, request, id=None):
    ...
```

- `url_path` is kebab-case; the method name is snake_case. The route becomes
  `/api/v1/categories/{id}/mark-as-menu/`.
- The signature's keyword argument must match the ViewSet's
  `lookup_url_kwarg` — `id` in `category_api` and `product_api`, `pk`
  everywhere else.
- Repeat `tags` on the action's `@extend_schema`; the class-level decorator
  does not always carry through.
- `request=None` for actions with no body. Declare a real serializer in
  `responses` — write a response-only `serializers.Serializer` if the shape
  is not a model (`CategoryStatisticsSerializer`,
  `CategoryBulkMenuUpdateResponseSerializer`).
- Non-body inputs get `OpenApiParameter`. When the same parameter repeats,
  hoist it to a module-level constant, as `CATEGORY_LOOKUP_PARAMETER` and
  `PRODUCT_LOOKUP_PARAMETER` do.
- Opt out of list machinery where it does not apply:
  `@action(..., filter_backends=[], pagination_class=None)`.
- Paginate a list-shaped action explicitly:

```python
page = self.paginate_queryset(queryset)
if page is not None:
    serializer = XSerializer(page, many=True, context=self.get_serializer_context())
    return self.get_paginated_response(serializer.data)
```

- Return the serializer body directly. Do not add a
  `{"success": ..., "message": ...}` envelope — only six `user_api` actions
  do that, and it is not the convention. Errors are shaped globally by
  `EcommerceBackend.core.exceptions.custom_exception_handler`; just raise
  `ValidationError` / `NotFound` / `PermissionDenied`.

## 3. Make the action public (if it should be)

`PublicReadPermissionMixin` makes only `list` and `retrieve` public. Extend
it:

```python
public_actions = PublicReadPermissionMixin.public_actions + [
    "roots", "children", "path",
]
```

## 4. Give the action its own permission (if it needs one)

Three steps, all required:

1. Declare the codename on the model:

```python
class Meta:
    permissions = [
        ("mark_category_as_menu", "Can mark category as menu"),
    ]
```

2. Generate and commit the migration:

```bash
python manage.py makemigrations category_api
```

3. Wire it on the ViewSet with `CustomPermissionAccessMixin`, which applies
   `ModelPermissionAccess` **only** to the mapped actions and leaves every
   other endpoint's permissions untouched:

```python
class CategoryViewSet(
    CustomPermissionAccessMixin,
    PublicReadPermissionMixin,
    viewsets.ModelViewSet,
):
    permission_classes = [IsAuthenticated]
    custom_permissions = {
        "mark_as_menu": "mark_category_as_menu",
        "remove_from_menu": "remove_category_from_menu",
    }
```

The codename is resolved against the app label of the ViewSet's queryset
model, so `get_queryset()` must return a real queryset. Holding one custom
permission never implies another. Superusers hold all of them.

Use `ModelPermissionAccess` directly (not the mixin) only when the **whole**
ViewSet should be model-permission driven, as in `user_api`.

## 5. Mutating state

- Wrap multi-row changes in `transaction.atomic`.
- Save narrowly and include the audit fields:

```python
category.updated_by = request.user
category.save(update_fields=["show_in_menu", "updated_by", "updated_at"])
```

- Use `F()` expressions for sibling re-indexing rather than a Python loop —
  see `CategoryViewSet.reorder`.

## 6. Finish

```bash
flake8 <app>
python manage.py test <app> --settings=EcommerceBackend.test_settings
python manage.py spectacular --file /tmp/schema.yaml --settings=EcommerceBackend.test_settings
```

Then document the endpoint and, if it introduced a permission rule, add it to
[docs/business-rules.md](../../../docs/business-rules.md#custom-model-permissions).

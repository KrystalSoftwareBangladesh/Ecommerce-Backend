# EcommerceBackend/core/schema.py
"""drf-spectacular schema generation hooks."""


def exclude_wagtail_admin_api(endpoints, **kwargs):
    """Drop Wagtail's internal admin API from the generated schema.

    ``wagtail.admin.urls`` (mounted at ``/cms-admin/``) ships its own
    admin-only API under ``/cms-admin/api/main/`` for the Wagtail admin
    UI (page/image/document choosers). It isn't part of this project's
    public API (``/api/v1/``) and isn't built as a plain DRF view, so
    drf-spectacular can't introspect it and logs errors/operationId
    collisions trying to. Excluding it here keeps the schema to what
    this project actually serves.
    """
    return [
        (path, path_regex, method, callback)
        for path, path_regex, method, callback in endpoints
        if not path.startswith("/cms-admin/")
    ]

# cms_api/backends.py
"""Authentication backend granting Wagtail Admin entry (docs/cms-
architecture.md AD-11, Phase 5A).

Wagtail Admin's own entry gate (``wagtail.admin.auth.
require_admin_access``) checks ``user.has_perms(["wagtailadmin.
access_admin"])`` — a permission with no relationship to ``is_staff``
and that nothing in this project grants. This backend grants exactly
that one permission string to active staff (or superuser) users, and
nothing else: it never authenticates a login itself (``authenticate``/
``get_user`` both return ``None``, so it never interferes with the
existing ``user_api.backends.EmailOrUsernameBackend``/``ModelBackend``
chain), and ``has_perm`` returns ``False`` for every other permission
string so it cannot grant anything beyond admin entry. Per-action
authorization inside Wagtail Admin (editing, publishing, deleting,
...) is enforced separately by ``cms_api.wagtail_permissions`` against
the existing ``cms_api`` permission codenames — this backend only
answers "can this user walk through the door".
"""

WAGTAIL_ADMIN_ACCESS_PERMISSION = "wagtailadmin.access_admin"


class WagtailAdminAccessBackend:
    def authenticate(self, request, **kwargs):
        return None

    def get_user(self, user_id):
        return None

    def has_perm(self, user_obj, perm, obj=None):
        if perm != WAGTAIL_ADMIN_ACCESS_PERMISSION:
            return False
        return bool(
            user_obj
            and user_obj.is_active
            and (user_obj.is_staff or user_obj.is_superuser)
        )

    def has_module_perms(self, user_obj, app_label):
        return False

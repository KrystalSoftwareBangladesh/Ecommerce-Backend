# user_api/views/v1/__init__.py
from user_api.views.v1.auth import (
    LoginView, LogoutView, TokenRefreshView, ChangePasswordView,
    RegisterView, PasswordResetRequestView, PasswordResetConfirmView,
)
from user_api.views.v1.user import UserProfileView
from user_api.views.v1.permission import PermissionListView
from user_api.views.v1.group import GroupViewSet
from .user import UserExistenceCheckView, UserViewSet
from .email_verification import (
    EmailVerificationRequestView, EmailVerificationConfirmView,
    EmailVerificationStatusView,
)


__all__ = [
    LoginView, LogoutView, TokenRefreshView, ChangePasswordView,
    RegisterView, PasswordResetRequestView, PasswordResetConfirmView,
    UserProfileView, PermissionListView, GroupViewSet,
    "UserExistenceCheckView", "UserViewSet", "EmailVerificationRequestView",
    'EmailVerificationConfirmView', 'EmailVerificationStatusView',
]

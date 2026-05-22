from user_api.views.v1.auth import LoginView
from user_api.views.v1.auth import LogoutView
from user_api.views.v1.auth import TokenRefreshView
from user_api.views.v1.auth import ChangePasswordView
from user_api.views.v1.auth import RegisterView
from user_api.views.v1.user import UserProfileView
from user_api.views.v1.user import UserListView
from user_api.views.v1.user import AssignGroupView
from user_api.views.v1.create import CreateUserView
from user_api.views.v1.permission import PermissionListView
from user_api.views.v1.group import GroupViewSet
from .user import UserExistenceCheckView


__all__ = [
    LoginView,
    LogoutView,
    TokenRefreshView,
    ChangePasswordView,
    RegisterView,
    UserProfileView,
    UserListView,
    AssignGroupView,
    CreateUserView,
    PermissionListView,
    GroupViewSet,
    "UserExistenceCheckView",
]

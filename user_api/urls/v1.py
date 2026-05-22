from django.urls import path
from rest_framework.routers import DefaultRouter

from user_api.views import v1


router = DefaultRouter()


# router.register('roles', v1.GroupViewSet, basename='roles')


urlpatterns = [
    path('auth/register/', v1.RegisterView.as_view(), name='register'),
    path('auth/login/', v1.LoginView.as_view(), name='login'),
    path('auth/logout/', v1.LogoutView.as_view(), name='logout'),
    path('auth/refresh/', v1.TokenRefreshView.as_view(), name='token-refresh'),
    path('users/me/change-password/', v1.ChangePasswordView.as_view(), name='change-password'),   # noqa
    path('users/me/', v1.UserProfileView.as_view(), name='user-profile'),
    path('users/', v1.CreateUserView.as_view(), name='create-user'),
    # path('users/<int:pk>/assign-role', v1.AssignGroupView.as_view(), name='assign-role'),     # noqa
    path('users/', v1.UserListView.as_view(), name='user-list'),
    # path('permissions/', v1.PermissionListView.as_view(), name='permission-list'),       # noqa
    path('users/verify/', v1.UserExistenceCheckView.as_view(), name='user-existence-check'),   # noqa
]

urlpatterns += router.urls

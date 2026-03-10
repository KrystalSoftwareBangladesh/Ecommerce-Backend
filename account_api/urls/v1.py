from rest_framework.routers import DefaultRouter

from account_api.views import v1


router = DefaultRouter()
router.register(
    r'chart-of-accounts',
    v1.ChartOfAccountViewSet,
    basename='chart-of-account',
)

urlpatterns = []
urlpatterns += router.urls

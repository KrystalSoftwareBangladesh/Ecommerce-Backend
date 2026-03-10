from rest_framework.routers import DefaultRouter

from transaction_api.views import v1


router = DefaultRouter()
router.register(
    r'transactions',
    v1.AccountingTransactionViewSet,
    basename='transaction',
)

urlpatterns = []
urlpatterns += router.urls

# sale_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from sale_api.views import v1


router = DefaultRouter()
router.register(r'sales', v1.SaleViewSet, basename='sales')

urlpatterns = []
urlpatterns += router.urls

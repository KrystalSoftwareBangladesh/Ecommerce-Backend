# supplier_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from supplier_api.views import v1


router = DefaultRouter()
router.register(r'suppliers', v1.SupplierViewSet, basename='supplier')

urlpatterns = []
urlpatterns += router.urls

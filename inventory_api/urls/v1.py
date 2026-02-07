# inventory_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from inventory_api.views import v1

router = DefaultRouter()

router.register(
    r'inventory-movements',
    v1.InventoryMovementViewSet,
    basename='inventory-movement'
)

urlpatterns = []
urlpatterns += router.urls

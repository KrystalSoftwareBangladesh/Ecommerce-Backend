# product_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from product_api.views import v1

router = DefaultRouter()

router.register(r'products', v1.ProductViewSet, basename='product')
router.register(r'product-variants', v1.ProductVariantViewSet, basename='product-variant')  # noqa
# router.register(r'inventory-movements', InventoryMovementViewSet,
#                 basename='inventory-movement')

urlpatterns = []
urlpatterns += router.urls

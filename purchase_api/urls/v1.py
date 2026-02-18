# purchase_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from purchase_api.views import v1


router = DefaultRouter()
router.register(r'purchases', v1.PurchaseViewSet, basename='purchases')

urlpatterns = []
urlpatterns += router.urls

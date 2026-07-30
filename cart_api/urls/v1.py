# cart_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from cart_api.views import v1


router = DefaultRouter()
router.register(r'carts', v1.CartViewSet, basename='cart')

urlpatterns = []
urlpatterns += router.urls

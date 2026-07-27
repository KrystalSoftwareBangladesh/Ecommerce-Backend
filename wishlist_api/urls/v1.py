# wishlist_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from wishlist_api.views import v1


router = DefaultRouter()
router.register(r'wishlists', v1.WishlistViewSet, basename='wishlists')

urlpatterns = []
urlpatterns += router.urls

# banner_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from banner_api.views import v1


router = DefaultRouter()
router.register(
    r'placements', v1.BannerPlacementViewSet, basename='banner-placement')
router.register(r'', v1.BannerViewSet, basename='banners')

urlpatterns = []
urlpatterns += router.urls

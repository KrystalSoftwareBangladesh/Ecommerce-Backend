# origin_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from origin_api.views import v1


router = DefaultRouter()
router.register(r'origins', v1.OriginViewSet, basename='origin')

urlpatterns = []
urlpatterns += router.urls

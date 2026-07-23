# review_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from review_api.views import v1

router = DefaultRouter()

router.register(r'reviews', v1.ReviewViewSet, basename='review')

urlpatterns = []
urlpatterns += router.urls

# category_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from category_api.views import v1


router = DefaultRouter()
router.register(r'categories', v1.CategoryViewSet, basename='categories')

urlpatterns = []
urlpatterns += router.urls

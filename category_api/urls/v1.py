# from django.urls import path
from rest_framework.routers import DefaultRouter

from category_api.views import v1


router = DefaultRouter()


router.register(r'categories', v1.CategoryViewSet, basename='categories')


urlpatterns = []

urlpatterns += router.urls

# blog_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from blog_api.views import v1


router = DefaultRouter()

router.register(
    r'blog/posts',
    v1.BlogPostViewSet,
    basename='blog-post',
)
router.register(
    r'blog/tags',
    v1.BlogTagViewSet,
    basename='blog-tag',
)

urlpatterns = []
urlpatterns += router.urls

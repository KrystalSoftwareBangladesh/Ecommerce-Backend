# cms_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from cms_api.views import v1


router = DefaultRouter()

router.register(
    r'cms/pages',
    v1.CmsPageViewSet,
    basename='cms-page',
)
router.register(
    r'cms/public/pages',
    v1.CmsPagePublicViewSet,
    basename='cms-public-page',
)
router.register(
    r'cms/sections',
    v1.CmsSectionViewSet,
    basename='cms-section',
)
router.register(
    r'cms/section-types',
    v1.SectionTypeViewSet,
    basename='cms-section-type',
)

urlpatterns = []
urlpatterns += router.urls

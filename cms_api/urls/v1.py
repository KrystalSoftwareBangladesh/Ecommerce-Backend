# cms_api/urls/v1.py
from django.urls import path

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
    r'cms/public/sitemap',
    v1.CmsSitemapViewSet,
    basename='cms-sitemap',
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
router.register(
    r'cms/redirects',
    v1.CmsRedirectViewSet,
    basename='cms-redirect',
)
router.register(
    r'cms/navigation',
    v1.CmsNavigationMenuViewSet,
    basename='cms-navigation-menu',
)

urlpatterns = [
    path(
        'cms/public/preview/<str:token>/',
        v1.CmsPreviewView.as_view(),
        name='cms-public-preview',
    ),
    path(
        'cms/public/navigation/<str:key>/',
        v1.CmsNavigationPublicView.as_view(),
        name='cms-public-navigation',
    ),
]
urlpatterns += router.urls

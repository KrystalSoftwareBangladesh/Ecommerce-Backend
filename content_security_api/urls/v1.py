# content_security_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from content_security_api.views import v1


router = DefaultRouter()

router.register(
    r'content-security/scans',
    v1.ContentScanViewSet,
    basename='content-security-scan',
)
router.register(
    r'content-security/findings',
    v1.ContentScanFindingViewSet,
    basename='content-security-finding',
)
router.register(
    r'content-security/keyword-rules',
    v1.KeywordRuleViewSet,
    basename='content-security-keyword-rule',
)
router.register(
    r'content-security/domain-rules',
    v1.DomainRuleViewSet,
    basename='content-security-domain-rule',
)
router.register(
    r'content-security/html-tag-rules',
    v1.HtmlTagRuleViewSet,
    basename='content-security-html-tag-rule',
)
router.register(
    r'content-security/html-attribute-rules',
    v1.HtmlAttributeRuleViewSet,
    basename='content-security-html-attribute-rule',
)
router.register(
    r'content-security/redirect-rules',
    v1.RedirectRuleViewSet,
    basename='content-security-redirect-rule',
)
router.register(
    r'content-security/hidden-content-rules',
    v1.HiddenContentRuleViewSet,
    basename='content-security-hidden-content-rule',
)
router.register(
    r'content-security/obfuscation-rules',
    v1.ObfuscationRuleViewSet,
    basename='content-security-obfuscation-rule',
)

urlpatterns = []
urlpatterns += router.urls

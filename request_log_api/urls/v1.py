# request_log_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from request_log_api.views import v1


router = DefaultRouter()

router.register(
    r'request-logs',
    v1.RequestLogViewSet,
    basename='request-log',
)

urlpatterns = []
urlpatterns += router.urls

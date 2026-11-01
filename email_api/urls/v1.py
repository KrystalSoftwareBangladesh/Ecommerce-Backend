# email_api/urls/v1.py
from rest_framework.routers import DefaultRouter

from email_api.views import v1


router = DefaultRouter()

router.register(
    r'email/order-notification-recipients',
    v1.OrderNotificationRecipientViewSet,
    basename='order-notification-recipient',
)

urlpatterns = []
urlpatterns += router.urls

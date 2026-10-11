# shipping_api/urls/v1.py
from django.urls import path
from rest_framework.routers import DefaultRouter
from shipping_api.views import v1

router = DefaultRouter()
router.register(
    r"shipping/zones",
    v1.ShippingZoneViewSet,
    basename="shipping-zone",
)
router.register(
    r"shipping/methods",
    v1.ShippingMethodViewSet,
    basename="shipping-method",
)
router.register(
    r"shipping/rates",
    v1.ShippingRateViewSet,
    basename="shipping-rate",
)

urlpatterns = router.urls
urlpatterns += [
    path(
        "shipping/options/",
        v1.ShippingOptionView.as_view(),
        name="shipping-options",
    ),
]

from rest_framework.routers import DefaultRouter
from customer_api.views import v1

router = DefaultRouter()
router.register(r"customers", v1.CustomerViewSet, basename="customer")

urlpatterns = router.urls

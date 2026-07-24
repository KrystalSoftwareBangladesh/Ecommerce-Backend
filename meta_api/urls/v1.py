# meta_api/urls/v1.py
from django.urls import path

from meta_api.views import v1


urlpatterns = [
    path('moderation-statuses/', v1.ModerationStatusListAPIView.as_view())
]

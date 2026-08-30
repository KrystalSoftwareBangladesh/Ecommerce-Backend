# request_log_api/tests/urls.py
"""
Endpoints used only by the middleware tests.

Mounted with `override_settings(ROOT_URLCONF=...)` so the middleware can
be exercised against a multipart upload, an unhandled exception and a
payload full of secrets without depending on - or disturbing - any real
business endpoint.
"""
from django.urls import path

from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['POST'])
@permission_classes([AllowAny])
def echo(request):
    return Response({
        'received': request.data,
        'access_token': 'issued-token-value',
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def upload(request):
    return Response({'files': sorted(request.FILES)})


@api_view(['POST'])
@permission_classes([AllowAny])
def item(request, pk):
    return Response({'pk': pk})


@api_view(['GET'])
@permission_classes([AllowAny])
def boom(request):
    raise RuntimeError('exploded while using password=hunter2')


urlpatterns = [
    path('probe/echo/', echo),
    path('probe/upload/', upload),
    path('probe/boom/', boom),
    path('probe/items/<int:pk>/', item),
    path('static/probe/', echo),
]

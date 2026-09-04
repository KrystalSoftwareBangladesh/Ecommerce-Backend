# product_api/views/v1/product_image.py
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from EcommerceBackend.core.permission import PublicReadPermissionMixin
from product_api.models import ProductImage
from product_api.serializers import (
    ProductImageCreateUpdateSerializer,
    ProductImageDetailSerializer,
    ProductImageListSerializer,
    BulkProductImageUploadSerializer,
)
from product_api.services.product import (
    replace_product_image,
    reorder_product_images,
    set_product_image_default,
    soft_delete_product_image,
    upload_product_image,
    bulk_upload_product_images,
)


@extend_schema(tags=["Products"])
class ProductImageViewSet(
    PublicReadPermissionMixin,
    viewsets.ModelViewSet,
):
    """ViewSet for product image CRUD and image-specific actions."""
    queryset = ProductImage.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
    )
    serializer_class = ProductImageCreateUpdateSerializer

    def get_queryset(self):
        return (
            self.queryset.select_related('product', 'created_by', 'updated_by')
            .prefetch_related('product__categories')
            .order_by('display_order', 'created_at', 'id')
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductImageListSerializer
        if self.action == 'retrieve':
            return ProductImageDetailSerializer
        return ProductImageCreateUpdateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = upload_product_image(
            product=serializer.validated_data.get('product'),
            image_file=serializer.validated_data.get('image'),
            alt_text=serializer.validated_data.get('alt_text', ''),
            created_by=request.user,
            updated_by=request.user,
        )
        response_serializer = ProductImageDetailSerializer(image)
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        image = self.get_object()
        soft_delete_product_image(image, deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Bulk upload product images",
        request=BulkProductImageUploadSerializer,
        responses=ProductImageDetailSerializer(many=True),
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='bulk-upload',
    )
    def bulk_upload(self, request):
        serializer = BulkProductImageUploadSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )

        serializer.is_valid(raise_exception=True)

        images = bulk_upload_product_images(
            product=serializer.validated_data['product'],
            images_data=serializer.validated_data['images'],
            created_by=request.user,
            updated_by=request.user,
        )

        response_serializer = ProductImageDetailSerializer(
            images,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='replace-image')
    def replace_image(self, request, pk=None):
        image = self.get_object()
        image_file = request.FILES.get('image')
        if image_file is None:
            return Response(
                {'image': ['An image file is required.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        replace_product_image(image, image_file, updated_by=request.user)
        serializer = ProductImageDetailSerializer(image)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        image = self.get_object()
        set_product_image_default(image, updated_by=request.user)
        serializer = ProductImageDetailSerializer(image)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reorder')
    def reorder(self, request, pk=None):
        image = self.get_object()
        new_display_order = request.data.get('display_order')
        if new_display_order is None:
            return Response(
                {'display_order': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            reordered_images = reorder_product_images(
                product=image.product,
                image_id=image.id,
                new_display_order=int(new_display_order),
                updated_by=request.user,
            )

        serializer = ProductImageListSerializer(reordered_images, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

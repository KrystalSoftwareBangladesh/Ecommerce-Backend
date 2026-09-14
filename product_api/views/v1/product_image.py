# product_api/views/v1/product_image.py
from django.db import transaction
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

import django_filters

from EcommerceBackend.core.permission import (
    PublicReadPermissionMixin, ModelPermissionAccess,
)
from product_api.models import ProductImage
from product_api.serializers import (
    ProductImageCreateUpdateSerializer,
    ProductImageDetailSerializer,
    ProductImageListSerializer,
    BulkProductImageUploadSerializer,
    ProductImageSummarySerializer,
)
from product_api.services import (
    replace_product_image,
    reorder_product_images,
    set_product_image_default,
    soft_delete_product_image,
    upload_product_image,
    bulk_upload_product_images,
    get_product_image_summary,
)


def _parse_bulk_image_data(data, files):
    images = {}

    for key, values in data.lists():
        if not key.startswith("images["):
            continue

        try:
            index = int(key.split("[", 1)[1].split("]", 1)[0])
            field = key.split("][", 1)[1].rstrip("]")
        except (IndexError, ValueError):
            continue

        images.setdefault(index, {})[field] = values[-1]

    for key, values in files.lists():
        if not key.startswith("images["):
            continue

        try:
            index = int(key.split("[", 1)[1].split("]", 1)[0])
            field = key.split("][", 1)[1].rstrip("]")
        except (IndexError, ValueError):
            continue

        images.setdefault(index, {})[field] = values[-1]

    return [
        images[index]
        for index in sorted(images)
    ]


class ProductImageFilter(django_filters.FilterSet):
    products = django_filters.CharFilter(
        method='filter_products',
    )

    class Meta:
        model = ProductImage
        fields = ['products']

    def filter_products(self, queryset, name, value):
        values = [
            item.strip()
            for item in value.split(',')
            if item.strip()
        ]

        if not values:
            return queryset

        product_ids = []
        product_slugs = []

        for item in values:
            if item.isdigit():
                product_ids.append(int(item))
            else:
                product_slugs.append(item)

        product_filter = Q()

        if product_ids:
            product_filter |= Q(product__id__in=product_ids)

        if product_slugs:
            product_filter |= Q(product__slug__in=product_slugs)

        return queryset.filter(product_filter).distinct()


@extend_schema(tags=["Products"])
class ProductImageViewSet(
    PublicReadPermissionMixin,
    viewsets.ModelViewSet,
):
    permission_classes = [ModelPermissionAccess]
    custom_permissions = {
        "replace_image": "change_productimage",
        "set_default": "change_productimage",
        "reorder": "change_productimage",
    }
    queryset = ProductImage.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
    )
    serializer_class = ProductImageCreateUpdateSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProductImageFilter

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
        response_serializer = ProductImageDetailSerializer(
            image,
            context=self.get_serializer_context(),
        )
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
        description=(
            "Upload 1–10 images for a single product using multipart/form-data. "   # noqa
            "For each image, use indexed fields such as "
            "`images[0][image]`, `images[0][alt_text]`, "
            "`images[0][display_order]`, and `images[0][is_default]`."
        ),
        request=BulkProductImageUploadSerializer,
        responses=ProductImageDetailSerializer(many=True),
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='bulk-upload',
    )
    def bulk_upload(self, request):
        data = {
            "product": request.data.get("product"),
            "images": _parse_bulk_image_data(
                request.data,
                request.FILES,
            ),
        }
        serializer = BulkProductImageUploadSerializer(
            data=data,
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
        serializer = ProductImageDetailSerializer(
            image,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        image = self.get_object()
        set_product_image_default(image, updated_by=request.user)
        serializer = ProductImageDetailSerializer(
            image,
            context=self.get_serializer_context(),
        )
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

        serializer = ProductImageListSerializer(
            reordered_images,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Product images summary",
        description=(
            "Products count"
            "Product images count"
            "High resolution count"
            "Ratio mismatch count"
        ),
        request=None,
        responses=ProductImageSummarySerializer(),
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='summary',
    )
    def summary(self, request, *args, **kwargs):
        queryset = ProductImage.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        queryset = self.filter_queryset(queryset)
        summary_data = get_product_image_summary(queryset)
        serializer = ProductImageSummarySerializer(summary_data)
        return Response(serializer.data)

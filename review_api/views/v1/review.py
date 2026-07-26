# review_api/views/v1/review.py
# from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend

import django_filters

from drf_spectacular.utils import extend_schema

from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import PublicReadPermissionMixin
from EcommerceBackend.core.choices import ModerationStatus

from review_api.models import Review
from review_api.serializers import (
    ReviewListSerializer,
    ReviewDetailSerializer,
    ReviewCreateUpdateSerializer,
)
from review_api.services.review import (
    approve_review,
    reject_review,
)


class ReviewFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product_id")
    rating = django_filters.NumberFilter(field_name="rating")
    status = django_filters.NumberFilter(field_name="status")

    class Meta:
        model = Review
        fields = ["product", "rating", "status"]


@extend_schema(tags=["Reviews"])
class ReviewViewSet(
    PublicReadPermissionMixin,
    viewsets.ModelViewSet,
):
    permission_classes = [IsAuthenticated]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
    ]

    filterset_class = ReviewFilter

    search_fields = [
        "title",
        "body",
        "created_by__first_name",
        "created_by__last_name",
    ]

    def get_queryset(self):
        queryset = Review.objects.filter(
            # is_active=True,
        ).select_related(
            "product",
            "created_by",
            "approved_by",
        )

        # if self.request.user.is_authenticated:
        #     queryset = queryset.filter(
        #         Q(status=ModerationStatus.APPROVED)
        #         | Q(created_by=self.request.user)
        #     )
        # else:
        #     queryset = queryset.filter(
        #         status=ModerationStatus.APPROVED
        #     )

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return ReviewListSerializer

        if self.action == "retrieve":
            return ReviewDetailSerializer

        return ReviewCreateUpdateSerializer

    def create(self, request, *args, **kwargs):
        product_id = request.data.get("product")
        if Review.objects.filter(
            product_id=product_id,
            created_by=request.user,
        ).exclude(
            status=ModerationStatus.REJECTED,
        ).exists():
            return Response(
                {
                    "detail": "You have already reviewed this product."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()

        return Response(
            ReviewDetailSerializer(
                review,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        review = self.get_object()

        review.updated_by = request.user
        review.save(update_fields=["updated_by", "updated_at"])

        review.soft_delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=None,
        responses={200: None},
        description="Approve a review."
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def approve(self, request, pk=None):
        review = self.get_object()

        approve_review(
            review=review,
            user=request.user,
        )

        return Response(
            {"detail": "Review approved."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=None,
        responses={200: None},
        description="Reject a review."
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
    )
    def reject(self, request, pk=None):
        review = self.get_object()

        reject_review(
            review=review,
        )

        return Response(
            {"detail": "Review rejected."},
            status=status.HTTP_200_OK,
        )

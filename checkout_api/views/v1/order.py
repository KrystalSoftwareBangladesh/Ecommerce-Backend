# checkout_api/views/v1/order.py

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from checkout_api.serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderCancelResponseSerializer,
)
from checkout_api.services import create_order, cancel_order
from sale_api.models import Sale, SaleStatus


def _customer_orders(user):
    """Return only active website orders belonging to this user."""
    return (
        Sale.objects.filter(
            customer__user=user,
            channel=Sale.SaleChannel.WEBSITE,
            is_active=True,
        )
        .select_related("customer", "customer__user")
        .prefetch_related(
            "items__product_variant",
            "items__product_variant__product",
        )
        .order_by("-created_at", "-id")
    )


@extend_schema(
    tags=["Checkout"],
    request=OrderCreateSerializer,
    responses={201: OrderDetailSerializer},
)
class CheckoutConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_order(
            user=request.user,
            **serializer.validated_data,
        )
        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Checkout"],
    responses={200: OrderListSerializer(many=True)},
)
class CustomerOrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = _customer_orders(request.user)
        return Response(OrderListSerializer(orders, many=True).data)


@extend_schema(
    tags=["Checkout"],
    responses={200: OrderDetailSerializer},
)
class CustomerOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(_customer_orders(request.user), pk=pk)
        return Response(OrderDetailSerializer(order).data)


@extend_schema(
    tags=["Checkout"],
    request=None,
    responses={200: OrderCancelResponseSerializer},
)
class CustomerOrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(_customer_orders(request.user), pk=pk)
        if order.status == SaleStatus.CANCELLED:
            return Response({
                "id": order.id,
                "status": order.status,
                "message": "Order is already cancelled.",
            })

        order = cancel_order(user=request.user, sale=order)
        return Response({
            "id": order.id,
            "status": order.status,
            "message": "Order cancelled successfully.",
        })

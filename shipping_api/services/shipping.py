# shipping_api/services/shipping.py
import decimal

from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from rest_framework.exceptions import ValidationError

from cart_api.models import Cart
from cart_api.services.cart import get_active_cart
from customer_api.models import CustomerAddress

from shipping_api.models import (
    ShippingZone,
    ShippingZoneRule,
    ShippingRate,
)


def match_zone(*, city, postcode, zone=None):
    """
    Match an address to a shipping zone.

    Matching precedence:
    0. The zone explicitly chosen for the address
       (``CustomerAddress.shipping_zone``), when it is
       still active and not deleted.
    1. Exact postcode rule (case-insensitive, trimmed).
    2. Exact city rule (case-insensitive, trimmed).
    3. The single default zone (is_default=True).

    Returns the matched ShippingZone or None.
    """
    # 0. Explicit zone on the address
    if (
        zone is not None
        and zone.is_active
        and zone.deleted_at is None
    ):
        return zone

    city = (city or "").strip()
    postcode = (postcode or "").strip()

    # 1. Postcode match
    if postcode:
        postcode_rules = (
            ShippingZoneRule.objects.filter(
                match_type=ShippingZoneRule.MatchType.POSTCODE,
                zone__is_active=True,
                zone__deleted_at__isnull=True,
            )
            .select_related("zone")
        )
        for rule in postcode_rules:
            if postcode.lower() == rule.match_value.strip().lower():
                return rule.zone

    # 2. City match
    if city:
        city_rules = (
            ShippingZoneRule.objects.filter(
                match_type=ShippingZoneRule.MatchType.CITY,
                zone__is_active=True,
                zone__deleted_at__isnull=True,
            )
            .select_related("zone")
        )
        for rule in city_rules:
            if city.lower() == rule.match_value.strip().lower():
                return rule.zone

    # 3. Default zone
    default_zone = ShippingZone.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
        is_default=True,
    ).first()

    return default_zone


def calculate_shipping_charge(
    *,
    rate,
    cart_subtotal,
):
    """
    Calculate the shipping charge for a given rate
    and cart subtotal.

    If free_shipping_threshold is set and the cart
    subtotal >= threshold, shipping is free.
    Otherwise, charge the base_rate.
    """
    if (
        rate.free_shipping_threshold is not None
        and cart_subtotal >= rate.free_shipping_threshold
    ):
        return decimal.Decimal("0.00")

    return rate.base_charge


def _get_cart_subtotal(*, user):
    """
    Calculate the merchandise subtotal from the
    user's active cart using backend prices.

    Returns (cart, subtotal) tuple.
    Raises ValidationError if no active cart.
    """
    cart = get_active_cart(user=user)

    if cart is None:
        raise ValidationError(
            "No active cart found."
        )

    cart_data = (
        Cart.objects.filter(pk=cart.pk)
        .annotate(
            subtotal=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("cart_items__quantity")
                        * F(
                            "cart_items__product"
                            "__current_selling_price"
                        ),
                        output_field=DecimalField(
                            max_digits=12,
                            decimal_places=2,
                        ),
                    ),
                    filter=Q(cart_items__is_active=True),
                ),
                Value(
                    decimal.Decimal("0.00"),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2,
                    ),
                ),
            ),
        )
        .first()
    )

    return cart_data, cart_data.subtotal


def get_shipping_options(*, user, address_id):
    """
    Return available shipping options for the
    authenticated user's cart and delivery address.

    Steps:
    1. Validate the address belongs to the user.
    2. Match address to a zone.
    3. Get active rates for the zone.
    4. Calculate charges using backend cart subtotal.
    5. Return list of options.
    """
    # 1. Validate address
    try:
        address = CustomerAddress.objects.select_related(
            "customer",
            "shipping_zone",
        ).get(
            id=address_id,
            address_type=(
                CustomerAddress.AddressType.SHIPPING
            ),
            is_active=True,
            deleted_at__isnull=True,
        )
    except CustomerAddress.DoesNotExist:
        raise ValidationError(
            "Invalid or inactive shipping address."
        )

    if address.customer.user != user:
        raise ValidationError(
            "Address does not belong to this customer."
        )

    # 2. Match zone
    zone = match_zone(
        city=address.city,
        postcode=address.postcode,
        zone=address.shipping_zone,
    )

    if zone is None:
        raise ValidationError(
            "No shipping zone found for this address. "
            "Please contact support."
        )

    # 3. Get active rates
    rates = (
        ShippingRate.objects.filter(
            zone=zone,
            is_active=True,
            deleted_at__isnull=True,
            method__is_active=True,
            method__deleted_at__isnull=True,
        )
        .select_related("method")
        .order_by(
            "method__display_order",
            "method__name",
        )
    )

    if not rates.exists():
        raise ValidationError(
            "No shipping methods available for "
            "your area."
        )

    # 4. Calculate charges
    cart, subtotal = _get_cart_subtotal(user=user)

    options = []
    for rate in rates:
        charge = calculate_shipping_charge(
            rate=rate,
            cart_subtotal=subtotal,
        )
        is_free = (
            charge == decimal.Decimal("0.00")
            and rate.base_charge > 0
        )
        options.append({
            "shipping_method_id": rate.method.id,
            "shipping_method_name": rate.method.name,
            "shipping_method_code": rate.method.code,
            "base_charge": rate.base_charge,
            "shipping_charge": charge,
            "is_free_shipping": is_free,
            "free_shipping_threshold": (
                rate.free_shipping_threshold
            ),
            "zone_name": zone.name,
            "zone_code": zone.code,
        })

    return {
        "zone": zone,
        "options": options,
        "cart_subtotal": subtotal,
    }

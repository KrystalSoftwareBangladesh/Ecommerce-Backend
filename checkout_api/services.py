import decimal

from rest_framework.exceptions import ValidationError

from cart_api.services.cart import get_active_cart
from customer_api.models import CustomerAddress
from shipping_api.services.shipping import (
    match_zone,
    calculate_shipping_charge,
)
from shipping_api.models import ShippingRate


def _validate_cart(user):
    """Return the active cart or raise."""
    cart = get_active_cart(user=user)
    if cart is None:
        raise ValidationError("No active cart found.")
    return cart


def _validate_cart_items(cart):
    """
    Return active cart items with product data.

    Raises if the cart is empty or contains
    inactive/invalid products.
    """
    items = (
        cart.cart_items.filter(is_active=True)
        .select_related("product")
        .order_by("created_at")
    )
    if not items.exists():
        raise ValidationError("Cart is empty.")
    return list(items)


def _validate_products(cart_items):
    """
    Validate every product in the cart is active
    and has a valid price.

    Returns a list of error strings. Empty means
    all products are valid.
    """
    errors = []
    for item in cart_items:
        product = item.product
        if not product.is_active:
            errors.append(
                f"Product '{product.name}' is no "
                "longer available."
            )
        elif (
            product.current_selling_price is None
            or product.current_selling_price <= 0
        ):
            errors.append(
                f"Product '{product.name}' has no "
                "valid price."
            )
    return errors


def _validate_address(user, address_id):
    """
    Validate the shipping address belongs to the
    user and is active.

    Returns the CustomerAddress or raises.
    """
    try:
        address = CustomerAddress.objects.get(
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
    return address


def _resolve_shipping(address, method_id, subtotal):
    """
    Match zone, find rate, calculate charge.

    Returns a dict with shipping details or raises
    ValidationError.
    """
    zone = match_zone(
        city=address.city,
        postcode=address.postcode,
    )
    if zone is None:
        raise ValidationError(
            "No shipping zone found for this address."
        )

    try:
        rate = ShippingRate.objects.get(
            zone=zone,
            method_id=method_id,
            is_active=True,
            deleted_at__isnull=True,
            method__is_active=True,
            method__deleted_at__isnull=True,
        )
    except ShippingRate.DoesNotExist:
        raise ValidationError(
            "Shipping method is not available for "
            "your area."
        )

    charge = calculate_shipping_charge(
        rate=rate,
        cart_subtotal=subtotal,
    )
    is_free = (
        charge == decimal.Decimal("0.00")
        and rate.base_charge > 0
    )

    return {
        "method_id": rate.method.id,
        "method_name": rate.method.name,
        "method_code": rate.method.code,
        "base_charge": rate.base_charge,
        "shipping_charge": charge,
        "is_free_shipping": is_free,
        "free_shipping_threshold": (
            rate.free_shipping_threshold
        ),
        "zone_name": zone.name,
        "zone_code": zone.code,
    }


def _build_item_lines(cart_items):
    """
    Build item detail dicts with current backend
    prices.

    Returns (item_dicts, subtotal).
    """
    subtotal = decimal.Decimal("0.00")
    item_dicts = []
    for item in cart_items:
        product = item.product
        unit_price = product.current_selling_price
        line_total = unit_price * item.quantity
        subtotal += line_total
        item_dicts.append({
            "id": item.id,
            "product_id": product.id,
            "product_name": product.name,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        })
    return item_dicts, subtotal


def validate_checkout(*, user, shipping_address_id,
                      shipping_method_id):
    """
    Validate the user's checkout and return a
    calculated summary.

    Does NOT create a sale, change cart status, or
    deduct inventory.

    Returns a dict with ``is_valid``, ``cart``,
    ``pricing``, ``shipping``, and ``errors``.
    """
    errors = []
    cart_data = None
    pricing_data = None
    shipping_data = None

    # --- Cart validation ---
    try:
        cart = _validate_cart(user)
    except ValidationError as exc:
        return {
            "is_valid": False,
            "cart": None,
            "pricing": None,
            "shipping": None,
            "errors": [str(exc.detail[0])],
        }

    try:
        cart_items = _validate_cart_items(cart)
    except ValidationError as exc:
        return {
            "is_valid": False,
            "cart": None,
            "pricing": None,
            "shipping": None,
            "errors": [str(exc.detail[0])],
        }

    # --- Product validation ---
    product_errors = _validate_products(cart_items)
    errors.extend(product_errors)

    # If products are invalid, stop — prices are
    # unreliable.
    if errors:
        return {
            "is_valid": False,
            "cart": None,
            "pricing": None,
            "shipping": None,
            "errors": errors,
        }

    # --- Build item lines and subtotal ---
    item_dicts, subtotal = _build_item_lines(
        cart_items
    )

    cart_data = {
        "id": cart.id,
        "items": item_dicts,
    }

    # --- Address validation ---
    try:
        address = _validate_address(
            user, shipping_address_id
        )
    except ValidationError as exc:
        return {
            "is_valid": False,
            "cart": cart_data,
            "pricing": None,
            "shipping": None,
            "errors": [str(exc.detail[0])],
        }

    # --- Shipping resolution ---
    try:
        shipping = _resolve_shipping(
            address, shipping_method_id, subtotal
        )
    except ValidationError as exc:
        return {
            "is_valid": False,
            "cart": cart_data,
            "pricing": None,
            "shipping": None,
            "errors": [str(exc.detail[0])],
        }

    # --- Calculate totals ---
    discount_total = decimal.Decimal("0.00")
    tax_total = decimal.Decimal("0.00")
    grand_total = (
        subtotal - discount_total
        + tax_total + shipping["shipping_charge"]
    )

    pricing_data = {
        "subtotal": subtotal,
        "shipping_charge": shipping["shipping_charge"],
        "discount_total": discount_total,
        "tax_total": tax_total,
        "grand_total": grand_total,
    }

    shipping_data = {
        "address_id": address.id,
        "method_id": shipping["method_id"],
        "method_name": shipping["method_name"],
        "method_code": shipping["method_code"],
        "zone_name": shipping["zone_name"],
        "zone_code": shipping["zone_code"],
        "base_charge": shipping["base_charge"],
        "is_free_shipping": (
            shipping["is_free_shipping"]
        ),
        "free_shipping_threshold": (
            shipping["free_shipping_threshold"]
        ),
    }

    return {
        "is_valid": True,
        "cart": cart_data,
        "pricing": pricing_data,
        "shipping": shipping_data,
        "errors": [],
    }

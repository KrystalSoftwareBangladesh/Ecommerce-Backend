import decimal
import hashlib
import json

from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from EcommerceBackend.core.choices import CartStatus
from cart_api.services.cart import get_active_cart
from customer_api.models import CustomerAddress
from inventory_api.services.reservation import (
    release_reservations,
    reserve_stock,
)
from sale_api.models import (
    PaymentStatus,
    Sale,
    SaleItem,
    SaleStatus,
)
from sale_api.services import (
    get_or_create_cod_payment_method,
)
from shipping_api.models import ShippingRate
from shipping_api.services.shipping import (
    calculate_shipping_charge,
    match_zone,
)


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


# ── Order creation and cancellation ──────────


def _build_fingerprint(
    shipping_address_id,
    shipping_method_id,
    notes,
):
    """
    Build a canonical SHA-256 fingerprint of the
    meaningful request inputs.

    The fingerprint is deterministic: the same
    inputs always produce the same hash.
    """
    canonical = json.dumps(
        {
            'shipping_address_id': (
                shipping_address_id
            ),
            'shipping_method_id': (
                shipping_method_id
            ),
            'notes': (notes or '').strip(),
        },
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(
        canonical.encode()
    ).hexdigest()


def _resolve_variant(product):
    """
    Resolve a product to exactly one eligible
    active variant.

    Returns the ProductVariant or raises
    ValidationError.
    """
    active_variants = (
        product.variants.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
    )
    count = active_variants.count()
    if count == 0:
        raise ValidationError(
            f"Product '{product.name}' has no "
            "available variants."
        )
    if count == 1:
        return active_variants.first()
    raise ValidationError(
        f"Product '{product.name}' has multiple "
        "variants. Please select one."
    )


def _snapshot_address(address):
    """
    Return a JSON-safe dict of the address fields
    for persistence on the Sale.
    """
    return {
        'first_name': address.first_name,
        'last_name': address.last_name,
        'company': address.company,
        'address_1': address.address_1,
        'address_2': address.address_2,
        'city': address.city,
        'state': address.state,
        'postcode': address.postcode,
        'country': address.country,
        'phone': address.phone,
    }


@transaction.atomic
def create_order(
    *,
    user,
    shipping_address_id,
    shipping_method_id,
    idempotency_key,
    notes='',
):
    """
    Create a storefront order from the user's
    active cart.

    Idempotency is checked FIRST, before any cart
    validation.

    - Same idempotency_key + same fingerprint:
      return existing order.
    - Same idempotency_key + different fingerprint:
      raise conflict (409 at API layer).
    - No existing order: create new.

    The entire operation is atomic — any failure
    rolls back all changes.
    """
    # --- Step 0: Validate idempotency key ---
    if not idempotency_key or not str(
        idempotency_key
    ).strip():
        raise ValidationError(
            "idempotency_key is required."
        )

    # --- Step 1: Idempotency (before cart) ---
    fingerprint = _build_fingerprint(
        shipping_address_id,
        shipping_method_id,
        notes,
    )

    customer = user.customer_profile
    existing = Sale.objects.filter(
        customer=customer,
        idempotency_key=idempotency_key,
    ).first()

    if existing is not None:
        if (
            existing.request_fingerprint
            == fingerprint
        ):
            # Same key, same inputs — return
            # existing order.
            return existing
        # Same key, different inputs — conflict.
        raise ValidationError(
            "An order with this idempotency key "
            "already exists with different "
            "parameters."
        )

    # --- Step 2: Cart validation ---
    cart = get_active_cart(user=user)
    if cart is None:
        raise ValidationError(
            "No active cart found."
        )

    cart_items = _validate_cart_items(cart)
    product_errors = _validate_products(cart_items)
    if product_errors:
        raise ValidationError(product_errors)

    # --- Step 3: Resolve variants and prices ---
    resolved_items = []
    subtotal = decimal.Decimal("0.00")
    for item in cart_items:
        product = item.product
        variant = _resolve_variant(product)
        unit_price = (
            product.current_selling_price
        )
        line_total = (
            unit_price * item.quantity
        )
        subtotal += line_total
        resolved_items.append({
            'product_variant': variant,
            'quantity': item.quantity,
            'unit_price': unit_price,
            'line_total': line_total,
            'product_name': product.name,
            'variant_sku': variant.sku,
        })

    # --- Step 4: Validate address ---
    address = _validate_address(
        user, shipping_address_id
    )

    # --- Step 5: Validate shipping ---
    shipping = _resolve_shipping(
        address, shipping_method_id, subtotal
    )
    shipping_charge = shipping['shipping_charge']

    # --- Step 6: Get COD payment method ---
    cod_pm = get_or_create_cod_payment_method(
        user=user
    )

    # --- Step 7: Create Sale ---
    discount = decimal.Decimal("0.00")
    tax = decimal.Decimal("0.00")
    grand_total = (
        subtotal - discount
        + tax + shipping_charge
    )

    try:
        # The nested atomic block creates a savepoint.
        # A uniqueness race must not poison the outer
        # order transaction before we read the winner.
        with transaction.atomic():
            sale = Sale.objects.create(
                customer=customer,
                payment_method=cod_pm,
                sale_date=timezone.now().date(),
                channel=Sale.SaleChannel.WEBSITE,
                status=SaleStatus.PENDING,
                payment_status=PaymentStatus.UNPAID,
                subtotal_amount=subtotal,
                discount_amount=discount,
                tax_amount=tax,
                shipping_amount=shipping_charge,
                total_amount=grand_total,
                shipping_address_snapshot=(
                    _snapshot_address(address)
                ),
                shipping_method_snapshot={
                    'id': shipping['method_id'],
                    'name': shipping['method_name'],
                    'code': shipping['method_code'],
                },
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                notes=notes,
                created_by=user,
                updated_by=user,
            )
    except IntegrityError:
        # Concurrent insert with same
        # idempotency_key. Fetch and compare
        # fingerprints.
        existing = Sale.objects.filter(
            customer=customer,
            idempotency_key=idempotency_key,
        ).first()
        if existing is not None:
            if (
                existing.request_fingerprint
                == fingerprint
            ):
                return existing
            raise ValidationError(
                "An order with this idempotency "
                "key already exists with "
                "different parameters."
            )
        raise

    # --- Step 8: Create SaleItems ---
    for item in resolved_items:
        SaleItem.objects.create(
            sale=sale,
            product_variant=(
                item['product_variant']
            ),
            quantity=item['quantity'],
            unit_price=item['unit_price'],
            line_total=item['line_total'],
        )

    # --- Step 9: Reserve inventory ---
    reserve_items = [
        {
            'product_variant': (
                item['product_variant']
            ),
            'quantity': item['quantity'],
        }
        for item in resolved_items
    ]
    reserve_stock(
        sale, reserve_items, user=user
    )

    # --- Step 10: Mark cart CHECKED_OUT ---
    cart.status = CartStatus.CHECKED_OUT
    cart.updated_by = user
    cart.save(
        update_fields=[
            'status',
            'updated_by',
            'updated_at',
        ]
    )

    return sale


@transaction.atomic
def cancel_order(*, user, sale):
    """
    Cancel a pending storefront order.

    Only PENDING orders can be cancelled.
    Releases active reservations idempotently.

    Returns the cancelled sale.
    """
    if sale.status != SaleStatus.PENDING:
        raise ValidationError(
            "Only pending orders can be cancelled."
        )

    release_reservations(sale, user=user)

    sale.status = SaleStatus.CANCELLED
    sale.updated_by = user
    sale.save(
        update_fields=[
            'status',
            'updated_by',
            'updated_at',
        ]
    )

    return sale

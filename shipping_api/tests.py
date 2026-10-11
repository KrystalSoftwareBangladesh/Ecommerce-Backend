# shipping_api/tests.py
import decimal

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from user_api.models import User
from customer_api.models import CustomerProfile, CustomerAddress
from cart_api.models import Cart, CartItem
from product_api.models import Product
from EcommerceBackend.core.choices import CartStatus

from shipping_api.models import (
    ShippingZone,
    ShippingZoneRule,
    ShippingMethod,
    ShippingRate,
)
from shipping_api.services.shipping import (
    match_zone,
    calculate_shipping_charge,
)


class ShippingZoneModelTest(TestCase):
    """Tests for ShippingZone model."""

    def test_save_single_default(self):
        """Only one zone can be default."""
        z1 = ShippingZone.objects.create(
            name="Zone A", code="zone-a", is_default=True
        )
        z2 = ShippingZone.objects.create(
            name="Zone B", code="zone-b", is_default=True
        )
        z1.refresh_from_db()
        self.assertFalse(z1.is_default)
        self.assertTrue(z2.is_default)

    def test_str_with_default(self):
        z = ShippingZone.objects.create(
            name="Dhaka", code="dhaka", is_default=True
        )
        self.assertIn("default", str(z))


class ShippingMethodModelTest(TestCase):
    """Tests for ShippingMethod model."""

    def test_str(self):
        m = ShippingMethod.objects.create(
            name="Standard", code="standard"
        )
        self.assertEqual(str(m), "Standard")


class ShippingRateModelTest(TestCase):
    """Tests for ShippingRate model."""

    def test_str_with_threshold(self):
        zone = ShippingZone.objects.create(
            name="Dhaka", code="dhaka"
        )
        method = ShippingMethod.objects.create(
            name="Standard", code="standard"
        )
        rate = ShippingRate.objects.create(
            zone=zone,
            method=method,
            base_charge=60,
            free_shipping_threshold=1000,
        )
        self.assertIn("1000", str(rate))


class ZoneMatchingTest(TestCase):
    """Tests for zone matching logic."""

    def setUp(self):
        self.zone_dhaka = ShippingZone.objects.create(
            name="Dhaka", code="dhaka"
        )
        self.zone_chittagong = (
            ShippingZone.objects.create(
                name="Chittagong",
                code="chittagong",
            )
        )
        self.zone_default = ShippingZone.objects.create(
            name="Rest of BD",
            code="rest-bd",
            is_default=True,
        )
        ShippingZoneRule.objects.create(
            zone=self.zone_dhaka,
            match_type=ShippingZoneRule.MatchType.CITY,
            match_value="Dhaka",
        )
        ShippingZoneRule.objects.create(
            zone=self.zone_dhaka,
            match_type=(
                ShippingZoneRule.MatchType.POSTCODE
            ),
            match_value="1205",
        )
        ShippingZoneRule.objects.create(
            zone=self.zone_chittagong,
            match_type=ShippingZoneRule.MatchType.CITY,
            match_value="Chittagong",
        )

    def test_city_match(self):
        zone = match_zone(
            city="Dhaka", postcode=""
        )
        self.assertEqual(zone, self.zone_dhaka)

    def test_city_match_case_insensitive(self):
        zone = match_zone(
            city="dhaka", postcode=""
        )
        self.assertEqual(zone, self.zone_dhaka)

    def test_city_match_strips_whitespace(self):
        zone = match_zone(
            city="  Dhaka  ", postcode=""
        )
        self.assertEqual(zone, self.zone_dhaka)

    def test_postcode_match(self):
        zone = match_zone(
            city="Unknown", postcode="1205"
        )
        self.assertEqual(zone, self.zone_dhaka)

    def test_postcode_match_case_insensitive(self):
        zone = match_zone(
            city="Unknown", postcode="1205"
        )
        self.assertEqual(zone, self.zone_dhaka)

    def test_default_zone_fallback(self):
        zone = match_zone(
            city="Sylhet", postcode="3100"
        )
        self.assertEqual(zone, self.zone_default)

    def test_no_match_returns_default(self):
        zone = match_zone(
            city="", postcode=""
        )
        self.assertEqual(zone, self.zone_default)

    def test_no_match_returns_none_when_no_default(self):
        self.zone_default.is_default = False
        self.zone_default.save()
        zone = match_zone(
            city="Sylhet", postcode="3100"
        )
        self.assertIsNone(zone)

    def test_inactive_zone_not_matched(self):
        self.zone_dhaka.is_active = False
        self.zone_dhaka.save()
        zone = match_zone(
            city="Dhaka", postcode=""
        )
        self.assertEqual(zone, self.zone_default)

    def test_deleted_zone_not_matched(self):
        self.zone_dhaka.soft_delete()
        zone = match_zone(
            city="Dhaka", postcode=""
        )
        self.assertEqual(zone, self.zone_default)

    def test_postcode_priority_over_city(self):
        """Postcode match takes priority over city."""
        zone_sylhet = ShippingZone.objects.create(
            name="Sylhet", code="sylhet"
        )
        ShippingZoneRule.objects.create(
            zone=zone_sylhet,
            match_type=(
                ShippingZoneRule.MatchType.POSTCODE
            ),
            match_value="3100",
        )
        # City matches Dhaka, postcode matches Sylhet
        zone = match_zone(
            city="Dhaka", postcode="3100"
        )
        self.assertEqual(zone, zone_sylhet)


class ShippingChargeTest(TestCase):
    """Tests for shipping charge calculation."""

    def setUp(self):
        self.zone = ShippingZone.objects.create(
            name="Dhaka", code="dhaka"
        )
        self.method = ShippingMethod.objects.create(
            name="Standard", code="standard"
        )

    def test_base_charge_below_threshold(self):
        rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal("60.00"),
            free_shipping_threshold=(
                decimal.Decimal("1000.00")
            ),
        )
        charge = calculate_shipping_charge(
            rate=rate,
            cart_subtotal=decimal.Decimal("500.00"),
        )
        self.assertEqual(
            charge, decimal.Decimal("60.00")
        )

    def test_free_shipping_at_threshold(self):
        rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal("60.00"),
            free_shipping_threshold=(
                decimal.Decimal("1000.00")
            ),
        )
        charge = calculate_shipping_charge(
            rate=rate,
            cart_subtotal=decimal.Decimal("1000.00"),
        )
        self.assertEqual(
            charge, decimal.Decimal("0.00")
        )

    def test_free_shipping_above_threshold(self):
        rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal("60.00"),
            free_shipping_threshold=(
                decimal.Decimal("1000.00")
            ),
        )
        charge = calculate_shipping_charge(
            rate=rate,
            cart_subtotal=decimal.Decimal("1500.00"),
        )
        self.assertEqual(
            charge, decimal.Decimal("0.00")
        )

    def test_no_threshold_charges_base(self):
        rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal("60.00"),
            free_shipping_threshold=None,
        )
        charge = calculate_shipping_charge(
            rate=rate,
            cart_subtotal=decimal.Decimal("5000.00"),
        )
        self.assertEqual(
            charge, decimal.Decimal("60.00")
        )


class ShippingOptionsAPITest(TestCase):
    """Tests for GET /api/v1/shipping/options/."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="ship@example.com",
            email="ship@example.com",
            first_name="Ship",
            last_name="Test",
            password="TestPass123!",
        )
        self.profile = CustomerProfile.objects.create(
            user=self.user, customer_type="WEBSITE"
        )
        self.address = CustomerAddress.objects.create(
            customer=self.profile,
            address_type=(
                CustomerAddress.AddressType.SHIPPING
            ),
            first_name="Ship",
            last_name="Test",
            address_1="123 Main St",
            city="Dhaka",
            state="Dhaka",
            postcode="1205",
            country="BD",
        )
        self.zone = ShippingZone.objects.create(
            name="Dhaka", code="dhaka"
        )
        ShippingZoneRule.objects.create(
            zone=self.zone,
            match_type=ShippingZoneRule.MatchType.CITY,
            match_value="Dhaka",
        )
        self.method = ShippingMethod.objects.create(
            name="Standard", code="standard"
        )
        self.rate = ShippingRate.objects.create(
            zone=self.zone,
            method=self.method,
            base_charge=decimal.Decimal("60.00"),
            free_shipping_threshold=(
                decimal.Decimal("1000.00")
            ),
        )
        self.product = Product.objects.create(
            name="Test Product",
            current_selling_price=decimal.Decimal("500.00"),
        )
        self.cart = Cart.objects.create(
            created_by=self.user,
            updated_by=self.user,
        )
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=1,
        )
        self.url = "/api/v1/shipping/options/"

    def test_get_shipping_options(self):
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code, status.HTTP_200_OK
        )
        data = resp.json()
        self.assertEqual(data["zone"]["code"], "dhaka")
        self.assertEqual(len(data["options"]), 1)
        self.assertEqual(
            decimal.Decimal(
                str(data["options"][0]["base_charge"])
            ),
            decimal.Decimal("60.00"),
        )
        self.assertEqual(
            decimal.Decimal(
                str(data["cart_subtotal"])
            ),
            decimal.Decimal("500.00"),
        )
        self.assertFalse(
            data["options"][0]["is_free_shipping"]
        )

    def test_free_shipping_applied(self):
        """Subtotal >= threshold => free shipping."""
        self.cart_item.quantity = 3
        self.cart_item.save()
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code, status.HTTP_200_OK
        )
        data = resp.json()
        self.assertTrue(
            data["options"][0]["is_free_shipping"]
        )
        self.assertEqual(
            decimal.Decimal(
                str(
                    data["options"][0]["shipping_charge"]
                )
            ),
            decimal.Decimal("0.00"),
        )

    def test_requires_authentication(self):
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_requires_address_id(self):
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_other_user_address_rejected(self):
        other = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="TestPass123!",
        )
        other_profile = (
            CustomerProfile.objects.create(
                user=other, customer_type="WEBSITE"
            )
        )
        other_addr = CustomerAddress.objects.create(
            customer=other_profile,
            address_type=(
                CustomerAddress.AddressType.SHIPPING
            ),
            city="Dhaka",
            postcode="1205",
        )
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": other_addr.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_billing_address_rejected(self):
        billing = CustomerAddress.objects.create(
            customer=self.profile,
            address_type=(
                CustomerAddress.AddressType.BILLING
            ),
            city="Dhaka",
            postcode="1205",
        )
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": billing.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_inactive_address_rejected(self):
        self.address.is_active = False
        self.address.save()
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_deleted_address_rejected(self):
        self.address.soft_delete()
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_no_active_cart(self):
        self.cart.status = CartStatus.CHECKED_OUT
        self.cart.save()
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_no_matching_zone(self):
        self.zone.delete()
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_inactive_method_excluded(self):
        self.method.is_active = False
        self.method.save()
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_multiple_methods(self):
        express = ShippingMethod.objects.create(
            name="Express", code="express"
        )
        ShippingRate.objects.create(
            zone=self.zone,
            method=express,
            base_charge=decimal.Decimal("120.00"),
        )
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {"address_id": self.address.id},
        )
        self.assertEqual(
            resp.status_code, status.HTTP_200_OK
        )
        data = resp.json()
        self.assertEqual(len(data["options"]), 2)

    def test_frontend_subtotal_ignored(self):
        """Backend recalculates subtotal."""
        self.client.force_authenticate(
            user=self.user
        )
        resp = self.client.get(
            self.url,
            {
                "address_id": self.address.id,
                "subtotal": "9999.99",
            },
        )
        self.assertEqual(
            resp.status_code, status.HTTP_200_OK
        )
        data = resp.json()
        self.assertEqual(
            decimal.Decimal(
                str(data["cart_subtotal"])
            ),
            decimal.Decimal("500.00"),
        )

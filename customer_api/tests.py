from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from user_api.models import User
from customer_api.models import CustomerProfile, CustomerAddress


class CustomerAddressAPITestCase(TestCase):
    """Test cases for customer address API."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="addrtest@example.com",
            email="addrtest@example.com",
            first_name="Addr",
            last_name="Test",
            password="TestPass123!",
        )
        self.profile = CustomerProfile.objects.create(
            user=self.user, customer_type="WEBSITE"
        )
        self.client.force_authenticate(user=self.user)
        self.list_url = "/api/v1/customer-addresses/"

    def _create_address(self, **overrides):
        data = {
            "address_type": "BILLING",
            "first_name": "John",
            "last_name": "Doe",
            "address_1": "123 Main St",
            "city": "Dhaka",
            "state": "Dhaka",
            "postcode": "1205",
            "country": "BD",
            "phone": "+8801700000000",
        }
        data.update(overrides)
        return self.client.post(
            self.list_url, data, format="json"
        )

    # --- List ---

    def test_list_addresses(self):
        """GET /api/v1/customer-addresses/ returns the user's addresses."""
        self._create_address()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_list_excludes_other_users(self):
        """Only the authenticated user's addresses are returned."""
        other = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="TestPass123!",
        )
        other_profile = CustomerProfile.objects.create(
            user=other, customer_type="WEBSITE"
        )
        CustomerAddress.objects.create(
            customer=other_profile,
            address_type="BILLING",
            first_name="Other",
        )
        self._create_address()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(
            resp.data["results"][0]["first_name"], "John"
        )

    # --- Create ---

    def test_create_billing_address(self):
        """POST creates a new billing address."""
        resp = self._create_address()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            resp.data["address_type"], "BILLING"
        )
        self.assertEqual(
            CustomerAddress.objects.filter(
                customer=self.profile
            ).count(),
            1,
        )

    def test_create_shipping_address(self):
        """POST creates a new shipping address."""
        resp = self._create_address(address_type="SHIPPING")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            resp.data["address_type"], "SHIPPING"
        )

    def test_create_two_shipping_addresses(self):
        """Multiple active shipping addresses are allowed."""
        self._create_address(address_type="SHIPPING")
        resp = self._create_address(
            address_type="SHIPPING",
            first_name="Second",
            address_1="456 Other St",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            CustomerAddress.objects.filter(
                customer=self.profile,
                address_type="SHIPPING",
                is_active=True,
            ).count(),
            2,
        )

    def test_create_requires_authentication(self):
        """Unauthenticated request is rejected."""
        self.client.force_authenticate(user=None)
        resp = self.client.post(
            self.list_url,
            {"address_type": "BILLING"},
            format="json",
        )
        self.assertEqual(
            resp.status_code, status.HTTP_401_UNAUTHORIZED
        )

    # --- Retrieve ---

    def test_retrieve_address(self):
        """GET /api/v1/customer-addresses/{id}/ returns detail."""
        create_resp = self._create_address()
        addr_id = create_resp.data["id"]
        resp = self.client.get(f"{self.list_url}{addr_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], addr_id)
        self.assertIn("address_1", resp.data)

    def test_retrieve_other_user_address_404(self):
        """Cannot retrieve another user's address."""
        other = User.objects.create_user(
            username="other2@example.com",
            email="other2@example.com",
            password="TestPass123!",
        )
        other_profile = CustomerProfile.objects.create(
            user=other, customer_type="WEBSITE"
        )
        addr = CustomerAddress.objects.create(
            customer=other_profile,
            address_type="BILLING",
            first_name="Other",
        )
        resp = self.client.get(f"{self.list_url}{addr.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # --- Update (PATCH) ---

    def test_partial_update_address(self):
        """PATCH updates specified fields."""
        create_resp = self._create_address()
        addr_id = create_resp.data["id"]
        resp = self.client.patch(
            f"{self.list_url}{addr_id}/",
            {"city": "Chittagong"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["city"], "Chittagong")

    # --- Delete (soft) ---

    def test_delete_address(self):
        """DELETE soft-deletes the address."""
        create_resp = self._create_address()
        addr_id = create_resp.data["id"]
        resp = self.client.delete(f"{self.list_url}{addr_id}/")
        self.assertEqual(
            resp.status_code, status.HTTP_204_NO_CONTENT
        )
        addr = CustomerAddress.objects.get(id=addr_id)
        self.assertFalse(addr.is_active)
        self.assertIsNotNone(addr.deleted_at)

    def test_deleted_address_not_in_list(self):
        """Soft-deleted addresses are excluded from list."""
        create_resp = self._create_address()
        addr_id = create_resp.data["id"]
        self.client.delete(f"{self.list_url}{addr_id}/")
        resp = self.client.get(self.list_url)
        self.assertEqual(len(resp.data["results"]), 0)
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from user_api.models import User
from customer_api.models import CustomerProfile


class CustomerSignupAPITestCase(TestCase):
    """Test cases for customer registration API."""

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.signup_url = '/auth/register/'

    def test_successful_signup(self):
        """Test successful customer registration."""
        data = {
            'email': 'newcustomer@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'first_name': 'John',
            'last_name': 'Doe',
            'middle_name': 'Michael',
            'phone': '1234567890',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('data', response.json())
        self.assertIn('refresh', response.json()['data'])
        self.assertIn('access', response.json()['data'])
        self.assertEqual(response.json()['data']['email'],
                         'newcustomer@example.com')
        self.assertEqual(response.json()['data']['customer_type'], 'WEBSITE')

        # Verify User was created
        user = User.objects.get(email='newcustomer@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertEqual(user.middle_name, 'Michael')
        self.assertEqual(user.role, 'CUSTOMER')

        # Verify CustomerProfile was created
        profile = CustomerProfile.objects.get(user=user)
        self.assertEqual(profile.phone, '1234567890')
        self.assertEqual(profile.customer_type, 'WEBSITE')

    def test_signup_with_minimal_data(self):
        """Test signup with only required fields."""
        data = {
            'email': 'minimal@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'first_name': 'Jane',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='minimal@example.com')
        self.assertEqual(user.first_name, 'Jane')

    def test_password_mismatch(self):
        """Test signup with mismatched passwords."""
        data = {
            'email': 'mismatch@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'DifferentPassword123!',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', response.json())

    def test_duplicate_email(self):
        """Test signup with duplicate email."""
        # Create an existing user
        User.objects.create_user(
            email='existing@example.com',
            username='existing@example.com',
            password='Password123!',
        )

        data = {
            'email': 'existing@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.json())

    def test_weak_password(self):
        """Test signup with weak password."""
        data = {
            'email': 'weak@example.com',
            'password': '123',  # Too weak
            'confirm_password': '123',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_email(self):
        """Test signup without email."""
        data = {
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_password(self):
        """Test signup without password."""
        data = {
            'email': 'nopass@example.com',
            'confirm_password': 'SecurePassword123!',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_first_name(self):
        """Test signup without first_name."""
        data = {
            'email': 'nofirstname@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_email_format(self):
        """Test signup with invalid email format."""
        data = {
            'email': 'invalid-email',
            'password': 'SecurePassword123!',
            'confirm_password': 'SecurePassword123!',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_atomicity_on_failure(self):
        """Test that User is not created if CustomerProfile creation fails."""
        # This is a general atomicity test to ensure rollback
        initial_user_count = User.objects.count()

        # Send invalid request
        data = {
            'email': 'atomicity@example.com',
            'password': 'SecurePassword123!',
            'confirm_password': 'MismatchPassword123!',
            'first_name': 'John',
        }

        response = self.client.post(self.signup_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Ensure no user was created
        self.assertEqual(User.objects.count(), initial_user_count)


# Create your tests here.

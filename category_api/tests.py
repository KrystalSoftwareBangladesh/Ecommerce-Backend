from django.test import TestCase
from rest_framework.test import APITestCase

from category_api.models import Category
from user_api.models import User


class CategoryApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='category-staff',
            email='category-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.client.force_authenticate(user=self.user)

    def test_create_category_allows_null_slug(self):
        response = self.client.post(
            '/api/v1/categories/',
            {
                'name': 'Electronics',
                'description': 'Gadgets and devices',
                'slug': None,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        category = Category.objects.get(pk=response.data['id'])
        self.assertEqual(category.name, 'Electronics')
        self.assertEqual(category.slug, 'electronics')
        self.assertEqual(response.data['slug'], 'electronics')

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

    def test_summary_returns_category_statistics(self):
        root_in_menu = Category.objects.create(
            name='Electronics',
            show_in_menu=True,
        )
        root_not_in_menu = Category.objects.create(name='Books')
        Category.objects.create(
            name='Phones',
            parent=root_in_menu,
            show_in_menu=True,
        )
        # Inactive categories are still counted; only deleted ones are not.
        Category.objects.create(
            name='Laptops',
            parent=root_in_menu,
            is_active=False,
        )
        deleted_child = Category.objects.create(
            name='Tablets',
            parent=root_not_in_menu,
            show_in_menu=True,
        )
        deleted_child.soft_delete()

        response = self.client.get('/api/v1/categories/summary/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'total_categories': 4,
            'root_categories': 2,
            'sub_categories': 2,
            'menu_categories': 1,
            'sub_menu_categories': 1,
        })

    def test_summary_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get('/api/v1/categories/summary/')

        self.assertEqual(response.status_code, 401)

    def test_create_category_without_slug_generates_slug(self):
        response = self.client.post(
            '/api/v1/categories/',
            {
                'name': 'Home Appliances',
                'description': 'Kitchen and household goods',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        category = Category.objects.get(pk=response.data['id'])
        self.assertEqual(category.name, 'Home Appliances')
        self.assertEqual(category.slug, 'home-appliances')
        self.assertEqual(response.data['slug'], 'home-appliances')

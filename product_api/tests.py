from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from product_api.models import Product, ProductVariant


class ProductVariantApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='tester',
            password='secret123'
        )
        self.client.force_authenticate(user=self.user)
        self.product = Product.objects.create(
            name='Sample Product',
            current_selling_price='10.00',
            slug='sample-product'
        )

    def test_create_variant_allows_null_name(self):
        response = self.client.post(
            '/api/v1/product-variants/',
            {
                'product': self.product.id,
                'sku': 'SKU-001',
                'name': None,
            },
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['name'])
        self.assertTrue(
            ProductVariant.objects.filter(pk=response.data['id']).exists()
        )
        self.assertIsNone(
            ProductVariant.objects.get(pk=response.data['id']).name
        )

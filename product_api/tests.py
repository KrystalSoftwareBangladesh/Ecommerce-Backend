from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from category_api.models import Category
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

    def test_list_product_variants_by_product(self):
        ProductVariant.objects.create(
            product=self.product,
            sku='SKU-001',
            name='Blue Variant'
        )
        ProductVariant.objects.create(
            product=self.product,
            sku='SKU-002',
            name='Red Variant'
        )

        response = self.client.get(
            f'/api/v1/products/{self.product.id}/product-variants/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)

    def test_list_variants_endpoint_works(self):
        ProductVariant.objects.create(
            product=self.product,
            sku='SKU-001',
            name='Blue Variant'
        )

        response = self.client.get('/api/v1/product-variants/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['sku'], 'SKU-001')

    def test_list_products_filters_by_multiple_categories(self):
        category_one = Category.objects.create(name='Category One', slug='category-one')
        category_two = Category.objects.create(name='Category Two', slug='category-two')
        category_three = Category.objects.create(name='Category Three', slug='category-three')

        matching_product = Product.objects.create(
            name='Filtered Product',
            current_selling_price='15.00',
            slug='filtered-product'
        )
        matching_product.categories.add(category_one, category_two)

        other_product = Product.objects.create(
            name='Other Product',
            current_selling_price='20.00',
            slug='other-product'
        )
        other_product.categories.add(category_three)

        response = self.client.get(
            f'/api/v1/products/?categories={category_one.id}&categories={category_two.id}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Filtered Product')

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image as PilImage
from rest_framework import status
from rest_framework.test import APIClient

from category_api.models import Category
from product_api.models import Product, ProductVariant, ProductImage
from product_api.services import (
    reorder_product_images,
    replace_product_image,
    set_product_image_default,
    soft_delete_product_image,
    upload_product_image,
)


class ProductVariantApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='tester@example.com',
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


class ProductWriteSerializerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='writer@example.com',
            username='writer',
            password='secret123',
        )
        self.client.force_authenticate(user=self.user)

    def _create_product(self, name='Widget', price='10.00'):
        return Product.objects.create(
            name=name,
            current_selling_price=price,
            slug=name.lower(),
        )

    def test_create_accepts_variants(self):
        response = self.client.post(
            '/api/v1/products/',
            {
                'name': 'Widget',
                'current_selling_price': '10.00',
                'variants': [{'sku': 'W-1'}, {'sku': 'W-2'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product = Product.objects.get(name='Widget')
        self.assertEqual(product.variants.count(), 2)
        self.assertEqual(len(response.data['variants']), 2)

    def test_create_records_initial_price_history(self):
        response = self.client.post(
            '/api/v1/products/',
            {'name': 'Widget', 'current_selling_price': '10.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        product = Product.objects.get(name='Widget')
        self.assertEqual(product.price_histories.count(), 1)

    def test_create_rejects_duplicate_skus_in_one_payload(self):
        response = self.client.post(
            '/api/v1/products/',
            {
                'name': 'Widget',
                'current_selling_price': '10.00',
                'variants': [{'sku': 'SAME'}, {'sku': 'SAME'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variants', response.data['errors'])
        self.assertFalse(Product.objects.filter(name='Widget').exists())
        self.assertEqual(ProductVariant.objects.filter(sku='SAME').count(), 0)

    def test_create_rejects_duplicate_skus_case_insensitively(self):
        response = self.client.post(
            '/api/v1/products/',
            {
                'name': 'Widget',
                'current_selling_price': '10.00',
                'variants': [{'sku': 'same'}, {'sku': 'SAME'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variants', response.data['errors'])

    def test_update_with_variants_is_rejected_not_a_server_error(self):
        product = self._create_product()
        ProductVariant.objects.create(product=product, sku='W-1')

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'variants': [{'sku': 'W-2'}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variants', response.data['errors'])
        self.assertEqual(product.variants.count(), 1)

    def test_update_returns_variants_read_only(self):
        product = self._create_product()
        ProductVariant.objects.create(product=product, sku='W-1')

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'name': 'Renamed Widget'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['variants']), 1)
        self.assertEqual(response.data['variants'][0]['sku'], 'W-1')

    def test_update_excludes_inactive_variants_from_response(self):
        product = self._create_product()
        ProductVariant.objects.create(product=product, sku='W-1')
        ProductVariant.objects.create(
            product=product, sku='W-2', is_active=False)

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'name': 'Renamed Widget'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['variants']), 1)

    def test_update_records_price_history_on_change(self):
        product = self._create_product()

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'current_selling_price': '20.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(product.price_histories.count(), 1)
        self.assertEqual(
            str(product.price_histories.first().price), '20.00')

    def test_update_skips_price_history_when_price_unchanged(self):
        product = self._create_product()

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'name': 'Renamed Widget'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(product.price_histories.count(), 0)

    def test_update_sets_categories(self):
        product = self._create_product()
        category = Category.objects.create(name='Gadgets')

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'categories': [category.pk]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(list(product.categories.all()), [category])

    def test_update_leaves_categories_untouched_when_omitted(self):
        product = self._create_product()
        category = Category.objects.create(name='Gadgets')
        product.categories.set([category])

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'name': 'Renamed Widget'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(list(product.categories.all()), [category])

    def test_duplicate_name_is_rejected_on_create(self):
        self._create_product(name='Widget')

        response = self.client.post(
            '/api/v1/products/',
            {'name': 'widget', 'current_selling_price': '10.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data['errors'])

    def test_product_can_keep_its_own_name_on_update(self):
        product = self._create_product(name='Widget')

        response = self.client.patch(
            f'/api/v1/products/{product.pk}/',
            {'name': 'Widget', 'current_selling_price': '11.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProductImageApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='image_tester@example.com',
            username='image_tester',
            password='secret123',
        )
        self.client.force_authenticate(user=self.user)
        self.product = Product.objects.create(
            name='Image Product',
            current_selling_price='10.00',
            slug='image-product',
        )

    def _create_test_image(self, filename='test.png', fmt='PNG'):
        buffer = BytesIO()
        image = PilImage.new('RGB', (100, 100), color=(255, 0, 0))
        image.save(buffer, format=fmt)
        buffer.seek(0)
        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type='image/png' if fmt == 'PNG' else 'image/jpeg',
        )

    def test_upload_image_creates_image_and_marks_default(self):
        response = self.client.post(
            '/api/v1/product-images/',
            {
                'product': self.product.id,
                'image': self._create_test_image(),
                'alt_text': 'Front view',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ProductImage.objects.count(), 1)
        image = ProductImage.objects.get(pk=response.data['id'])
        self.assertTrue(image.is_default)
        self.assertEqual(image.alt_text, 'Front view')

    def test_retrieve_and_list_images(self):
        ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='First image',
            display_order=1,
            is_default=True,
        )
        ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('second.png'),
            alt_text='Second image',
            display_order=2,
        )

        list_response = self.client.get('/api/v1/product-images/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data['count'], 2)

        retrieve_response = self.client.get(
            f"/api/v1/product-images/{ProductImage.objects.first().id}/"
        )
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data['alt_text'], 'First image')

    def test_update_metadata_works(self):
        image = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='Old alt',
            display_order=1,
            is_default=True,
        )

        response = self.client.patch(
            f'/api/v1/product-images/{image.id}/',
            {'alt_text': 'Updated alt'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        image.refresh_from_db()
        self.assertEqual(image.alt_text, 'Updated alt')

    def test_patch_is_default_unsets_other_defaults(self):
        first = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='First',
            display_order=1,
            is_default=True,
        )
        second = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('second.png'),
            alt_text='Second',
            display_order=2,
        )

        response = self.client.patch(
            f'/api/v1/product-images/{second.id}/',
            {'is_default': True},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_replace_image_preserves_metadata_and_flags(self):
        image = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='Original alt',
            display_order=3,
            is_default=True,
        )
        original_name = image.image.name

        response = self.client.post(
            f'/api/v1/product-images/{image.id}/replace-image/',
            {'image': self._create_test_image('replacement.png')},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        image.refresh_from_db()
        self.assertEqual(image.alt_text, 'Original alt')
        self.assertTrue(image.is_default)
        self.assertEqual(image.display_order, 3)
        self.assertNotEqual(image.image.name, original_name)

    def test_set_default_image_updates_previous_default(self):
        first = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='First',
            display_order=1,
            is_default=True,
        )
        second = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('second.png'),
            alt_text='Second',
            display_order=2,
        )

        response = self.client.post(
            f'/api/v1/product-images/{second.id}/set-default/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_reorder_images_keeps_display_order_sequential(self):
        first = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='First',
            display_order=1,
        )
        second = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('second.png'),
            alt_text='Second',
            display_order=2,
        )
        third = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('third.png'),
            alt_text='Third',
            display_order=3,
        )

        response = self.client.post(
            f'/api/v1/product-images/{third.id}/reorder/',
            {'display_order': 1},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual([first.display_order, second.display_order, third.display_order], [2, 3, 1])

    def test_soft_delete_image_removes_it_from_active_listing(self):
        image = ProductImage.objects.create(
            product=self.product,
            image=self._create_test_image('first.png'),
            alt_text='First',
            display_order=1,
            is_default=True,
        )

        response = self.client.delete(f'/api/v1/product-images/{image.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProductImage.objects.get(pk=image.pk).is_active)
        self.assertEqual(
            ProductImage.objects.filter(is_active=True).count(),
            0,
        )


class ProductImageBusinessRuleTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Business Product',
            current_selling_price='15.00',
            slug='business-product',
        )

    def _create_test_image(self, filename='test.png'):
        buffer = BytesIO()
        image = PilImage.new('RGB', (100, 100), color=(255, 0, 0))
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type='image/png',
        )

    def test_first_uploaded_image_becomes_default(self):
        image = upload_product_image(self.product, self._create_test_image())
        self.assertTrue(image.is_default)

    def test_uploading_additional_images_does_not_change_existing_default(self):
        first = upload_product_image(self.product, self._create_test_image('first.png'))
        second = upload_product_image(self.product, self._create_test_image('second.png'))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

    def test_setting_another_image_as_default_removes_previous_default(self):
        first = upload_product_image(self.product, self._create_test_image('first.png'))
        second = upload_product_image(self.product, self._create_test_image('second.png'))
        set_product_image_default(second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_deleting_default_image_promotes_next_available_image(self):
        first = upload_product_image(self.product, self._create_test_image('first.png'))
        second = upload_product_image(self.product, self._create_test_image('second.png'))
        soft_delete_product_image(first)
        second.refresh_from_db()
        self.assertTrue(second.is_default)

    def test_reordering_keeps_display_order_sequential(self):
        first = upload_product_image(self.product, self._create_test_image('first.png'))
        second = upload_product_image(self.product, self._create_test_image('second.png'))
        third = upload_product_image(self.product, self._create_test_image('third.png'))
        reorder_product_images(self.product, third.id, 1)
        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(
            [first.display_order, second.display_order, third.display_order],
            [2, 3, 1],
        )

    def test_delete_keeps_display_order_sequential(self):
        first = upload_product_image(self.product, self._create_test_image('first.png'))
        second = upload_product_image(self.product, self._create_test_image('second.png'))
        third = upload_product_image(self.product, self._create_test_image('third.png'))
        soft_delete_product_image(second)
        first.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual([first.display_order, third.display_order], [1, 2])

    def test_setting_default_via_service_unsets_previous_default(self):
        first = upload_product_image(self.product, self._create_test_image('first.png'))
        second = upload_product_image(self.product, self._create_test_image('second.png'))
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

        set_product_image_default(second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)


class ProductImageValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='image_validator@example.com',
            username='image_validator',
            password='secret123',
        )
        self.client.force_authenticate(user=self.user)
        self.product = Product.objects.create(
            name='Validation Product',
            current_selling_price='10.00',
            slug='validation-product',
        )

    def test_large_file_is_rejected(self):
        large_file = SimpleUploadedFile(
            'large.png',
            b'x' * (1024 * 1024 + 1),
            content_type='image/png',
        )
        response = self.client.post(
            '/api/v1/product-images/',
            {
                'product': self.product.id,
                'image': large_file,
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_file_type_is_rejected(self):
        response = self.client.post(
            '/api/v1/product-images/',
            {
                'product': self.product.id,
                'image': SimpleUploadedFile(
                    'test.txt',
                    b'hello world',
                    content_type='text/plain',
                ),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_image_types_are_accepted(self):
        buffer = BytesIO()
        image = PilImage.new('RGB', (100, 100), color=(255, 0, 0))
        image.save(buffer, format='JPEG')
        buffer.seek(0)

        response = self.client.post(
            '/api/v1/product-images/',
            {
                'product': self.product.id,
                'image': SimpleUploadedFile(
                    'test.jpg',
                    buffer.getvalue(),
                    content_type='image/jpeg',
                ),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class ProductImagePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email='image_permissions@example.com',
            username='image_permissions',
            password='secret123',
        )
        self.product = Product.objects.create(
            name='Permission Product',
            current_selling_price='10.00',
            slug='permission-product',
        )

    def test_public_can_read_images(self):
        image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile(
                'test.png',
                b'fake-bytes',
                content_type='image/png',
            ),
            alt_text='Read',
            display_order=1,
            is_default=True,
        )

        list_response = self.client.get('/api/v1/product-images/')
        retrieve_response = self.client.get(
            f'/api/v1/product-images/{image.id}/'
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_create_update_delete_are_rejected(self):
        create_response = self.client.post(
            '/api/v1/product-images/',
            {'product': self.product.id, 'image': SimpleUploadedFile('test.png', b'fake', content_type='image/png')},
            format='multipart',
        )
        self.assertEqual(create_response.status_code, status.HTTP_401_UNAUTHORIZED)

        image = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile(
                'test.png',
                b'fake-bytes',
                content_type='image/png',
            ),
            alt_text='Delete',
            display_order=1,
            is_default=True,
        )

        update_response = self.client.patch(
            f'/api/v1/product-images/{image.id}/',
            {'alt_text': 'Updated'},
            format='json',
        )
        self.assertEqual(update_response.status_code, status.HTTP_401_UNAUTHORIZED)

        delete_response = self.client.delete(f'/api/v1/product-images/{image.id}/')
        self.assertEqual(delete_response.status_code, status.HTTP_401_UNAUTHORIZED)

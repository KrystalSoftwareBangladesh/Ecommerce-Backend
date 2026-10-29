from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from rest_framework.test import APITestCase

from blog_api.models import BlogPost, BlogPostStatus
from category_api.models import Category
from product_api.models import Brand, Product
from user_api.models import User

from meta_api.services import get_sitemap_urls


SITEMAP_URL = '/api/v1/seo/sitemap-urls/'
SECTIONS = ['products', 'categories', 'brands', 'blogs']


def slugs(response, section):
    return [item['slug'] for item in response.data[section]]


class SitemapUrlsApiTests(APITestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Dell Laptop',
            current_selling_price='10.00',
            slug='dell-laptop',
        )
        self.category = Category.objects.create(
            name='Laptops',
            slug='laptops',
        )
        self.brand = Brand.objects.create(name='Dell', slug='dell')
        self.blog = BlogPost.objects.create(
            title='Laptop Buying Guide',
            slug='laptop-buying-guide',
            status=BlogPostStatus.PUBLISHED,
            published_at=timezone.now(),
        )

    def test_response_has_exact_structure_and_iso_timestamps(self):
        updated_at = datetime(2026, 10, 28, 12, 0, tzinfo=dt_timezone.utc)
        published_at = datetime(2026, 10, 26, 8, 0, tzinfo=dt_timezone.utc)
        Product.objects.filter(pk=self.product.pk).update(
            updated_at=updated_at,
        )
        BlogPost.objects.filter(pk=self.blog.pk).update(
            published_at=published_at,
        )

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.json().keys()), SECTIONS)
        for section in SECTIONS:
            self.assertEqual(len(response.data[section]), 1)
            item = response.data[section][0]
            self.assertEqual(set(item.keys()), {'slug', 'lastmod'})
            parsed = datetime.fromisoformat(item['lastmod'])
            self.assertIsNotNone(parsed.tzinfo)

        self.assertEqual(
            response.json()['products'],
            [{'slug': 'dell-laptop', 'lastmod': '2026-10-28T12:00:00Z'}],
        )
        self.assertEqual(
            response.json()['blogs'],
            [{
                'slug': 'laptop-buying-guide',
                'lastmod': '2026-10-26T08:00:00Z',
            }],
        )

    def test_lastmod_uses_updated_at_and_published_at(self):
        response = self.client.get(SITEMAP_URL)

        for section, instance, field in [
            ('products', self.product, 'updated_at'),
            ('categories', self.category, 'updated_at'),
            ('brands', self.brand, 'updated_at'),
            ('blogs', self.blog, 'published_at'),
        ]:
            instance.refresh_from_db()
            self.assertEqual(
                datetime.fromisoformat(
                    response.data[section][0]['lastmod']
                ),
                getattr(instance, field),
            )

    def test_empty_results_keep_every_key_as_an_empty_list(self):
        Product.objects.all().delete()
        Category.objects.all().delete()
        Brand.objects.all().delete()
        BlogPost.objects.all().delete()

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {section: [] for section in SECTIONS},
        )

    def test_products_exclude_inactive_and_soft_deleted(self):
        Product.objects.create(
            name='Inactive', current_selling_price='1.00',
            slug='inactive-product', is_active=False,
        )
        Product.objects.create(
            name='Deleted', current_selling_price='1.00',
            slug='deleted-product', deleted_at=timezone.now(),
        )

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(slugs(response, 'products'), ['dell-laptop'])

    def test_categories_exclude_inactive_deleted_and_slugless(self):
        Category.objects.create(
            name='Inactive', slug='inactive-category', is_active=False,
        )
        Category.objects.create(
            name='Deleted', slug='deleted-category',
            deleted_at=timezone.now(),
        )
        empty = Category.objects.create(name='Empty Slug')
        null = Category.objects.create(name='Null Slug')
        Category.objects.filter(pk=empty.pk).update(slug='')
        Category.objects.filter(pk=null.pk).update(slug=None)

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(slugs(response, 'categories'), ['laptops'])

    def test_brands_exclude_inactive_deleted_and_slugless(self):
        Brand.objects.create(
            name='Inactive', slug='inactive-brand', is_active=False,
        )
        Brand.objects.create(
            name='Deleted', slug='deleted-brand',
            deleted_at=timezone.now(),
        )
        empty = Brand.objects.create(name='Empty Slug')
        Brand.objects.filter(pk=empty.pk).update(slug='')

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(slugs(response, 'brands'), ['dell'])

    def test_blogs_include_only_indexable_published_posts(self):
        now = timezone.now()
        BlogPost.objects.create(title='Draft', slug='draft-post')
        BlogPost.objects.create(
            title='Inactive', slug='inactive-post', is_active=False,
            status=BlogPostStatus.PUBLISHED, published_at=now,
        )
        BlogPost.objects.create(
            title='Deleted', slug='deleted-post', deleted_at=now,
            status=BlogPostStatus.PUBLISHED, published_at=now,
        )
        BlogPost.objects.create(
            title='Noindex', slug='noindex-post', seo_noindex=True,
            status=BlogPostStatus.PUBLISHED, published_at=now,
        )
        empty = BlogPost.objects.create(
            title='Empty Slug',
            status=BlogPostStatus.PUBLISHED, published_at=now,
        )
        BlogPost.objects.filter(pk=empty.pk).update(slug='')

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(slugs(response, 'blogs'), ['laptop-buying-guide'])

    def test_is_not_paginated(self):
        for index in range(15):
            Product.objects.create(
                name=f'Product {index}', current_selling_price='1.00',
                slug=f'product-{index}',
            )

        response = self.client.get(SITEMAP_URL)

        self.assertNotIn('results', response.data)
        self.assertEqual(len(response.data['products']), 16)

    def test_anonymous_access_is_allowed(self):
        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.status_code, 200)

    def test_authenticated_access_is_allowed(self):
        user = User.objects.create_user(
            username='sitemap-user',
            email='sitemap-user@example.com',
            password='test-pass-123',
        )
        self.client.force_authenticate(user=user)

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.status_code, 200)

    def test_invalid_token_is_ignored(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-token')

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.status_code, 200)

    def test_write_methods_are_not_allowed(self):
        for method in ['post', 'put', 'patch', 'delete']:
            response = getattr(self.client, method)(SITEMAP_URL, {})
            self.assertEqual(response.status_code, 405, method)

    def test_service_runs_one_query_per_content_type(self):
        with self.assertNumQueries(4):
            get_sitemap_urls()

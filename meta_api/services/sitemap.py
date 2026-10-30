# meta_api/services/sitemap.py
from django.db.models import F

from blog_api.models import BlogPost, BlogPostStatus
from category_api.models import Category
from product_api.models import Brand, Product


def _sitemap_entries(queryset, lastmod_field):
    """
    One query per content type: only `slug` and the lastmod column are
    read, so the cost does not grow with related data.
    """
    return list(
        queryset
        .annotate(lastmod=F(lastmod_field))
        .order_by('id')
        .values('slug', 'lastmod')
    )


def get_sitemap_urls():
    """
    Slugs and last-modified timestamps of every publicly indexable
    product, category, brand and blog post, for the storefront sitemap.
    """
    products = Product.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
    )
    categories = Category.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
        slug__isnull=False,
    ).exclude(slug='')
    brands = Brand.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
    ).exclude(slug='')
    blogs = BlogPost.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
        status=BlogPostStatus.PUBLISHED,
        published_at__isnull=False,
        seo_noindex=False,
    ).exclude(slug='')

    return {
        'products': _sitemap_entries(products, 'updated_at'),
        'categories': _sitemap_entries(categories, 'updated_at'),
        'brands': _sitemap_entries(brands, 'updated_at'),
        'blogs': _sitemap_entries(blogs, 'published_at'),
    }

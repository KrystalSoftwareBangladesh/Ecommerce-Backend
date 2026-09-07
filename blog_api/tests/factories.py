# blog_api/tests/factories.py
"""
Small builders for the blog test suite.

Deliberately thin: they call `Model.objects.create(...)` the way the rest
of the repository's tests do, and only exist so a test can say what it
cares about and stay silent about the rest.
"""
import io

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from PIL import Image

from category_api.models import Category
from user_api.models import User

from blog_api.models import BlogPost, BlogPostStatus, BlogTag


def user(username, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='test-pass-123',
        **kwargs,
    )


def superuser(username='blog-admin'):
    return User.objects.create_superuser(
        username=username,
        email=f'{username}@example.com',
        password='test-pass-123',
    )


def grant(target, model, *codenames):
    """
    Give a user the named permissions on `model` and return a freshly
    loaded user so Django's permission cache is not stale.
    """
    content_type = ContentType.objects.get_for_model(model)

    for codename in codenames:
        target.user_permissions.add(
            Permission.objects.get(
                content_type=content_type,
                codename=codename,
            )
        )

    return User.objects.get(pk=target.pk)


def category(name='Skincare', **kwargs):
    return Category.objects.create(name=name, **kwargs)


def tag(name='Routine', **kwargs):
    return BlogTag.objects.create(name=name, **kwargs)


def post(title='A first post', published=False, **kwargs):
    kwargs.setdefault('content', '<p>Body</p>')

    if published:
        kwargs.setdefault('status', BlogPostStatus.PUBLISHED)
        kwargs.setdefault('published_at', timezone.now())

    categories = kwargs.pop('categories', None)
    tags = kwargs.pop('tags', None)

    instance = BlogPost.objects.create(title=title, **kwargs)

    if categories:
        instance.categories.set(categories)

    if tags:
        instance.tags.set(tags)

    return instance


def image_file(name='featured.png'):
    """An in-memory PNG, the way `product_api` builds one."""
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')

    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type='image/png',
    )

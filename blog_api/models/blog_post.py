# blog_api/models/blog_post.py
from django.db import models
from django.utils.text import slugify

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from category_api.models import Category
from user_api.models import User

from .blog_tag import BlogTag
from .choices import BlogPostStatus


class BlogPost(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    """
    A single piece of editorial content.

    `content` holds HTML and is stored verbatim; the blog does not own a
    markup format. Categories are the shared `Category` tree, so the
    storefront and the blog stay on one taxonomy.
    """
    title = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
    )
    content = models.TextField(
        blank=True,
        default='',
        help_text='Post body as HTML.',
    )
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_posts',
    )
    status = models.CharField(
        max_length=20,
        choices=BlogPostStatus.choices,
        default=BlogPostStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )
    featured_image = models.ImageField(
        upload_to='blog/featured-images/',
        max_length=500,
        blank=True,
        null=True,
    )
    featured_image_alt_text = models.CharField(
        max_length=255,
        blank=True,
        default='',
    )
    categories = models.ManyToManyField(
        Category,
        related_name='blog_posts',
        blank=True,
    )
    tags = models.ManyToManyField(
        BlogTag,
        related_name='posts',
        blank=True,
    )
    seo_title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Overrides the title in search results. Falls back to '
                  'the post title when empty.',
    )
    seo_description = models.TextField(
        blank=True,
        default='',
        help_text='Meta description shown in search results.',
    )
    seo_focus_keyword = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Primary keyword the post targets.',
    )
    seo_noindex = models.BooleanField(
        default=False,
        help_text='Ask search engines not to index this post.',
    )
    seo_nofollow = models.BooleanField(
        default=False,
        help_text='Ask search engines not to follow links in this post.',
    )
    legacy_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Identifier of this post in the system it was migrated '
                  'from. Set by migration tooling, not by the API.',
    )

    class Meta:
        verbose_name = 'Blog Post'
        verbose_name_plural = 'Blog Posts'
        ordering = ['-published_at', '-created_at']
        permissions = [
            ('publish_blog_post', 'Can publish blog post'),
            ('unpublish_blog_post', 'Can unpublish blog post'),
        ]
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['status', 'published_at']),
            models.Index(fields=['author', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status=BlogPostStatus.PUBLISHED,
                    published_at__isnull=False,
                ) | models.Q(
                    status=BlogPostStatus.DRAFT,
                    published_at__isnull=True,
                ),
                name='blog_post_published_at_matches_status',
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.pk and not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        """Generate a unique slug based on the post title."""
        base_slug = slugify(self.title)
        slug = base_slug
        counter = 1

        qs = BlogPost.objects.filter(slug=slug)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = BlogPost.objects.filter(slug=slug)

        return slug

    @property
    def is_published(self):
        return self.status == BlogPostStatus.PUBLISHED

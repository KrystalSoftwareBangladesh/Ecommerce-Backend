# blog_api/tests/test_models.py
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from blog_api.models import BlogPost, BlogPostStatus, BlogTag
from blog_api.tests import factories


class BlogPostModelTests(TestCase):
    def test_creating_a_post_stores_html_content_verbatim(self):
        html = '<p>Hello <strong>world</strong></p>'

        post = factories.post(title='Hello', content=html)

        self.assertEqual(post.content, html)

    def test_slug_is_generated_from_the_title(self):
        post = factories.post(title='A First Post')

        self.assertEqual(post.slug, 'a-first-post')

    def test_slug_is_made_unique_across_posts(self):
        first = factories.post(title='Same Title')
        second = factories.post(title='Same Title')

        self.assertEqual(first.slug, 'same-title')
        self.assertEqual(second.slug, 'same-title-1')

    def test_slug_is_not_regenerated_when_the_title_changes(self):
        post = factories.post(title='Original Title')

        post.title = 'Completely Different Title'
        post.save()
        post.refresh_from_db()

        self.assertEqual(post.slug, 'original-title')

    def test_a_new_post_is_a_draft_without_a_publication_date(self):
        post = factories.post()

        self.assertEqual(post.status, BlogPostStatus.DRAFT)
        self.assertIsNone(post.published_at)
        self.assertFalse(post.is_published)

    def test_featured_image_is_optional(self):
        post = factories.post()

        self.assertFalse(post.featured_image)

    def test_featured_image_can_be_attached(self):
        post = factories.post(featured_image=factories.image_file())

        self.assertIn('blog/featured-images/', post.featured_image.name)

    def test_seo_fields_default_to_empty_and_are_writable(self):
        post = factories.post()

        self.assertEqual(post.seo_title, '')
        self.assertEqual(post.seo_description, '')
        self.assertEqual(post.seo_focus_keyword, '')
        self.assertFalse(post.seo_noindex)
        self.assertFalse(post.seo_nofollow)

        post.seo_title = 'Search title'
        post.seo_description = 'Search description'
        post.seo_focus_keyword = 'keyword'
        post.seo_noindex = True
        post.seo_nofollow = True
        post.save()
        post.refresh_from_db()

        self.assertEqual(post.seo_title, 'Search title')
        self.assertTrue(post.seo_noindex)
        self.assertTrue(post.seo_nofollow)

    def test_a_post_relates_to_an_author_categories_and_tags(self):
        author = factories.user('writer')
        categories = [
            factories.category('Skincare'),
            factories.category('Wellness'),
        ]
        tags = [
            factories.tag('Routine'),
            factories.tag('Tips'),
        ]

        post = factories.post(
            author=author,
            categories=categories,
            tags=tags,
        )

        self.assertEqual(post.author, author)
        self.assertEqual(post.categories.count(), 2)
        self.assertEqual(post.tags.count(), 2)
        self.assertIn(post, author.blog_posts.all())
        self.assertIn(post, categories[0].blog_posts.all())
        self.assertIn(post, tags[0].posts.all())

    def test_legacy_id_is_unique(self):
        factories.post(title='Migrated one', legacy_id=101)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                factories.post(title='Migrated two', legacy_id=101)

    def test_a_published_post_must_carry_a_publication_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BlogPost.objects.create(
                    title='Broken',
                    status=BlogPostStatus.PUBLISHED,
                    published_at=None,
                )

    def test_a_draft_must_not_carry_a_publication_date(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BlogPost.objects.create(
                    title='Broken',
                    status=BlogPostStatus.DRAFT,
                    published_at=timezone.now(),
                )

    def test_soft_delete_marks_the_post_without_removing_it(self):
        post = factories.post()

        post.soft_delete()
        post.refresh_from_db()

        self.assertFalse(post.is_active)
        self.assertIsNotNone(post.deleted_at)
        self.assertTrue(BlogPost.objects.filter(pk=post.pk).exists())


class BlogTagModelTests(TestCase):
    def test_slug_is_generated_from_the_name(self):
        tag = factories.tag('Skin Care Routine')

        self.assertEqual(tag.slug, 'skin-care-routine')

    def test_slug_is_not_regenerated_when_the_name_changes(self):
        tag = factories.tag('Original')

        tag.name = 'Renamed'
        tag.save()
        tag.refresh_from_db()

        self.assertEqual(tag.slug, 'original')

    def test_name_is_unique(self):
        factories.tag('Routine')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                factories.tag('Routine')

    def test_legacy_id_is_unique(self):
        factories.tag('First', legacy_id=55)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                factories.tag('Second', legacy_id=55)

    def test_soft_delete_keeps_the_row(self):
        tag = factories.tag('Routine')

        tag.soft_delete()
        tag.refresh_from_db()

        self.assertFalse(tag.is_active)
        self.assertIsNotNone(tag.deleted_at)
        self.assertTrue(BlogTag.objects.filter(pk=tag.pk).exists())

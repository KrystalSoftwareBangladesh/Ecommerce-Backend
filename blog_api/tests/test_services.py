# blog_api/tests/test_services.py
from django.test import TestCase

from rest_framework.exceptions import ValidationError

from blog_api.models import BlogPostStatus
from blog_api.services import (
    create_blog_post,
    delete_blog_post,
    publish_blog_post,
    unpublish_blog_post,
    update_blog_post,
)
from blog_api.tests import factories


class BlogPostServiceTests(TestCase):
    def setUp(self):
        self.user = factories.user('editor')

    def test_create_always_produces_a_draft(self):
        post = create_blog_post(
            validated_data={
                'title': 'Winter routine',
                'content': '<p>Body</p>',
                'status': BlogPostStatus.PUBLISHED,
            },
            user=self.user,
        )

        self.assertEqual(post.status, BlogPostStatus.DRAFT)
        self.assertIsNone(post.published_at)

    def test_create_defaults_the_author_to_the_acting_user(self):
        post = create_blog_post(
            validated_data={'title': 'Mine'},
            user=self.user,
        )

        self.assertEqual(post.author, self.user)
        self.assertEqual(post.created_by, self.user)

    def test_create_keeps_an_explicit_author(self):
        author = factories.user('guest-writer')

        post = create_blog_post(
            validated_data={'title': 'Guest post', 'author': author},
            user=self.user,
        )

        self.assertEqual(post.author, author)
        self.assertEqual(post.created_by, self.user)

    def test_create_attaches_categories_and_tags(self):
        categories = [factories.category('Skincare')]
        tags = [factories.tag('Routine')]

        post = create_blog_post(
            validated_data={
                'title': 'Tagged',
                'categories': categories,
                'tags': tags,
            },
            user=self.user,
        )

        self.assertEqual(list(post.categories.all()), categories)
        self.assertEqual(list(post.tags.all()), tags)

    def test_update_leaves_a_published_post_published(self):
        post = factories.post(published=True)
        published_at = post.published_at

        updated = update_blog_post(
            post=post,
            validated_data={'title': 'Edited title'},
            user=self.user,
        )

        self.assertEqual(updated.status, BlogPostStatus.PUBLISHED)
        self.assertEqual(updated.published_at, published_at)
        self.assertEqual(updated.updated_by, self.user)

    def test_update_only_touches_relations_that_were_supplied(self):
        tags = [factories.tag('Routine')]
        post = factories.post(tags=tags)

        update_blog_post(
            post=post,
            validated_data={'title': 'Edited'},
            user=self.user,
        )

        self.assertEqual(list(post.tags.all()), tags)

    def test_update_can_clear_relations_explicitly(self):
        post = factories.post(tags=[factories.tag('Routine')])

        update_blog_post(
            post=post,
            validated_data={'tags': []},
            user=self.user,
        )

        self.assertEqual(post.tags.count(), 0)

    def test_delete_soft_deletes_and_records_the_actor(self):
        post = factories.post()

        delete_blog_post(post=post, user=self.user)
        post.refresh_from_db()

        self.assertFalse(post.is_active)
        self.assertIsNotNone(post.deleted_at)
        self.assertEqual(post.updated_by, self.user)

    def test_publish_sets_the_status_and_the_publication_date(self):
        post = factories.post()

        published = publish_blog_post(post=post, user=self.user)

        self.assertEqual(published.status, BlogPostStatus.PUBLISHED)
        self.assertIsNotNone(published.published_at)

    def test_publishing_an_already_published_post_is_rejected(self):
        post = factories.post(published=True)

        with self.assertRaises(ValidationError):
            publish_blog_post(post=post, user=self.user)

    def test_unpublish_returns_to_draft_and_clears_the_date(self):
        post = factories.post(published=True)

        drafted = unpublish_blog_post(post=post, user=self.user)

        self.assertEqual(drafted.status, BlogPostStatus.DRAFT)
        self.assertIsNone(drafted.published_at)

    def test_unpublishing_a_draft_is_rejected(self):
        post = factories.post()

        with self.assertRaises(ValidationError):
            unpublish_blog_post(post=post, user=self.user)

    def test_republishing_stamps_a_new_publication_date(self):
        post = factories.post(published=True)
        first_published_at = post.published_at

        unpublish_blog_post(post=post, user=self.user)
        publish_blog_post(post=post, user=self.user)

        self.assertNotEqual(post.published_at, first_published_at)

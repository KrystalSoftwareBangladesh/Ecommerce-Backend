# blog_api/tests/test_api_blog_post.py
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework.test import APITestCase

from blog_api.models import BlogPost, BlogPostStatus
from blog_api.tests import factories


POSTS_URL = '/api/v1/blog/posts/'


def detail_url(post):
    return f'{POSTS_URL}{post.id}/'


class BlogPostApiTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('blog-editor'),
            BlogPost,
            'view_blogpost',
            'add_blogpost',
            'change_blogpost',
            'delete_blogpost',
        )
        self.publisher = factories.grant(
            factories.user('blog-publisher'),
            BlogPost,
            'view_blogpost',
            'publish_blog_post',
            'unpublish_blog_post',
        )
        self.outsider = factories.user('blog-outsider')

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.editor)


class BlogPostCrudTests(BlogPostApiTestCase):
    def test_list_returns_the_project_pagination_shape(self):
        factories.post(published=True)

        response = self.client.get(POSTS_URL)

        self.assertEqual(response.status_code, 200)
        for key in ['count', 'total_pages', 'current_page', 'results']:
            self.assertIn(key, response.data)

    def test_create_requires_the_add_permission(self):
        self.authenticate(self.outsider)

        response = self.client.post(POSTS_URL, {'title': 'Nope'})

        self.assertEqual(response.status_code, 403)

    def test_create_requires_authentication(self):
        response = self.client.post(POSTS_URL, {'title': 'Nope'})

        self.assertEqual(response.status_code, 401)

    def test_create_returns_a_draft_with_a_generated_slug(self):
        self.authenticate()

        response = self.client.post(
            POSTS_URL,
            {
                'title': 'Winter Skincare',
                'content': '<p>Layer up</p>',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], BlogPostStatus.DRAFT)
        self.assertEqual(response.data['slug'], 'winter-skincare')
        self.assertIsNone(response.data['published_at'])

    def test_create_ignores_a_client_supplied_status_and_slug(self):
        self.authenticate()

        response = self.client.post(
            POSTS_URL,
            {
                'title': 'Sneaky',
                'status': BlogPostStatus.PUBLISHED,
                'slug': 'chosen-by-the-client',
                'published_at': '2026-01-01T00:00:00Z',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], BlogPostStatus.DRAFT)
        self.assertEqual(response.data['slug'], 'sneaky')

    def test_create_stores_categories_tags_and_seo_metadata(self):
        self.authenticate()
        category = factories.category('Skincare')
        tag = factories.tag('Routine')

        response = self.client.post(
            POSTS_URL,
            {
                'title': 'Full payload',
                'content': '<p>Body</p>',
                'categories': [category.id],
                'tags': [tag.id],
                'seo_title': 'Search title',
                'seo_description': 'Search description',
                'seo_focus_keyword': 'skincare',
                'seo_noindex': True,
                'seo_nofollow': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)

        post = BlogPost.objects.get(pk=response.data['id'])
        self.assertEqual(list(post.categories.all()), [category])
        self.assertEqual(list(post.tags.all()), [tag])
        self.assertEqual(post.seo_focus_keyword, 'skincare')
        self.assertTrue(post.seo_noindex)

    def test_create_accepts_a_multipart_featured_image(self):
        self.authenticate()

        response = self.client.post(
            POSTS_URL,
            {
                'title': 'With an image',
                'featured_image': factories.image_file(),
                'featured_image_alt_text': 'A red square',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data['featured_image'])
        self.assertEqual(
            response.data['featured_image_alt_text'],
            'A red square',
        )

    def test_retrieve_works_by_id_and_by_slug(self):
        post = factories.post(title='Findable', published=True)

        by_id = self.client.get(detail_url(post))
        by_slug = self.client.get(f'{POSTS_URL}{post.slug}/')

        self.assertEqual(by_id.status_code, 200)
        self.assertEqual(by_slug.status_code, 200)
        self.assertEqual(by_slug.data['id'], post.id)

    def test_put_updates_the_post_without_changing_the_slug(self):
        self.authenticate()
        post = factories.post(title='Before')

        response = self.client.put(
            detail_url(post),
            {
                'title': 'After',
                'slug': 'client-slug',
                'content': '<p>Rewritten</p>',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'After')
        self.assertEqual(response.data['slug'], 'before')

    def test_patch_updates_only_the_supplied_fields(self):
        self.authenticate()
        tag = factories.tag('Routine')
        post = factories.post(title='Before', tags=[tag])

        response = self.client.patch(
            detail_url(post),
            {'seo_title': 'New search title'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Before')
        self.assertEqual(response.data['seo_title'], 'New search title')
        self.assertEqual(len(response.data['tags']), 1)

    def test_update_requires_the_change_permission(self):
        self.authenticate(self.outsider)
        post = factories.post()

        response = self.client.patch(
            detail_url(post),
            {'title': 'Nope'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_delete_soft_deletes_the_post(self):
        self.authenticate()
        post = factories.post()

        response = self.client.delete(detail_url(post))
        post.refresh_from_db()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(post.is_active)
        self.assertIsNotNone(post.deleted_at)
        self.assertEqual(post.updated_by, self.editor)

    def test_delete_requires_the_delete_permission(self):
        self.authenticate(self.outsider)
        post = factories.post()

        response = self.client.delete(detail_url(post))

        self.assertEqual(response.status_code, 403)

    def test_a_soft_deleted_post_is_gone_from_every_read(self):
        self.authenticate()
        post = factories.post(published=True)
        post.soft_delete()

        listed = self.client.get(POSTS_URL)
        retrieved = self.client.get(detail_url(post))

        self.assertEqual(listed.data['count'], 0)
        self.assertEqual(retrieved.status_code, 404)


class BlogPostPublishingTests(BlogPostApiTestCase):
    def publish_url(self, post):
        return f'{detail_url(post)}publish/'

    def unpublish_url(self, post):
        return f'{detail_url(post)}unpublish/'

    def test_publish_moves_a_draft_to_published_with_a_date(self):
        self.authenticate(self.publisher)
        post = factories.post()

        response = self.client.post(self.publish_url(post))
        post.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.status, BlogPostStatus.PUBLISHED)
        self.assertIsNotNone(post.published_at)
        self.assertEqual(response.data['status'], BlogPostStatus.PUBLISHED)

    def test_unpublish_returns_a_post_to_draft_and_clears_the_date(self):
        self.authenticate(self.publisher)
        post = factories.post(published=True)

        response = self.client.post(self.unpublish_url(post))
        post.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.status, BlogPostStatus.DRAFT)
        self.assertIsNone(post.published_at)

    def test_publishing_needs_more_than_the_permission_to_write(self):
        self.authenticate(self.editor)
        post = factories.post()

        response = self.client.post(self.publish_url(post))
        post.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(post.status, BlogPostStatus.DRAFT)

    def test_unpublishing_needs_more_than_the_permission_to_write(self):
        self.authenticate(self.editor)
        post = factories.post(published=True)

        response = self.client.post(self.unpublish_url(post))
        post.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(post.status, BlogPostStatus.PUBLISHED)

    def test_publish_permission_does_not_imply_unpublish_permission(self):
        user = factories.grant(
            factories.user('publish-only'),
            BlogPost,
            'publish_blog_post',
        )
        self.authenticate(user)
        post = factories.post(published=True)

        response = self.client.post(self.unpublish_url(post))

        self.assertEqual(response.status_code, 403)

    def test_publishing_does_not_require_permission_to_view_drafts(self):
        user = factories.grant(
            factories.user('publisher-without-view'),
            BlogPost,
            'publish_blog_post',
        )
        self.authenticate(user)
        post = factories.post()

        response = self.client.post(self.publish_url(post))

        self.assertEqual(response.status_code, 200)

    def test_publishing_requires_authentication(self):
        post = factories.post()

        response = self.client.post(self.publish_url(post))

        self.assertEqual(response.status_code, 401)

    def test_editing_a_published_post_keeps_it_published(self):
        self.authenticate(self.editor)
        post = factories.post(published=True)
        published_at = post.published_at

        response = self.client.patch(
            detail_url(post),
            {'content': '<p>Corrected</p>'},
            format='json',
        )
        post.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.status, BlogPostStatus.PUBLISHED)
        self.assertEqual(post.published_at, published_at)

    def test_publishing_twice_is_rejected(self):
        self.authenticate(self.publisher)
        post = factories.post(published=True)

        response = self.client.post(self.publish_url(post))

        self.assertEqual(response.status_code, 400)

    def test_unpublishing_a_draft_is_rejected(self):
        self.authenticate(self.publisher)
        post = factories.post()

        response = self.client.post(self.unpublish_url(post))

        self.assertEqual(response.status_code, 400)


class BlogPostPublicVisibilityTests(BlogPostApiTestCase):
    def setUp(self):
        super().setUp()
        self.published = factories.post(title='Published', published=True)
        self.draft = factories.post(title='Draft')
        self.deleted = factories.post(title='Deleted', published=True)
        self.deleted.soft_delete()

    def test_an_anonymous_caller_sees_only_published_posts(self):
        response = self.client.get(POSTS_URL)

        titles = [row['title'] for row in response.data['results']]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(titles, ['Published'])

    def test_an_anonymous_caller_cannot_open_a_draft(self):
        response = self.client.get(detail_url(self.draft))

        self.assertEqual(response.status_code, 404)

    def test_an_anonymous_caller_cannot_open_a_draft_by_slug(self):
        response = self.client.get(f'{POSTS_URL}{self.draft.slug}/')

        self.assertEqual(response.status_code, 404)

    def test_an_anonymous_caller_cannot_open_a_deleted_post(self):
        response = self.client.get(detail_url(self.deleted))

        self.assertEqual(response.status_code, 404)

    def test_a_status_filter_cannot_surface_drafts_publicly(self):
        response = self.client.get(
            f'{POSTS_URL}?status={BlogPostStatus.DRAFT}'
        )

        self.assertEqual(response.data['count'], 0)

    def test_an_authenticated_user_without_view_sees_only_published(self):
        self.authenticate(self.outsider)

        response = self.client.get(POSTS_URL)

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            self.client.get(detail_url(self.draft)).status_code,
            404,
        )

    def test_a_user_holding_view_sees_drafts_too(self):
        self.authenticate(self.editor)

        response = self.client.get(POSTS_URL)
        titles = {row['title'] for row in response.data['results']}

        self.assertEqual(titles, {'Published', 'Draft'})
        self.assertEqual(
            self.client.get(detail_url(self.draft)).status_code,
            200,
        )

    def test_a_user_holding_view_still_never_sees_deleted_posts(self):
        self.authenticate(self.editor)

        response = self.client.get(POSTS_URL)
        titles = {row['title'] for row in response.data['results']}

        self.assertNotIn('Deleted', titles)

    def test_unpublishing_removes_a_post_from_the_public_blog(self):
        self.authenticate(self.publisher)
        self.client.post(f'{detail_url(self.published)}unpublish/')
        self.client.force_authenticate(user=None)

        response = self.client.get(detail_url(self.published))

        self.assertEqual(response.status_code, 404)


class BlogPostFilteringTests(BlogPostApiTestCase):
    def setUp(self):
        super().setUp()
        self.skincare = factories.category('Skincare')
        self.wellness = factories.category('Wellness')
        self.routine = factories.tag('Routine')
        self.tips = factories.tag('Tips')
        self.author = factories.user('house-writer')

        self.first = factories.post(
            title='Winter routine',
            content='<p>Moisturise daily</p>',
            published=True,
            author=self.author,
            categories=[self.skincare],
            tags=[self.routine],
        )
        self.second = factories.post(
            title='Summer wellness',
            content='<p>Hydrate</p>',
            published=True,
            categories=[self.wellness],
            tags=[self.tips],
        )
        self.hidden_draft = factories.post(
            title='Winter draft',
            author=self.author,
            categories=[self.skincare],
            tags=[self.routine],
        )

    def titles(self, response):
        return [row['title'] for row in response.data['results']]

    def test_public_filtering_by_category_id(self):
        response = self.client.get(
            f'{POSTS_URL}?category={self.skincare.id}'
        )

        self.assertEqual(self.titles(response), ['Winter routine'])

    def test_public_filtering_by_category_slug(self):
        response = self.client.get(
            f'{POSTS_URL}?category_slug={self.wellness.slug}'
        )

        self.assertEqual(self.titles(response), ['Summer wellness'])

    def test_public_filtering_by_tag_id(self):
        response = self.client.get(f'{POSTS_URL}?tag={self.tips.id}')

        self.assertEqual(self.titles(response), ['Summer wellness'])

    def test_public_filtering_by_tag_slug(self):
        response = self.client.get(
            f'{POSTS_URL}?tag_slug={self.routine.slug}'
        )

        self.assertEqual(self.titles(response), ['Winter routine'])

    def test_public_search_matches_title_and_content(self):
        by_title = self.client.get(f'{POSTS_URL}?search=Summer')
        by_content = self.client.get(f'{POSTS_URL}?search=Moisturise')

        self.assertEqual(self.titles(by_title), ['Summer wellness'])
        self.assertEqual(self.titles(by_content), ['Winter routine'])

    def test_public_filtering_never_reaches_a_draft(self):
        for query in [
            f'category={self.skincare.id}',
            f'tag={self.routine.id}',
            f'author={self.author.id}',
            'search=Winter',
            f'status={BlogPostStatus.DRAFT}',
        ]:
            response = self.client.get(f'{POSTS_URL}?{query}')

            self.assertNotIn('Winter draft', self.titles(response), query)

    def test_a_permitted_user_can_filter_by_status(self):
        self.authenticate(self.editor)

        response = self.client.get(
            f'{POSTS_URL}?status={BlogPostStatus.DRAFT}'
        )

        self.assertEqual(self.titles(response), ['Winter draft'])

    def test_a_permitted_user_can_filter_by_author(self):
        self.authenticate(self.editor)

        response = self.client.get(f'{POSTS_URL}?author={self.author.id}')

        self.assertEqual(
            set(self.titles(response)),
            {'Winter routine', 'Winter draft'},
        )

    def test_ordering_is_newest_publication_first_by_default(self):
        response = self.client.get(POSTS_URL)

        self.assertEqual(
            self.titles(response),
            ['Summer wellness', 'Winter routine'],
        )

    def test_ordering_can_be_reversed(self):
        response = self.client.get(f'{POSTS_URL}?ordering=published_at')

        self.assertEqual(
            self.titles(response),
            ['Winter routine', 'Summer wellness'],
        )


class BlogPostRelationshipTests(BlogPostApiTestCase):
    def test_a_post_can_carry_several_categories_and_tags(self):
        self.authenticate()
        categories = [
            factories.category('Skincare'),
            factories.category('Wellness'),
        ]
        tags = [
            factories.tag('Routine'),
            factories.tag('Tips'),
        ]

        created = self.client.post(
            POSTS_URL,
            {
                'title': 'Many relations',
                'categories': [c.id for c in categories],
                'tags': [t.id for t in tags],
            },
            format='json',
        )

        self.assertEqual(len(created.data['categories']), 2)
        self.assertEqual(len(created.data['tags']), 2)

    def test_the_detail_payload_expands_author_categories_and_tags(self):
        author = factories.user('house-writer')
        post = factories.post(
            published=True,
            author=author,
            categories=[factories.category('Skincare')],
            tags=[factories.tag('Routine')],
        )

        response = self.client.get(detail_url(post))

        self.assertEqual(response.data['author']['id'], author.id)
        self.assertEqual(
            response.data['categories'][0]['name'],
            'Skincare',
        )
        self.assertEqual(response.data['tags'][0]['name'], 'Routine')

    def test_the_featured_image_is_returned_as_an_absolute_url(self):
        post = factories.post(
            published=True,
            featured_image=factories.image_file(),
        )

        response = self.client.get(detail_url(post))

        self.assertTrue(
            response.data['featured_image'].startswith('http')
        )

    def test_a_post_without_a_featured_image_reports_none(self):
        post = factories.post(published=True)

        response = self.client.get(detail_url(post))

        self.assertIsNone(response.data['featured_image'])

    def test_the_list_does_not_grow_queries_with_the_number_of_posts(self):
        category = factories.category('Skincare')
        tag = factories.tag('Routine')
        author = factories.user('house-writer')

        def add(title):
            factories.post(
                title=title,
                published=True,
                author=author,
                categories=[category],
                tags=[tag],
            )

        def queries_for_the_list():
            with CaptureQueriesContext(connection) as captured:
                self.client.get(POSTS_URL)
            return len(captured)

        add('One')
        one_post = queries_for_the_list()

        for index in range(5):
            add(f'Extra {index}')

        self.assertEqual(queries_for_the_list(), one_post)

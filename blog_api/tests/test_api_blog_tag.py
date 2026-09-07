# blog_api/tests/test_api_blog_tag.py
from rest_framework.test import APITestCase

from blog_api.models import BlogTag
from blog_api.tests import factories


TAGS_URL = '/api/v1/blog/tags/'


def detail_url(tag):
    return f'{TAGS_URL}{tag.id}/'


class BlogTagApiTestCase(APITestCase):
    def setUp(self):
        self.manager = factories.grant(
            factories.user('tag-manager'),
            BlogTag,
            'view_blogtag',
            'add_blogtag',
            'change_blogtag',
            'delete_blogtag',
        )
        self.outsider = factories.user('tag-outsider')

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.manager)


class BlogTagCrudTests(BlogTagApiTestCase):
    def test_list_is_public_and_paginated(self):
        factories.tag('Routine')

        response = self.client.get(TAGS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        for key in ['count', 'total_pages', 'current_page', 'results']:
            self.assertIn(key, response.data)

    def test_detail_is_public(self):
        tag = factories.tag('Routine')

        response = self.client.get(detail_url(tag))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Routine')

    def test_create_generates_the_slug(self):
        self.authenticate()

        response = self.client.post(
            TAGS_URL,
            {'name': 'Skin Care Routine'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['slug'], 'skin-care-routine')

    def test_create_ignores_a_client_supplied_slug(self):
        self.authenticate()

        response = self.client.post(
            TAGS_URL,
            {'name': 'Routine', 'slug': 'chosen-by-the-client'},
            format='json',
        )

        self.assertEqual(response.data['slug'], 'routine')

    def test_create_records_the_actor(self):
        self.authenticate()

        response = self.client.post(
            TAGS_URL,
            {'name': 'Routine'},
            format='json',
        )
        tag = BlogTag.objects.get(pk=response.data['id'])

        self.assertEqual(tag.created_by, self.manager)
        self.assertEqual(tag.updated_by, self.manager)

    def test_create_does_not_accept_a_legacy_id(self):
        self.authenticate()

        response = self.client.post(
            TAGS_URL,
            {'name': 'Routine', 'legacy_id': 99},
            format='json',
        )
        tag = BlogTag.objects.get(pk=response.data['id'])

        self.assertIsNone(tag.legacy_id)

    def test_create_rejects_a_duplicate_name_case_insensitively(self):
        self.authenticate()
        factories.tag('Routine')

        response = self.client.post(
            TAGS_URL,
            {'name': 'routine'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(BlogTag.objects.count(), 1)

    def test_update_renames_without_changing_the_slug(self):
        self.authenticate()
        tag = factories.tag('Routine')

        response = self.client.put(
            detail_url(tag),
            {'name': 'Routines', 'slug': 'client-slug'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Routines')
        self.assertEqual(response.data['slug'], 'routine')

    def test_update_rejects_a_name_another_tag_already_uses(self):
        self.authenticate()
        factories.tag('Routine')
        other = factories.tag('Tips')

        response = self.client.patch(
            detail_url(other),
            {'name': 'Routine'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_update_accepts_the_tags_own_name_unchanged(self):
        self.authenticate()
        tag = factories.tag('Routine')

        response = self.client.patch(
            detail_url(tag),
            {'name': 'Routine'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)

    def test_delete_soft_deletes_the_tag(self):
        self.authenticate()
        tag = factories.tag('Routine')

        response = self.client.delete(detail_url(tag))
        tag.refresh_from_db()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(tag.is_active)
        self.assertIsNotNone(tag.deleted_at)
        self.assertEqual(tag.updated_by, self.manager)

    def test_a_soft_deleted_tag_disappears_from_the_public_list(self):
        tag = factories.tag('Routine')
        tag.soft_delete()

        listed = self.client.get(TAGS_URL)
        retrieved = self.client.get(detail_url(tag))

        self.assertEqual(listed.data['count'], 0)
        self.assertEqual(retrieved.status_code, 404)

    def test_search_matches_the_name(self):
        factories.tag('Routine')
        factories.tag('Tips')

        response = self.client.get(f'{TAGS_URL}?search=Rout')

        self.assertEqual(response.data['count'], 1)


class BlogTagPermissionTests(BlogTagApiTestCase):
    def test_writes_require_authentication(self):
        tag = factories.tag('Routine')

        self.assertEqual(
            self.client.post(TAGS_URL, {'name': 'New'}).status_code,
            401,
        )
        self.assertEqual(
            self.client.delete(detail_url(tag)).status_code,
            401,
        )

    def test_create_requires_the_add_permission(self):
        self.authenticate(self.outsider)

        response = self.client.post(
            TAGS_URL,
            {'name': 'Routine'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_update_requires_the_change_permission(self):
        self.authenticate(self.outsider)
        tag = factories.tag('Routine')

        response = self.client.patch(
            detail_url(tag),
            {'name': 'Renamed'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_delete_requires_the_delete_permission(self):
        self.authenticate(self.outsider)
        tag = factories.tag('Routine')

        response = self.client.delete(detail_url(tag))

        self.assertEqual(response.status_code, 403)

    def test_a_holder_of_add_alone_cannot_delete(self):
        user = factories.grant(
            factories.user('tag-adder'),
            BlogTag,
            'add_blogtag',
        )
        self.authenticate(user)
        tag = factories.tag('Routine')

        self.assertEqual(
            self.client.post(
                TAGS_URL,
                {'name': 'Fresh'},
                format='json',
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.delete(detail_url(tag)).status_code,
            403,
        )

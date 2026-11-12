# cms_api/tests/test_api_section_types.py
"""Tests for the section-type schema endpoint."""
from rest_framework.test import APITestCase

from cms_api.sections import SECTION_TYPES
from cms_api.tests import factories


SECTION_TYPES_URL = '/api/v1/cms/section-types/'


class SectionTypeApiTests(APITestCase):
    def setUp(self):
        self.user = factories.user('cms-reader')

    def test_requires_authentication(self):
        response = self.client.get(SECTION_TYPES_URL)

        self.assertEqual(response.status_code, 401)

    def test_lists_every_registered_section_type(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(SECTION_TYPES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.data),
            len(SECTION_TYPES),
        )
        types = {row['type'] for row in response.data}
        self.assertEqual(types, set(SECTION_TYPES.keys()))

    def test_schema_describes_product_collection_modes(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(SECTION_TYPES_URL)

        row = next(
            row for row in response.data
            if row['type'] == 'product_collection'
        )
        fields = {
            field['name']: field
            for field in row['content']['fields']
        }
        self.assertEqual(
            fields['mode']['type'],
            'choice',
        )
        values = {
            choice['value']
            for choice in fields['mode']['choices']
        }
        self.assertIn('MANUAL', values)
        self.assertIn('BY_CATEGORY', values)

    def test_schema_lists_richtext_features(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(SECTION_TYPES_URL)

        row = next(
            row for row in response.data
            if row['type'] == 'rich_text'
        )
        body = row['content']['fields'][0]
        self.assertEqual(body['type'], 'richtext')
        self.assertIn('bold', body['features'])

    def test_schema_describes_nested_lists(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(SECTION_TYPES_URL)

        row = next(
            row for row in response.data
            if row['type'] == 'image_gallery'
        )
        images = row['content']['fields'][0]
        self.assertEqual(images['type'], 'list')
        self.assertEqual(images['item']['type'], 'object')

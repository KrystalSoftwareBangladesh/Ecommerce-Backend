# cms_api/tests/test_api_cms_page_public.py
"""Public page API tests: published-only reads (draft isolation)."""
from django.conf import settings

from rest_framework.test import APITestCase

from cms_api.services import (
    archive_page,
    publish_page,
    publish_section,
)
from cms_api.tests import factories


PUBLIC_URL = '/api/v1/cms/public/pages/'


class CmsPagePublicTestCase(APITestCase):
    def setUp(self):
        self.owner = factories.user('cms-public-owner')

    def published_page(self, slug='about', **kwargs):
        page = factories.page(self.owner, slug=slug, **kwargs)
        publish_page(page=page, user=self.owner)
        return page

    def get_page(self, path):
        return self.client.get(PUBLIC_URL, {'path': path})


class PublicDetailTests(CmsPagePublicTestCase):
    def test_published_page_resolves_its_path(self):
        page = self.published_page(title='About us')

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'About us')
        self.assertEqual(response.data['path'], page.url_path)

    def test_unpublished_page_is_not_served(self):
        page = factories.page(self.owner, slug='draft')

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 404)

    def test_archived_page_is_not_served(self):
        page = self.published_page(slug='old')
        archive_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 404)

    def test_unknown_path_is_not_found(self):
        response = self.get_page('/missing/')

        self.assertEqual(response.status_code, 404)

    def test_draft_changes_are_not_served(self):
        page = self.published_page(title='Published')
        page.refresh_from_db()
        page.title = 'Draft title'
        page.save()
        page.save_revision(user=self.owner)

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Published')

    def test_draft_slug_path_is_not_served(self):
        page = self.published_page(slug='about', title='About us')
        page.refresh_from_db()
        page.slug = 'about-v2'
        page.save()
        page.save_revision(user=self.owner)
        page.refresh_from_db()
        self.assertEqual(page.url_path, '/about-v2/')

        response = self.get_page('/about-v2/')

        self.assertEqual(response.status_code, 404)

    def test_published_path_resolves_after_a_draft_slug_change(self):
        page = self.published_page(slug='about', title='About us')
        page.refresh_from_db()
        page.slug = 'about-v2'
        page.save()
        page.save_revision(user=self.owner)

        response = self.get_page('/about/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['slug'], 'about')
        self.assertEqual(response.data['path'], '/about/')


class PublicListTests(CmsPagePublicTestCase):
    def test_list_includes_only_published_pages(self):
        page = self.published_page(slug='about')
        factories.page(self.owner, slug='draft')

        response = self.client.get(PUBLIC_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['path'], page.url_path)

    def test_list_needs_no_authentication(self):
        self.published_page(slug='about')

        response = self.client.get(PUBLIC_URL)

        self.assertEqual(response.status_code, 200)

    def test_list_reports_published_urls_after_a_draft_slug_change(self):
        page = self.published_page(slug='about', title='About us')
        page.refresh_from_db()
        page.slug = 'about-v2'
        page.save()
        page.save_revision(user=self.owner)

        response = self.client.get(PUBLIC_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'about')
        self.assertEqual(response.data[0]['path'], '/about/')


class PublicCompositionTests(CmsPagePublicTestCase):
    def test_local_rows_are_served(self):
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Hero',
            content=factories.hero_content('Welcome'),
        )
        publish_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 200)
        rows = response.data['sections']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Hero')
        self.assertEqual(rows[0]['source'], 'local')
        self.assertEqual(
            rows[0]['content'][0]['value']['heading'],
            'Welcome',
        )

    def test_unpublished_global_rows_are_omitted(self):
        shared = factories.section(
            name='Shared', user=self.owner, live=False,
        )
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Shared row',
            global_section=shared.pk,
        )
        factories.page_section(page, self.owner, name='Local row')
        publish_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        rows = response.data['sections']
        self.assertEqual([row['name'] for row in rows], ['Local row'])

    def test_global_rows_resolve_to_published_content(self):
        shared = factories.section(
            name='Shared',
            content=factories.hero_content('Shared hero'),
            user=self.owner,
        )
        publish_section(section=shared, user=self.owner)
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Shared row',
            global_section=shared.pk,
        )
        publish_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        rows = response.data['sections']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'global')
        self.assertEqual(rows[0]['global_section'], shared.pk)
        self.assertEqual(
            rows[0]['content'][0]['value']['heading'],
            'Shared hero',
        )


class PublicRichTextExpansionTests(CmsPagePublicTestCase):
    """Rich text placeholders expand to usable URLs in public reads."""

    def rich_body(self, page, body, name='Rich'):
        factories.page_section(
            page, self.owner, name=name,
            content=factories.rich_text_content(body),
        )
        publish_page(page=page, user=self.owner)
        response = self.get_page(page.url_path)
        self.assertEqual(response.status_code, 200)
        return response.data['sections'][0]['content'][0]['value']['body']

    def test_internal_page_links_expand_to_public_urls(self):
        target = self.published_page(slug='about', title='About')
        page = factories.page(self.owner, slug='compose')

        body = self.rich_body(
            page,
            '<p><a linktype="page" id="%d">About us</a></p>' % target.pk,
        )

        self.assertNotIn('linktype', body)
        self.assertIn('<a href=', body)
        self.assertIn(target.url_path, body)
        self.assertIn('>About us</a>', body)

    def test_links_use_the_published_path_after_a_draft_slug_change(
        self,
    ):
        target = self.published_page(slug='about', title='About')
        target.refresh_from_db()
        target.slug = 'about-v2'
        target.save()
        target.save_revision(user=self.owner)
        page = factories.page(self.owner, slug='compose')

        body = self.rich_body(
            page,
            '<p><a linktype="page" id="%d">About us</a></p>' % target.pk,
        )

        self.assertIn('href="/about/"', body)
        self.assertNotIn('about-v2', body)

    def test_unresolvable_page_links_leave_a_bare_anchor(self):
        page = factories.page(self.owner, slug='compose')

        body = self.rich_body(
            page,
            '<p><a linktype="page" id="999999">Gone</a></p>',
        )

        self.assertIn('<a>Gone</a>', body)

    def test_embedded_images_expand_to_media_urls(self):
        image = factories.cms_image(user=self.owner)
        page = factories.page(self.owner, slug='compose')

        body = self.rich_body(
            page,
            '<p><embed embedtype="image" id="%d" '
            'format="fullwidth" /></p>' % image.pk,
        )

        self.assertNotIn('embedtype', body)
        self.assertIn('src="', body)
        self.assertIn(settings.MEDIA_URL, body)

    def test_image_placeholder_in_img_form_also_expands(self):
        # The task's observed symptom form; Wagtail's canonical stored
        # form is <embed ... /> but content can arrive via the API with
        # either spelling.
        image = factories.cms_image(user=self.owner)
        page = factories.page(self.owner, slug='compose')

        body = self.rich_body(
            page,
            '<p><img embedtype="image" id="%d" '
            'format="fullwidth"></p>' % image.pk,
        )

        self.assertNotIn('embedtype', body)
        self.assertIn('src="', body)
        self.assertIn(settings.MEDIA_URL, body)

    def test_expanded_image_urls_sit_under_media_url(self):
        # Django serves no /media/ route; the web server does. The API
        # must emit paths under MEDIA_URL so that server can serve
        # them (docs/cms-architecture.md, media delivery note).
        image = factories.cms_image(user=self.owner)
        page = factories.page(self.owner, slug='compose')

        body = self.rich_body(
            page,
            '<p><embed embedtype="image" id="%d" '
            'format="fullwidth" /></p>' % image.pk,
        )

        src = body.split('src="', 1)[1].split('"', 1)[0]
        self.assertTrue(src.startswith(settings.MEDIA_URL), src)

    def test_ordinary_formatting_is_preserved(self):
        source = (
            '<h2>Head</h2><p><strong>bold</strong> and '
            '<em>italic</em></p><ul><li>one</li></ul>'
            '<blockquote>quote</blockquote>'
            '<table><tbody><tr><td>cell</td></tr></tbody></table>'
        )
        page = factories.page(self.owner, slug='compose')

        self.assertEqual(self.rich_body(page, source), source)

    def test_rich_text_of_unpublished_and_archived_pages_is_never_served(
        self,
    ):
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Rich',
            content=factories.rich_text_content('<p>secret</p>'),
        )
        self.assertEqual(self.get_page(page.url_path).status_code, 404)

        publish_page(page=page, user=self.owner)
        archive_page(page=page, user=self.owner)
        self.assertEqual(self.get_page(page.url_path).status_code, 404)

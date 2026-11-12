# cms_api/tests/test_api_cms_navigation.py
"""Navigation menu/item management and public read APIs (docs/
cms-architecture.md 5.5, 6, 8)."""
from django.utils import timezone

from rest_framework.test import APITestCase

from cms_api.models import CmsNavigationItem, CmsNavigationMenu, CmsPage
from cms_api.tests import factories


MENUS_URL = '/api/v1/cms/navigation/'


def menu_url(menu):
    return f'{MENUS_URL}{menu.id}/'


def items_url(menu):
    return f'{menu_url(menu)}items/'


def item_url(menu, item):
    return f'{items_url(menu)}{item.id}/'


def reorder_url(menu):
    return f'{items_url(menu)}reorder/'


def public_url(key):
    return f'/api/v1/cms/public/navigation/{key}/'


class CmsNavigationTestCase(APITestCase):
    def setUp(self):
        self.manager = factories.grant(
            factories.user('nav-manager'),
            CmsNavigationMenu,
            'manage_cms_navigation',
        )
        self.editor = factories.grant(
            factories.user('nav-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.manager)

    def publish(self, page):
        self.authenticate(self.editor)
        return self.client.post(
            f'/api/v1/cms/pages/{page.id}/publish/', {},
        )


class MenuCrudTests(CmsNavigationTestCase):
    def test_create_requires_manage_cms_navigation(self):
        self.client.force_authenticate(user=self.editor)

        response = self.client.post(
            MENUS_URL, {'name': 'Header', 'key': 'HEADER'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_standard_model_permissions_are_not_sufficient(self):
        """Only ``manage_cms_navigation`` grants access — the
        standard add/view/change/delete permissions this model also
        has (via Django's auto-created codenames) must not."""
        holder = factories.grant(
            factories.user('nav-add-only'),
            CmsNavigationMenu,
            'add_cmsnavigationmenu',
            'view_cmsnavigationmenu',
        )
        self.client.force_authenticate(user=holder)

        response = self.client.post(
            MENUS_URL, {'name': 'Header', 'key': 'HEADER'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_create_a_menu(self):
        self.authenticate()

        response = self.client.post(
            MENUS_URL, {'name': 'Header', 'key': 'HEADER'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['key'], 'HEADER')
        self.assertTrue(
            CmsNavigationMenu.objects.filter(key='HEADER').exists()
        )

    def test_key_must_be_unique(self):
        self.authenticate()
        factories.navigation_menu(key='HEADER')

        response = self.client.post(
            MENUS_URL, {'name': 'Another', 'key': 'HEADER'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_list_only_shows_active_menus(self):
        self.authenticate()
        factories.navigation_menu(name='Header', key='HEADER')

        response = self.client.get(MENUS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_update_a_menu(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.patch(
            menu_url(menu), {'name': 'New name'}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'New name')

    def test_is_active_is_not_writable_directly(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.patch(
            menu_url(menu), {'is_active': False}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        menu.refresh_from_db()
        self.assertTrue(menu.is_active)

    def test_delete_soft_deletes_and_hides_the_menu(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.delete(menu_url(menu))

        self.assertEqual(response.status_code, 204)
        menu.refresh_from_db()
        self.assertFalse(menu.is_active)
        self.assertIsNotNone(menu.deleted_at)
        listing = self.client.get(MENUS_URL)
        self.assertEqual(listing.data['count'], 0)
        detail = self.client.get(menu_url(menu))
        self.assertEqual(detail.status_code, 404)


class ItemWriteTests(CmsNavigationTestCase):
    def test_add_an_external_item(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.post(
            items_url(menu),
            {
                'label': 'Docs',
                'link_type': 'EXTERNAL',
                'external_url': 'https://example.com/docs',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['sort_order'], 0)

    def test_add_a_page_item(self):
        self.authenticate()
        menu = factories.navigation_menu()
        page = factories.page(self.editor)

        response = self.client.post(
            items_url(menu),
            {'label': 'About', 'link_type': 'PAGE', 'page': page.id},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['page'], page.id)

    def test_page_item_requires_a_page(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.post(
            items_url(menu),
            {'label': 'About', 'link_type': 'PAGE'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_external_item_requires_a_url(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.post(
            items_url(menu),
            {'label': 'Docs', 'link_type': 'EXTERNAL'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_cannot_set_both_page_and_external_url(self):
        self.authenticate()
        menu = factories.navigation_menu()
        page = factories.page(self.editor)

        response = self.client.post(
            items_url(menu),
            {
                'label': 'Both',
                'link_type': 'PAGE',
                'page': page.id,
                'external_url': 'https://example.com',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_external_url_rejects_a_non_http_scheme(self):
        self.authenticate()
        menu = factories.navigation_menu()

        response = self.client.post(
            items_url(menu),
            {
                'label': 'Bad',
                'link_type': 'EXTERNAL',
                'external_url': 'javascript:alert(1)',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_items_append_in_order(self):
        self.authenticate()
        menu = factories.navigation_menu()
        first = self.client.post(
            items_url(menu),
            {
                'label': 'A', 'link_type': 'EXTERNAL',
                'external_url': 'https://a.example.com',
            },
            format='json',
        )
        second = self.client.post(
            items_url(menu),
            {
                'label': 'B', 'link_type': 'EXTERNAL',
                'external_url': 'https://b.example.com',
            },
            format='json',
        )

        self.assertEqual(first.data['sort_order'], 0)
        self.assertEqual(second.data['sort_order'], 1)

    def test_nested_child_item(self):
        self.authenticate()
        menu = factories.navigation_menu()
        parent = factories.navigation_item(menu, label='Parent')

        response = self.client.post(
            items_url(menu),
            {
                'label': 'Child', 'link_type': 'EXTERNAL',
                'external_url': 'https://child.example.com',
                'parent': parent.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['parent'], parent.id)

    def test_parent_must_belong_to_the_same_menu(self):
        self.authenticate()
        menu = factories.navigation_menu(key='HEADER')
        other_menu = factories.navigation_menu(key='FOOTER')
        other_item = factories.navigation_item(other_menu)

        response = self.client.post(
            items_url(menu),
            {
                'label': 'Child', 'link_type': 'EXTERNAL',
                'external_url': 'https://example.com',
                'parent': other_item.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_item_cannot_become_its_own_parent(self):
        self.authenticate()
        menu = factories.navigation_menu()
        item = factories.navigation_item(menu)

        response = self.client.patch(
            item_url(menu, item), {'parent': item.id}, format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_a_descendant_cannot_become_an_ancestor(self):
        self.authenticate()
        menu = factories.navigation_menu()
        grandparent = factories.navigation_item(
            menu, label='Grandparent',
        )
        parent = factories.navigation_item(
            menu, label='Parent', parent=grandparent,
        )
        child = factories.navigation_item(
            menu, label='Child', parent=parent,
        )

        response = self.client.patch(
            item_url(menu, grandparent),
            {'parent': child.id},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_update_an_item(self):
        self.authenticate()
        menu = factories.navigation_menu()
        item = factories.navigation_item(menu, label='Old')

        response = self.client.patch(
            item_url(menu, item), {'label': 'New'}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['label'], 'New')

    def test_switching_link_type_requires_the_new_target(self):
        self.authenticate()
        menu = factories.navigation_menu()
        item = factories.navigation_item(menu)

        response = self.client.patch(
            item_url(menu, item),
            {'link_type': 'PAGE'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_switching_link_type_with_target_and_clearing_old_one(self):
        self.authenticate()
        menu = factories.navigation_menu()
        page = factories.page(self.editor)
        item = factories.navigation_item(menu)

        response = self.client.patch(
            item_url(menu, item),
            {
                'link_type': 'PAGE',
                'page': page.id,
                'external_url': '',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['page'], page.id)
        self.assertEqual(response.data['external_url'], '')

    def test_delete_an_item(self):
        self.authenticate()
        menu = factories.navigation_menu()
        item = factories.navigation_item(menu)

        response = self.client.delete(item_url(menu, item))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            CmsNavigationItem.objects.filter(pk=item.pk).exists()
        )

    def test_deleting_a_parent_cascades_to_children(self):
        self.authenticate()
        menu = factories.navigation_menu()
        parent = factories.navigation_item(menu, label='Parent')
        child = factories.navigation_item(
            menu, label='Child', parent=parent,
        )

        self.client.delete(item_url(menu, parent))

        self.assertFalse(
            CmsNavigationItem.objects.filter(pk=child.pk).exists()
        )

    def test_reorder_siblings(self):
        self.authenticate()
        menu = factories.navigation_menu()
        first = factories.navigation_item(menu, label='A')
        second = factories.navigation_item(menu, label='B')

        response = self.client.put(
            reorder_url(menu),
            {'order': [second.id, first.id]},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.sort_order, 0)
        self.assertEqual(first.sort_order, 1)

    def test_reorder_rejects_a_mismatched_set(self):
        self.authenticate()
        menu = factories.navigation_menu()
        item = factories.navigation_item(menu)

        response = self.client.put(
            reorder_url(menu),
            {'order': [item.id, 999999]},
            format='json',
        )

        self.assertEqual(response.status_code, 400)


class PublicNavigationTests(CmsNavigationTestCase):
    def test_unknown_key_returns_404(self):
        response = self.client.get(public_url('MISSING'))

        self.assertEqual(response.status_code, 404)

    def test_inactive_menu_returns_404(self):
        menu = factories.navigation_menu(key='HEADER')
        menu.soft_delete()

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.status_code, 404)

    def test_returns_the_visible_tree(self):
        menu = factories.navigation_menu(key='HEADER')
        factories.navigation_item(
            menu, label='Docs', external_url='https://docs.example.com',
        )

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['label'], 'Docs')
        self.assertEqual(
            response.data[0]['url'], 'https://docs.example.com',
        )

    def test_hidden_item_is_excluded(self):
        menu = factories.navigation_menu(key='HEADER')
        factories.navigation_item(menu, label='Hidden', is_visible=False)

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.data, [])

    def test_hiding_a_parent_prunes_its_children(self):
        menu = factories.navigation_menu(key='HEADER')
        parent = factories.navigation_item(
            menu, label='Parent', is_visible=False,
        )
        factories.navigation_item(
            menu, label='Child', parent=parent,
        )

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.data, [])

    def test_visible_children_are_nested_under_their_parent(self):
        menu = factories.navigation_menu(key='HEADER')
        parent = factories.navigation_item(menu, label='Parent')
        factories.navigation_item(menu, label='Child', parent=parent)

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(len(response.data), 1)
        self.assertEqual(len(response.data[0]['children']), 1)
        self.assertEqual(
            response.data[0]['children'][0]['label'], 'Child',
        )

    def test_page_item_resolves_to_the_published_path(self):
        menu = factories.navigation_menu(key='HEADER')
        page = factories.page(self.editor, slug='about-us')
        self.publish(page)
        factories.navigation_item(menu, label='About', page=page)

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.data[0]['url'], '/about-us/')

    def test_unpublished_page_item_is_excluded(self):
        menu = factories.navigation_menu(key='HEADER')
        page = factories.page(self.editor, slug='draft-page')
        factories.navigation_item(menu, label='Draft', page=page)

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.data, [])

    def test_archived_page_item_is_excluded(self):
        menu = factories.navigation_menu(key='HEADER')
        page = factories.page(self.editor, slug='archived-page')
        self.publish(page)
        page.refresh_from_db()
        page.archived_at = timezone.now()
        page.save()
        factories.navigation_item(menu, label='Archived', page=page)

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.data, [])

    def test_public_read_is_allowed_without_authentication(self):
        menu = factories.navigation_menu(key='HEADER')
        factories.navigation_item(
            menu, external_url='https://example.com',
        )

        response = self.client.get(public_url('HEADER'))

        self.assertEqual(response.status_code, 200)


class DeletePageNavigationGuardTests(CmsNavigationTestCase):
    def setUp(self):
        super().setUp()
        self.deleter = factories.grant(
            factories.user('nav-page-deleter'),
            CmsPage,
            'view_cmspage', 'delete_cmspage',
        )

    def test_page_referenced_by_a_nav_item_cannot_be_deleted(self):
        menu = factories.navigation_menu(key='HEADER')
        page = factories.page(self.editor, slug='linked')
        item = factories.navigation_item(menu, label='Linked', page=page)
        self.client.force_authenticate(user=self.deleter)

        response = self.client.delete(
            f'/api/v1/cms/pages/{page.id}/',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(response.data['errors']['dependencies']), 1)
        self.assertEqual(
            str(response.data['errors']['dependencies'][0]['object_id']),
            str(item.id),
        )
        self.assertTrue(CmsPage.objects.filter(pk=page.pk).exists())

    def test_acknowledge_true_does_not_bypass_the_nav_guard(self):
        """Unlike child pages / ReferenceIndex references,
        navigation-item references are never acknowledgeable: the FK
        is ``PROTECT`` (docs §5.5), so bypassing the guard would only
        trade a friendly 400 for a raw database error."""
        menu = factories.navigation_menu(key='HEADER')
        page = factories.page(self.editor, slug='linked')
        factories.navigation_item(menu, label='Linked', page=page)
        self.client.force_authenticate(user=self.deleter)

        response = self.client.delete(
            f'/api/v1/cms/pages/{page.id}/?acknowledge=true',
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(CmsPage.objects.filter(pk=page.pk).exists())

    def test_page_deletes_once_the_nav_item_is_removed(self):
        menu = factories.navigation_menu(key='HEADER')
        page = factories.page(self.editor, slug='linked')
        item = factories.navigation_item(menu, label='Linked', page=page)
        item.delete()
        self.client.force_authenticate(user=self.deleter)

        response = self.client.delete(
            f'/api/v1/cms/pages/{page.id}/',
        )

        self.assertEqual(response.status_code, 204)

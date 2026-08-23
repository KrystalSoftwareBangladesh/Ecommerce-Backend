from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APITestCase

from category_api.models import Category
from user_api.models import User


class CategoryApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='category-staff',
            email='category-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.client.force_authenticate(user=self.user)

    def test_create_category_allows_null_slug(self):
        response = self.client.post(
            '/api/v1/categories/',
            {
                'name': 'Electronics',
                'description': 'Gadgets and devices',
                'slug': None,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        category = Category.objects.get(pk=response.data['id'])
        self.assertEqual(category.name, 'Electronics')
        self.assertEqual(category.slug, 'electronics')
        self.assertEqual(response.data['slug'], 'electronics')

    def test_summary_returns_category_statistics(self):
        root_in_menu = Category.objects.create(
            name='Electronics',
            show_in_menu=True,
        )
        root_not_in_menu = Category.objects.create(name='Books')
        Category.objects.create(
            name='Phones',
            parent=root_in_menu,
            show_in_menu=True,
        )
        # Inactive categories are still counted; only deleted ones are not.
        Category.objects.create(
            name='Laptops',
            parent=root_in_menu,
            is_active=False,
        )
        deleted_child = Category.objects.create(
            name='Tablets',
            parent=root_not_in_menu,
            show_in_menu=True,
        )
        deleted_child.soft_delete()

        response = self.client.get('/api/v1/categories/summary/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {
            'total_categories': 4,
            'root_categories': 2,
            'sub_categories': 2,
            'menu_categories': 1,
            'sub_menu_categories': 1,
        })

    def test_summary_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get('/api/v1/categories/summary/')

        self.assertEqual(response.status_code, 401)

    def test_create_category_without_slug_generates_slug(self):
        response = self.client.post(
            '/api/v1/categories/',
            {
                'name': 'Home Appliances',
                'description': 'Kitchen and household goods',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        category = Category.objects.get(pk=response.data['id'])
        self.assertEqual(category.name, 'Home Appliances')
        self.assertEqual(category.slug, 'home-appliances')
        self.assertEqual(response.data['slug'], 'home-appliances')


class CategoryMenuPermissionTests(APITestCase):
    """
    `mark-as-menu` and `remove-from-menu` are guarded by the custom
    model permissions `mark_category_as_menu` and
    `remove_category_from_menu`.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='menu-staff',
            email='menu-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.category = Category.objects.create(name='Electronics')
        self.content_type = ContentType.objects.get_for_model(Category)

    def _grant(self, codename):
        permission = Permission.objects.get(
            codename=codename,
            content_type=self.content_type,
        )
        self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)

    def _mark_as_menu_url(self):
        return f'/api/v1/categories/{self.category.id}/mark-as-menu/'

    def _remove_from_menu_url(self):
        return f'/api/v1/categories/{self.category.id}/remove-from-menu/'

    def test_custom_permissions_exist(self):
        codenames = set(
            Permission.objects.filter(
                content_type=self.content_type,
            ).values_list('codename', flat=True)
        )

        self.assertIn('mark_category_as_menu', codenames)
        self.assertIn('remove_category_from_menu', codenames)

    def test_mark_as_menu_requires_authentication(self):
        response = self.client.post(self._mark_as_menu_url())

        self.assertEqual(response.status_code, 401)

    def test_remove_from_menu_requires_authentication(self):
        response = self.client.post(self._remove_from_menu_url())

        self.assertEqual(response.status_code, 401)

    def test_mark_as_menu_forbidden_without_permission(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._mark_as_menu_url())

        self.assertEqual(response.status_code, 403)
        self.category.refresh_from_db()
        self.assertFalse(self.category.show_in_menu)

    def test_remove_from_menu_forbidden_without_permission(self):
        self.category.show_in_menu = True
        self.category.save(update_fields=['show_in_menu'])
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._remove_from_menu_url())

        self.assertEqual(response.status_code, 403)
        self.category.refresh_from_db()
        self.assertTrue(self.category.show_in_menu)

    def test_mark_as_menu_allowed_with_permission(self):
        self._grant('mark_category_as_menu')
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._mark_as_menu_url())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['show_in_menu'])
        self.category.refresh_from_db()
        self.assertTrue(self.category.show_in_menu)

    def test_remove_from_menu_allowed_with_permission(self):
        self.category.show_in_menu = True
        self.category.save(update_fields=['show_in_menu'])
        self._grant('remove_category_from_menu')
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._remove_from_menu_url())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['show_in_menu'])
        self.category.refresh_from_db()
        self.assertFalse(self.category.show_in_menu)

    def test_menu_permissions_are_not_interchangeable(self):
        self._grant('mark_category_as_menu')
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self._remove_from_menu_url())

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_manage_menu_visibility(self):
        superuser = User.objects.create_superuser(
            username='menu-admin',
            email='menu-admin@example.com',
            password='test-pass-123',
        )
        self.client.force_authenticate(user=superuser)

        response = self.client.post(self._mark_as_menu_url())

        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        self.assertTrue(self.category.show_in_menu)

    def test_other_category_actions_still_only_require_authentication(self):
        """
        Guard against widening the permission change: actions outside
        `custom_permissions` must keep working for an authenticated user
        that holds no category model permissions.
        """
        self.client.force_authenticate(user=self.user)

        create_response = self.client.post(
            '/api/v1/categories/',
            {'name': 'Books'},
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)

        summary_response = self.client.get('/api/v1/categories/summary/')
        self.assertEqual(summary_response.status_code, 200)

        reorder_response = self.client.post(
            f'/api/v1/categories/{self.category.id}/reorder/',
            {'display_order': 1},
            format='json',
        )
        self.assertEqual(reorder_response.status_code, 200)

        bulk_response = self.client.post(
            '/api/v1/categories/bulk-menu-update/',
            {'ids': [self.category.id], 'show_in_menu': True},
            format='json',
        )
        self.assertEqual(bulk_response.status_code, 200)

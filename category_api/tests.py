from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
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


class CategoryWriteSerializerTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='category-writer',
            email='category-writer@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.client.force_authenticate(user=self.user)

    def test_create_uses_create_serializer(self):
        response = self.client.post(
            '/api/v1/categories/',
            {'name': 'Electronics'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn('slug', response.data)
        self.assertNotIn('children', response.data)

    def test_update_uses_update_serializer(self):
        category = Category.objects.create(name='Electronics')

        response = self.client.patch(
            f'/api/v1/categories/{category.pk}/',
            {'name': 'Consumer Electronics'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('slug', response.data)
        self.assertNotIn('children', response.data)

    def test_put_without_slug_keeps_existing_slug(self):
        category = Category.objects.create(name='Electronics')

        response = self.client.put(
            f'/api/v1/categories/{category.pk}/',
            {'name': 'Electronics'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.slug, 'electronics')

    def test_put_without_parent_keeps_existing_parent(self):
        root = Category.objects.create(name='Root')
        child = Category.objects.create(name='Child', parent=root)

        response = self.client.put(
            f'/api/v1/categories/{child.pk}/',
            {'name': 'Child'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        child.refresh_from_db()
        self.assertEqual(child.parent_id, root.pk)

    def test_blank_slug_on_update_keeps_existing_slug(self):
        category = Category.objects.create(name='Electronics')

        response = self.client.patch(
            f'/api/v1/categories/{category.pk}/',
            {'slug': ''},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.slug, 'electronics')

    def test_slug_can_still_be_changed_on_update(self):
        category = Category.objects.create(name='Electronics')

        response = self.client.patch(
            f'/api/v1/categories/{category.pk}/',
            {'slug': 'gadgets'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.slug, 'gadgets')

    def test_parent_can_still_be_cleared_explicitly(self):
        root = Category.objects.create(name='Root')
        child = Category.objects.create(name='Child', parent=root)

        response = self.client.patch(
            f'/api/v1/categories/{child.pk}/',
            {'parent': None},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        child.refresh_from_db()
        self.assertIsNone(child.parent_id)

    def test_category_cannot_be_its_own_parent(self):
        category = Category.objects.create(name='Electronics')

        response = self.client.patch(
            f'/api/v1/categories/{category.pk}/',
            {'parent': category.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('parent', response.data['errors'])
        category.refresh_from_db()
        self.assertIsNone(category.parent_id)

    def test_category_cannot_be_moved_under_its_own_subcategory(self):
        root = Category.objects.create(name='Root')
        child = Category.objects.create(name='Child', parent=root)
        grandchild = Category.objects.create(name='Grandchild', parent=child)

        response = self.client.patch(
            f'/api/v1/categories/{root.pk}/',
            {'parent': grandchild.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('parent', response.data['errors'])
        root.refresh_from_db()
        self.assertIsNone(root.parent_id)

    def test_category_can_be_moved_under_an_unrelated_category(self):
        root = Category.objects.create(name='Root')
        other = Category.objects.create(name='Other')

        response = self.client.patch(
            f'/api/v1/categories/{root.pk}/',
            {'parent': other.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        root.refresh_from_db()
        self.assertEqual(root.parent_id, other.pk)

    def test_soft_deleted_category_is_rejected_as_parent_on_create(self):
        deleted = Category.objects.create(
            name='Archived',
            deleted_at=timezone.now(),
        )

        response = self.client.post(
            '/api/v1/categories/',
            {'name': 'Electronics', 'parent': deleted.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('parent', response.data['errors'])

    def test_soft_deleted_category_is_rejected_as_parent_on_update(self):
        deleted = Category.objects.create(
            name='Archived',
            deleted_at=timezone.now(),
        )
        category = Category.objects.create(name='Electronics')

        response = self.client.patch(
            f'/api/v1/categories/{category.pk}/',
            {'parent': deleted.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('parent', response.data['errors'])


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

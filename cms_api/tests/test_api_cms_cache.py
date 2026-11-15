# cms_api/tests/test_api_cms_cache.py
"""Public CMS response caching and invalidation (docs/cms-
architecture.md §10, AD-12, Phase 5C).

The "cms" cache alias is ``DummyCache`` under ``test_settings`` (every
get() misses, every set() is a no-op) so the rest of the suite is
unaffected by caching. This module opts into a real, isolated
``LocMemCache`` for the one alias it needs, and clears it between
tests since ``LocMemCache`` with no explicit ``LOCATION`` shares one
process-wide store.

``transaction.on_commit`` never fires inside ``TestCase`` (the whole
test runs inside one transaction that is rolled back, never
committed), so every write that queues invalidation is wrapped in
``self.captureOnCommitCallbacks(...)``.

Concurrency tests use real threads (never sequential calls alone):
the failure modes being guarded against are interleavings, and the
module's safety claim is per-key atomicity on the cache backend.
"""
import threading
import time
from unittest import mock

from django.conf import settings
from django.db import transaction
from django.test import override_settings

from rest_framework.test import APITestCase

from cms_api.models import CmsPage
from cms_api.services import (
    add_navigation_item,
    archive_page,
    archive_section,
    delete_menu,
    delete_page,
    delete_section,
    publish_page,
    publish_section,
    remove_navigation_item,
    remove_page_section,
    reorder_navigation_items,
    restore_page,
    rollback_page,
    unpublish_page,
    unpublish_section,
    update_menu,
    update_navigation_item,
)
from cms_api.services import cache as cms_cache
from cms_api.tests import factories


PUBLIC_PAGES_URL = '/api/v1/cms/public/pages/'
SITEMAP_URL = '/api/v1/cms/public/sitemap/'
SECTION_TYPES_URL = '/api/v1/cms/section-types/'
PREVIEW_URL = '/api/v1/cms/public/preview/{token}/'


def navigation_url(key):
    return f'/api/v1/cms/public/navigation/{key}/'


CMS_LOCMEM_CACHES = {
    **settings.CACHES,
    'cms': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}


@override_settings(CACHES=CMS_LOCMEM_CACHES)
class CmsCacheTestCase(APITestCase):
    def setUp(self):
        self.owner = factories.user('cms-cache-owner')
        # LocMemCache with no explicit LOCATION shares one process-
        # wide store across every instance of this alias, so a key
        # from a previous test would otherwise leak into this one.
        cms_cache._cache().clear()

    def get_page(self, path):
        return self.client.get(PUBLIC_PAGES_URL, {'path': path})

    def published_page(self, slug='about', **kwargs):
        page = factories.page(self.owner, slug=slug, **kwargs)
        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=page, user=self.owner)
        return page


class CacheAliasTests(CmsCacheTestCase):
    def test_cms_alias_resolves_under_test_settings(self):
        """``caches["cms"]`` must resolve to a real backend — under
        plain ``test_settings`` that is ``DummyCache`` (see module
        docstring); here it is the ``LocMemCache`` override."""
        cms_cache._cache().set('cms-cache-smoke-test', 'ok', 30)

        self.assertEqual(
            cms_cache._cache().get('cms-cache-smoke-test'), 'ok',
        )


class PagePublishInvalidationTests(CmsCacheTestCase):
    def test_republish_serves_fresh_content_without_ttl_wait(self):
        page = self.published_page(title='Original title')
        self.assertEqual(
            self.get_page(page.url_path).data['title'],
            'Original title',
        )

        page.refresh_from_db()
        page.title = 'Updated title'
        page.save()
        page.save_revision(user=self.owner)

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            publish_page(page=page, user=self.owner)

        # Not yet invalidated: still the stale cached payload.
        self.assertEqual(
            self.get_page(page.url_path).data['title'],
            'Original title',
        )

        for callback in callbacks:
            callback()

        # Invalidated: the very next read is fresh, no TTL wait.
        self.assertEqual(
            self.get_page(page.url_path).data['title'],
            'Updated title',
        )

    def test_rollback_invalidates_the_cached_detail(self):
        page = self.published_page(slug='rollback-target', title='V1')
        self.get_page(page.url_path)
        first_revision = page.live_revision

        page.refresh_from_db()
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=page, user=self.owner)
        self.assertEqual(self.get_page(page.url_path).data['title'], 'V2')

        with self.captureOnCommitCallbacks(execute=True):
            rollback_page(
                page=page, revision_id=first_revision.id, user=self.owner,
            )

        self.assertEqual(self.get_page(page.url_path).data['title'], 'V1')

    def test_unpublish_removes_page_from_cached_reads(self):
        page = self.published_page()
        self.assertEqual(self.get_page(page.url_path).status_code, 200)

        with self.captureOnCommitCallbacks(execute=True):
            unpublish_page(page=page, user=self.owner)

        self.assertEqual(self.get_page(page.url_path).status_code, 404)

    def test_wagtail_native_publish_also_invalidates(self):
        """Publishing through the Page-specific Wagtail action
        directly (bypassing cms_api's ``publish_page`` service) is
        what Wagtail Admin does. The signal-based receiver must catch
        this path too, not only the DRF one."""
        page = self.published_page(title='Admin before')
        self.get_page(page.url_path)

        page.refresh_from_db()
        page.title = 'Admin after'
        page.save()
        revision = page.save_revision(user=self.owner)

        with self.captureOnCommitCallbacks(execute=True):
            page.specific.publish(
                revision, user=self.owner, skip_permission_checks=True,
            )

        self.assertEqual(
            self.get_page(page.url_path).data['title'], 'Admin after',
        )


class PageLifecycleInvalidationTests(CmsCacheTestCase):
    def test_archive_removes_page_from_cached_list_and_sitemap(self):
        page = self.published_page(slug='old-page')
        self.client.get(PUBLIC_PAGES_URL)
        self.client.get(SITEMAP_URL)

        with self.captureOnCommitCallbacks(execute=True):
            archive_page(page=page, user=self.owner)

        listing = self.client.get(PUBLIC_PAGES_URL).data
        sitemap = self.client.get(SITEMAP_URL).data
        self.assertFalse(any(row['id'] == page.pk for row in listing))
        self.assertFalse(any(row['id'] == page.pk for row in sitemap))

    def test_restore_brings_page_back_into_cached_list(self):
        page = self.published_page(slug='restorable')
        with self.captureOnCommitCallbacks(execute=True):
            archive_page(page=page, user=self.owner)
        self.client.get(PUBLIC_PAGES_URL)

        with self.captureOnCommitCallbacks(execute=True):
            restore_page(page=page, user=self.owner)

        listing = self.client.get(PUBLIC_PAGES_URL).data
        self.assertTrue(any(row['id'] == page.pk for row in listing))

    def test_delete_drops_the_cached_detail(self):
        page = self.published_page(slug='to-delete')
        self.get_page(page.url_path)

        with self.captureOnCommitCallbacks(execute=True):
            delete_page(page=page, user=self.owner)

        _generation, cached = cms_cache.get_page_detail(page.pk)
        self.assertIsNone(cached)


class DescendantPathInvalidationTests(CmsCacheTestCase):
    def test_parent_slug_change_invalidates_live_descendant_cache(self):
        parent = self.published_page(slug='parent', title='Parent')
        child = factories.page(
            self.owner, slug='child', title='Child', parent=parent,
        )
        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=child, user=self.owner)

        self.assertEqual(child.url_path, '/parent/child/')
        self.get_page(child.url_path)  # prime the child's cache

        parent.refresh_from_db()
        parent.slug = 'parent-renamed'
        parent.save()
        parent.save_revision(user=self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=parent, user=self.owner)

        child.refresh_from_db()
        self.assertEqual(child.url_path, '/parent-renamed/child/')
        response = self.get_page(child.url_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Child')
        self.assertEqual(response.data['path'], '/parent-renamed/child/')


class SectionInvalidationTests(CmsCacheTestCase):
    def setUp(self):
        super().setUp()
        self.section = factories.section(
            name='Promo', user=self.owner,
        )
        with self.captureOnCommitCallbacks(execute=True):
            publish_section(section=self.section, user=self.owner)
        self.page = self.published_page(slug='with-section')
        factories.page_section(
            self.page, self.owner, global_section=self.section.pk,
        )
        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=self.page, user=self.owner)

    def _section_heading(self, response):
        row = response.data['sections'][0]
        return row['content'][0]['value']['heading']

    def test_global_section_publish_invalidates_every_referencing_page(
        self,
    ):
        self.assertEqual(
            self._section_heading(self.get_page(self.page.url_path)),
            'Welcome',
        )

        self.section.content = factories.hero_content(
            heading='New promo',
        )
        self.section.save()
        self.section.save_revision(user=self.owner)

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            publish_section(section=self.section, user=self.owner)

        # Still stale until the commit callback actually runs.
        self.assertEqual(
            self._section_heading(self.get_page(self.page.url_path)),
            'Welcome',
        )
        for callback in callbacks:
            callback()

        self.assertEqual(
            self._section_heading(self.get_page(self.page.url_path)),
            'New promo',
        )

    def test_section_unpublish_invalidates_affected_pages(self):
        self.get_page(self.page.url_path)

        with self.captureOnCommitCallbacks(execute=True):
            unpublish_section(section=self.section, user=self.owner)

        response = self.get_page(self.page.url_path)
        self.assertEqual(response.data['sections'], [])

    def test_section_archive_invalidates_affected_pages(self):
        self.get_page(self.page.url_path)

        with self.captureOnCommitCallbacks(execute=True):
            archive_section(section=self.section, user=self.owner)

        response = self.get_page(self.page.url_path)
        self.assertEqual(response.data['sections'], [])

    def test_unreferenced_section_delete_does_not_error(self):
        orphan = factories.section(name='Orphan', user=self.owner)

        with self.captureOnCommitCallbacks(execute=True):
            delete_section(section=orphan, user=self.owner)

        orphan.refresh_from_db()
        self.assertFalse(orphan.is_active)


class PublishedSectionFanOutTests(CmsCacheTestCase):
    """A published page embeds a global section through its
    *published* revision, so an unpublished draft dropping the
    section must not hide the page from section-change invalidation.

    ``ReferenceIndex`` (the pre-fix fan-out) tracks each page's
    current, possibly draft, composition — exactly the case below.
    """

    def setUp(self):
        super().setUp()
        self.section = factories.section(name='Promo', user=self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            publish_section(section=self.section, user=self.owner)
        self.page = self.published_page(slug='draft-drops-section')
        self.row = factories.page_section(
            self.page, self.owner, global_section=self.section.pk,
        )
        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=self.page, user=self.owner)

    def _heading(self, response):
        row = response.data['sections'][0]
        return row['content'][0]['value']['heading']

    def test_draft_dropping_section_still_invalidates_on_publish(self):
        # 2. An unpublished draft that removes the section; the live
        # revision — and so the public payload — keeps it.
        remove_page_section(
            page=self.page, section=self.row, user=self.owner,
        )

        # 3. Cache the published public response.
        self.assertEqual(
            self._heading(self.get_page(self.page.url_path)),
            'Welcome',
        )

        # 4. Update and publish the section.
        self.section.content = factories.hero_content(heading='New promo')
        self.section.save()
        self.section.save_revision(user=self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            publish_section(section=self.section, user=self.owner)

        # 5. The very next public request serves the updated
        # published content, no TTL wait.
        self.assertEqual(
            self._heading(self.get_page(self.page.url_path)),
            'New promo',
        )


class NavigationInvalidationTests(CmsCacheTestCase):
    def setUp(self):
        super().setUp()
        self.menu = factories.navigation_menu(user=self.owner)
        self.item = factories.navigation_item(
            self.menu, label='Home',
        )

    def test_new_item_invalidates_the_menu_cache(self):
        first = self.client.get(navigation_url(self.menu.key)).data
        self.assertEqual(len(first), 1)

        with self.captureOnCommitCallbacks(execute=True):
            add_navigation_item(
                menu=self.menu,
                validated_data={
                    'label': 'About', 'link_type': 'EXTERNAL',
                    'external_url': 'https://example.com/about',
                },
                user=self.owner,
            )

        second = self.client.get(navigation_url(self.menu.key)).data
        self.assertEqual(len(second), 2)

    def test_item_update_invalidates_the_menu_cache(self):
        self.client.get(navigation_url(self.menu.key))

        with self.captureOnCommitCallbacks(execute=True):
            update_navigation_item(
                menu=self.menu, item=self.item,
                validated_data={'label': 'Home (renamed)'},
                user=self.owner,
            )

        response = self.client.get(navigation_url(self.menu.key))
        self.assertEqual(response.data[0]['label'], 'Home (renamed)')

    def test_item_removal_invalidates_the_menu_cache(self):
        self.client.get(navigation_url(self.menu.key))

        with self.captureOnCommitCallbacks(execute=True):
            remove_navigation_item(
                menu=self.menu, item=self.item, user=self.owner,
            )

        response = self.client.get(navigation_url(self.menu.key))
        self.assertEqual(response.data, [])

    def test_reorder_invalidates_the_menu_cache(self):
        second_item = factories.navigation_item(
            self.menu, label='About',
        )
        self.client.get(navigation_url(self.menu.key))

        with self.captureOnCommitCallbacks(execute=True):
            reorder_navigation_items(
                menu=self.menu, parent_id=None,
                order=[second_item.pk, self.item.pk],
                user=self.owner,
            )

        response = self.client.get(navigation_url(self.menu.key))
        self.assertEqual(response.data[0]['label'], 'About')

    def test_menu_rename_invalidates_both_old_and_new_key(self):
        self.client.get(navigation_url('HEADER'))

        with self.captureOnCommitCallbacks(execute=True):
            update_menu(
                menu=self.menu, validated_data={'key': 'MAIN'},
                user=self.owner,
            )

        self.assertIsNone(cms_cache.get_navigation('HEADER')[1])
        self.assertEqual(
            self.client.get(navigation_url('MAIN')).status_code, 200,
        )

    def test_menu_delete_invalidates_its_public_cache(self):
        self.client.get(navigation_url(self.menu.key))

        with self.captureOnCommitCallbacks(execute=True):
            delete_menu(menu=self.menu, user=self.owner)

        self.assertEqual(
            self.client.get(navigation_url(self.menu.key)).status_code,
            404,
        )

    def test_unknown_menu_key_is_never_cached(self):
        self.assertEqual(
            self.client.get(navigation_url('NOPE')).status_code, 404,
        )
        self.assertIsNone(cms_cache.get_navigation('NOPE')[1])

    def test_page_publish_invalidates_every_active_menu(self):
        """A navigation tree embeds a PAGE item's resolved published
        state and path, so any page publish must invalidate every
        active menu, not just menus that were themselves edited."""
        page = factories.page(self.owner, slug='nav-target')
        factories.navigation_item(self.menu, page=page, label='Target')
        self.client.get(navigation_url(self.menu.key))
        unpublished = self.client.get(navigation_url(self.menu.key)).data
        self.assertEqual(
            [node for node in unpublished if node['label'] == 'Target'],
            [],
        )

        with self.captureOnCommitCallbacks(execute=True):
            publish_page(page=page, user=self.owner)

        published_tree = self.client.get(navigation_url(self.menu.key)).data
        self.assertTrue(
            any(node['label'] == 'Target' for node in published_tree)
        )


class SectionTypesSharedCacheTests(CmsCacheTestCase):
    def test_response_is_identical_and_shared_across_users(self):
        other = factories.user('cms-cache-other')

        self.client.force_authenticate(self.owner)
        first = self.client.get(SECTION_TYPES_URL)

        self.client.force_authenticate(other)
        second = self.client.get(SECTION_TYPES_URL)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, second.data)
        self.assertIsNotNone(cms_cache.get_section_types()[1])


class PreviewNeverCachedTests(CmsCacheTestCase):
    def test_preview_still_sends_cache_control_no_store(self):
        from cms_api.services import issue_preview_token
        from cms_api.services.preview import KIND_PAGE

        editor = factories.grant(
            factories.user('cms-cache-previewer'),
            CmsPage, 'change_cmspage',
        )
        page = factories.page(editor, slug='previewed')
        token, _revision = issue_preview_token(
            kind=KIND_PAGE, obj=page, user=editor, revision_id=None,
        )
        self.client.force_authenticate(editor)

        response = self.client.get(PREVIEW_URL.format(token=token))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')


class RolledBackTransactionTests(CmsCacheTestCase):
    def test_rolled_back_publish_never_invalidates_committed_cache(self):
        page = self.published_page(title='Stable title')
        self.assertEqual(
            self.get_page(page.url_path).data['title'], 'Stable title',
        )

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                with self.captureOnCommitCallbacks(execute=True):
                    page.refresh_from_db()
                    page.title = 'Should never be visible'
                    page.save()
                    page.save_revision(user=self.owner)
                    publish_page(page=page, user=self.owner)
                    raise RuntimeError('force rollback of this publish')

        self.assertEqual(
            self.get_page(page.url_path).data['title'], 'Stable title',
        )


class SlowCache:
    """Cache proxy that pauses briefly after every delete or
    generation increment — the way a loaded remote cache does, where
    an invalidation takes real time.

    Without this, in-process threads cannot reproduce a cross-worker
    interleaving at all: the GIL plus ``LocMemCache``'s single
    per-store lock serialize cache operations so tightly that the
    gaps between one call's backend operations never open. Widening
    those gaps is exactly what makes a multi-step write or
    invalidation race — and what lets these tests catch one.
    """

    def __init__(self, inner, delay):
        self._inner = inner
        self._delay = delay

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name not in ('delete', 'delete_many', 'incr'):
            return attr

        def slow(*args, **kwargs):
            result = attr(*args, **kwargs)
            time.sleep(self._delay)
            return result

        return slow


class ConcurrentCacheUpdateTests(CmsCacheTestCase):
    """Registry-free caching must stay consistent when several
    workers cache and invalidate at once (docs/cms-architecture.md
    §10). Real threads, not sequential calls: the failure mode being
    guarded against is an interleaving.

    Both tests run on ``LocMemCache``, whose per-operation locking
    makes single-key writes/deletes atomic the same way Redis does —
    the module's only concurrency assumption is that per-key
    atomicity, so the same guarantee holds cross-process on a shared
    Redis. ``LocMemCache`` itself is per-process and shares nothing
    across processes; multi-process behaviour cannot be exercised
    here and is not claimed.
    """

    def test_concurrent_sets_all_land_and_invalidate_cleanly(self):
        page_ids = list(range(32))
        start = threading.Barrier(len(page_ids), timeout=30)

        def cache_detail(page_id):
            start.wait()
            generation, _cached = cms_cache.get_page_detail(page_id)
            cms_cache.set_page_detail(generation, page_id, {'id': page_id})

        threads = [
            threading.Thread(target=cache_detail, args=(page_id,))
            for page_id in page_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for page_id in page_ids:
            self.assertIsNotNone(cms_cache.get_page_detail(page_id)[1])

        cms_cache.invalidate_page_detail(*page_ids)

        for page_id in page_ids:
            self.assertIsNone(cms_cache.get_page_detail(page_id)[1])

    def test_write_racing_invalidation_is_never_stranded(self):
        """A write interleaved with its own invalidation may land
        after it (the cache-aside race), but must never become
        readable under a later generation — a payload stranded past
        every future invalidation would serve stale content until its
        TTL expired. Writers capture their generation exactly the way
        a request does (services/cache.py's contract); invalidation
        steps are deliberately slow here (see ``SlowCache``) so writes
        really do interleave with them.
        """
        page_ids = list(range(8))
        iterations = 100
        slow = SlowCache(cms_cache._cache(), delay=0.001)
        start = threading.Barrier(len(page_ids) + 1, timeout=30)

        def writer(page_id):
            start.wait()
            for _ in range(iterations):
                generation, _cached = cms_cache.get_page_detail(page_id)
                cms_cache.set_page_detail(
                    generation, page_id, {'id': page_id},
                )

        def invalidator():
            start.wait()
            for _ in range(iterations):
                cms_cache.invalidate_page_detail(*page_ids)

        with mock.patch.object(cms_cache, '_cache', return_value=slow):
            threads = [
                threading.Thread(target=writer, args=(page_id,))
                for page_id in page_ids
            ]
            threads.append(threading.Thread(target=invalidator))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            cms_cache.invalidate_page_detail(*page_ids)

            for page_id in page_ids:
                self.assertIsNone(cms_cache.get_page_detail(page_id)[1])


class CacheAsideRaceTests(CmsCacheTestCase):
    """The cache-aside race (services/cache.py module docstring): a
    request that read pre-publish content before the publishing
    transaction committed must not be able to write that content into
    the active cache namespace after the on-commit invalidation ran.

    The interleaving is forced deterministically and single-threaded:
    the "old" request is paused exactly at its cache write — it has
    already read the old content and nothing is cached yet — the
    publish and its completed invalidation run inside that pause, and
    the request is then resumed. Subsequent requests must never
    receive the old content.
    """

    def _pause_first_write(self, setter_name, during_pause):
        """Patch ``cms_cache.<setter_name>`` so its first call runs
        ``during_pause`` before performing the write (the request is
        suspended between reading old content and caching it), and
        return ``(patcher, state)`` where ``state['generation']`` is
        the generation that write was made under."""
        real_set = getattr(cms_cache, setter_name)
        state = {'paused': False, 'generation': None}

        def pausing_set(generation, *args, **kwargs):
            if not state['paused']:
                state['paused'] = True
                state['generation'] = generation
                during_pause()
            return real_set(generation, *args, **kwargs)

        return (
            mock.patch.object(cms_cache, setter_name, pausing_set),
            state,
        )

    def test_stale_detail_write_after_invalidation_is_unreachable(self):
        page = self.published_page(title='Original title')

        def publish_and_invalidate():
            page.refresh_from_db()
            page.title = 'Updated title'
            page.save()
            page.save_revision(user=self.owner)
            with self.captureOnCommitCallbacks(execute=True):
                publish_page(page=page, user=self.owner)

        patcher, state = self._pause_first_write(
            'set_page_detail', publish_and_invalidate,
        )
        with patcher:
            # The old request: reads the pre-publish content, is
            # paused at its cache write while the publish and its
            # invalidation complete, then resumes and writes.
            old_response = self.get_page(page.url_path)

        # The request really did read (and serve) the old content...
        self.assertEqual(old_response.data['title'], 'Original title')
        # ...and its resumed write really did land — under the
        # pre-publish generation, where the pre-fix literal keys
        # would have made it the active cache entry.
        stale_key = cms_cache._payload_key(
            cms_cache._page_detail_base(page.pk), state['generation'],
        )
        self.assertEqual(
            cms_cache._cache().get(stale_key)['title'], 'Original title',
        )

        # The invalidation moved the namespace past that generation,
        # so the stale payload is unreachable and nothing stale is
        # served.
        self.assertNotEqual(
            state['generation'], cms_cache.get_page_detail(page.pk)[0],
        )
        self.assertIsNone(cms_cache.get_page_detail(page.pk)[1])
        self.assertEqual(
            self.get_page(page.url_path).data['title'], 'Updated title',
        )

    def test_stale_list_write_after_invalidation_is_unreachable(self):
        page = self.published_page(slug='listed', title='Original title')

        def publish_and_invalidate():
            page.refresh_from_db()
            page.title = 'Updated title'
            page.save()
            page.save_revision(user=self.owner)
            with self.captureOnCommitCallbacks(execute=True):
                publish_page(page=page, user=self.owner)

        patcher, state = self._pause_first_write(
            'set_pages_list', publish_and_invalidate,
        )
        with patcher:
            old_response = self.client.get(PUBLIC_PAGES_URL)

        self.assertEqual(
            [
                row['title'] for row in old_response.data
                if row['id'] == page.pk
            ],
            ['Original title'],
        )
        self.assertIsNone(cms_cache.get_pages_list()[1])
        listing = self.client.get(PUBLIC_PAGES_URL).data
        self.assertEqual(
            [row['title'] for row in listing if row['id'] == page.pk],
            ['Updated title'],
        )


class GenerationCommitTests(CmsCacheTestCase):
    """Generations advance only after successful database commits
    (services/cache.py: invalidation runs from
    ``transaction.on_commit``): queued before the commit, applied
    after it, and discarded entirely by a rollback."""

    def _primed_page(self):
        page = self.published_page(title='V1')
        self.get_page(page.url_path)
        return page

    def test_generation_advances_only_when_commit_callbacks_run(self):
        page = self._primed_page()
        before, _cached = cms_cache.get_page_detail(page.pk)

        page.refresh_from_db()
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.owner)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            publish_page(page=page, user=self.owner)

        self.assertTrue(callbacks)
        queued, _cached = cms_cache.get_page_detail(page.pk)
        self.assertEqual(before, queued)

        for callback in callbacks:
            callback()

        after, _cached = cms_cache.get_page_detail(page.pk)
        self.assertNotEqual(before, after)

    def test_rolled_back_publish_leaves_generations_untouched(self):
        page = self._primed_page()
        before, _cached = cms_cache.get_page_detail(page.pk)

        # captureOnCommitCallbacks sits OUTSIDE the atomic block on
        # purpose: a rolled-back transaction discards its on_commit
        # callbacks (django.db BaseDatabaseWrapper.rollback clears
        # run_on_commit), and the capture must observe exactly the
        # post-rollback state production would run.
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    page.refresh_from_db()
                    page.title = 'Should never be visible'
                    page.save()
                    page.save_revision(user=self.owner)
                    publish_page(page=page, user=self.owner)
                    raise RuntimeError('force rollback of this publish')

        self.assertEqual(callbacks, [])
        after, _cached = cms_cache.get_page_detail(page.pk)
        self.assertEqual(before, after)


class AtomicGenerationTests(CmsCacheTestCase):
    """Generation counters use only atomic cache operations: ``add``
    (set-if-absent) and ``incr`` (a single counter step) — ``SETNX``
    and a Lua ``EXISTS``+``INCRBY`` under Redis (django-redis), a
    per-operation lock under ``LocMemCache``. Every increment must
    land: a lost update would leave a stale generation active."""

    def test_concurrent_bumps_never_lose_an_increment(self):
        bumpers = 8
        per_bumper = 25
        start = threading.Barrier(bumpers, timeout=30)
        before, _cached = cms_cache.get_page_detail(1)

        def bump():
            start.wait()
            for _ in range(per_bumper):
                cms_cache.invalidate_page_detail(1)

        threads = [threading.Thread(target=bump) for _ in range(bumpers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        after, _cached = cms_cache.get_page_detail(1)
        self.assertEqual(after - before, bumpers * per_bumper)


class DummyCacheInvalidationTests(APITestCase):
    """The suite's default "cms" alias is ``DummyCache``, and every
    other test module runs these code paths with caching off —
    reads and invalidation must stay silent no-ops there, never    raise."""

    def test_invalidation_and_reads_are_silent_on_dummy_cache(self):
        generation, cached = cms_cache.get_page_detail(7)
        self.assertIsNone(cached)

        cms_cache.invalidate_page_detail(7)
        cms_cache.invalidate_pages_list()
        cms_cache.invalidate_sitemap()
        cms_cache.invalidate_navigation('HEADER')

        self.assertIsNone(cms_cache.get_navigation('HEADER')[1])

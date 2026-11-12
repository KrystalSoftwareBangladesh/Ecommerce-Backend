from .settings import * # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    # DummyCache: tests get the real code path (cms_api/services/
    # cache.py never branches on "is caching on"), but every get()
    # misses and every set() is a no-op, so no cached CMS response
    # can leak across tests sharing this process (docs/cms-
    # architecture.md §10: "test settings keep the cache off ... to
    # avoid cross-test state"). Cache-behaviour tests override this
    # alias to LocMemCache explicitly (see test_api_cms_cache.py).
    'cms': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    },
}

# category_api/services/cache.py
from django.conf import settings
from django.core.cache import cache


CACHE_KEY_PREFIX = "categories:navigation"
CACHE_REGISTRY_KEY = f"{CACHE_KEY_PREFIX}:registry"


def _build_navigation_cache_key(action, query_params):
    """
    Build a cache key for a navigation action (`roots` or `children`) from
    its query parameters, so that different parameter values never share a
    cache entry.
    """
    normalized_params = "&".join(
        f"{key}={value}"
        for key, value in sorted(query_params.items())
    )

    return f"{CACHE_KEY_PREFIX}:{action}:{normalized_params}"


def get_cached_category_navigation(*, action, query_params):
    return cache.get(_build_navigation_cache_key(action, query_params))


def set_cached_category_navigation(*, action, query_params, data):
    key = _build_navigation_cache_key(action, query_params)
    ttl = settings.CATEGORY_NAVIGATION_CACHE_TTL

    cache.set(key, data, ttl)

    # Track every key written so invalidation can clear them all without
    # depending on a cache backend's pattern-matching support.
    registered_keys = cache.get(CACHE_REGISTRY_KEY) or set()
    registered_keys.add(key)
    cache.set(CACHE_REGISTRY_KEY, registered_keys, ttl)


def invalidate_category_navigation_cache():
    registered_keys = cache.get(CACHE_REGISTRY_KEY) or set()

    if registered_keys:
        cache.delete_many(list(registered_keys))

    cache.delete(CACHE_REGISTRY_KEY)

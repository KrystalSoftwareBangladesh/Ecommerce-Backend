from rest_framework.filters import BaseFilterBackend


class SearchFilter(BaseFilterBackend):
    """
    A custom search filter that allows more flexible query handling.
    """

    def get_search_fields(self, view):
        """
        Returns the search fields defined on the view.
        """
        return getattr(view, 'search_fields', None)
        # return getattr(view, 'search_fields', [])

    def filter_queryset(self, request, queryset, view):
        """
        Perform custom filtering based on search fields and query parameters.
        """
        search_fields = self.get_search_fields(view)
        search_param = request.query_params.get(
            'search')  # Default query param is `search`

        if not search_fields or not search_param:
            return queryset  # No search fields or query parameter, return unfiltered queryset  # noqa

        # Build a query dynamically
        from django.db.models import Q
        query = Q()
        for field in search_fields:
            # Case-insensitive search
            query |= Q(**{f"{field}__icontains": search_param})

        return queryset.filter(query)

# category_api/filters.py
import django_filters
from category_api.models import Category


class CategoryFilter(django_filters.FilterSet):
    """
    Custom filter for Category model.
    """
    is_parent = django_filters.BooleanFilter(
        field_name='parent',
        method='filter_is_parent',
        help_text='Filter categories by whether they are parent (root) or not'
    )
    is_menu = django_filters.BooleanFilter(
        field_name="show_in_menu",
        help_text="Filter categories by whether they are shown in the storefront menu", # noqa
    )

    class Meta:
        model = Category
        fields = ['parent', 'is_active', 'show_in_menu']

    @staticmethod
    def filter_is_parent(queryset, name, value):
        """
        Filter for parent-only categories (where parent is NULL).

        Args:
            queryset: The category queryset
            name: Field name (not used)
            value: Boolean value
                True: Return only parent categories (parent is NULL)
                False: Return only child categories (parent is NOT NULL)
        """
        if value is True:
            # Return only parent (root) categories
            return queryset.filter(parent__isnull=True)
        elif value is False:
            # Return only child categories
            return queryset.filter(parent__isnull=False)
        return queryset

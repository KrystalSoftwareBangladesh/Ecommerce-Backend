# category_api/filters.py
import django_filters
from django.db.models import Exists, OuterRef

from blog_api.models import BlogPost
from category_api.models import Category
from product_api.models import Product
from supplier_api.models import Supplier


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
    no_subcategory = django_filters.BooleanFilter(
        method='filter_no_subcategory',
        help_text=(
            'If true, only categories with no active subcategory; '
            'if false, only categories with at least one.'
        ),
    )
    no_product = django_filters.BooleanFilter(
        method='filter_no_product',
        help_text=(
            'If true, only categories with no active product; '
            'if false, only categories with at least one.'
        ),
    )
    no_blog_post = django_filters.BooleanFilter(
        method='filter_no_blog_post',
        help_text=(
            'If true, only categories with no active blog post; '
            'if false, only categories with at least one.'
        ),
    )
    no_supplier = django_filters.BooleanFilter(
        method='filter_no_supplier',
        help_text=(
            'If true, only categories with no active supplier; '
            'if false, only categories with at least one.'
        ),
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

    @staticmethod
    def filter_by_exists(queryset, value, condition):
        """
        Filter on whether an active related record exists.

        Args:
            queryset: The category queryset
            value: Boolean value
                True: categories with no matching record
                False: categories with at least one matching record
            condition: an Exists()-ready subquery on the related model
        """
        if value is True:
            return queryset.filter(~Exists(condition))
        elif value is False:
            return queryset.filter(Exists(condition))
        return queryset

    def filter_no_subcategory(self, queryset, name, value):
        condition = Category.objects.filter(
            parent_id=OuterRef('pk'),
            is_active=True,
            deleted_at__isnull=True,
        )
        return self.filter_by_exists(queryset, value, condition)

    def filter_no_product(self, queryset, name, value):
        condition = Product.objects.filter(
            categories=OuterRef('pk'),
            is_active=True,
            deleted_at__isnull=True,
        )
        return self.filter_by_exists(queryset, value, condition)

    def filter_no_blog_post(self, queryset, name, value):
        condition = BlogPost.objects.filter(
            categories=OuterRef('pk'),
            is_active=True,
            deleted_at__isnull=True,
        )
        return self.filter_by_exists(queryset, value, condition)

    def filter_no_supplier(self, queryset, name, value):
        condition = Supplier.objects.filter(
            categories=OuterRef('pk'),
            is_active=True,
            deleted_at__isnull=True,
        )
        return self.filter_by_exists(queryset, value, condition)

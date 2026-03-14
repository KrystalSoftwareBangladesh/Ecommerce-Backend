import django_filters

from account_api.models import AccountType, ChartOfAccount


class ChartOfAccountFilter(django_filters.FilterSet):
    account_type = django_filters.CharFilter(method='filter_account_type')
    parent = django_filters.NumberFilter(field_name='parent__id')
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = ChartOfAccount
        fields = ['account_type', 'parent', 'is_active']

    def filter_account_type(self, queryset, name, value):
        raw_values = []
        if self.request is not None:
            raw_values.extend(self.request.query_params.getlist(name))
            raw_values.extend(self.request.query_params.getlist(f'{name}[]'))

        if not raw_values and value:
            raw_values = [value]

        account_types = []
        for raw_value in raw_values:
            if raw_value is None:
                continue

            for item in str(raw_value).split(','):
                cleaned_item = item.strip()
                if cleaned_item:
                    account_types.append(cleaned_item)

        if not account_types:
            return queryset

        valid_account_types = {
            account_type for account_type, _ in AccountType.choices
        }
        filtered_account_types = list(dict.fromkeys([
            account_type
            for account_type in account_types
            if account_type in valid_account_types
        ]))

        if not filtered_account_types:
            return queryset.none()

        return queryset.filter(account_type__in=filtered_account_types)

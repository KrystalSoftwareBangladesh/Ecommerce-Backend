from django.db import models, transaction

from ZayrahLifeBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)


class AccountType(models.TextChoices):
    ASSET = 'ASSET', 'Asset'
    LIABILITY = 'LIABILITY', 'Liability'
    EQUITY = 'EQUITY', 'Equity'
    REVENUE = 'REVENUE', 'Revenue'
    EXPENSE = 'EXPENSE', 'Expense'


ACCOUNT_TYPE_CODE_PREFIXES = {
    AccountType.ASSET: 'AST-1',
    AccountType.LIABILITY: 'LIA-2',
    AccountType.EQUITY: 'EQT-3',
    AccountType.REVENUE: 'REV-4',
    AccountType.EXPENSE: 'EXP-5',
}

TOP_LEVEL_GROUP_START = 10
TOP_LEVEL_GROUP_STEP = 10
CHILD_SEGMENT_START = 1
CHILD_SEGMENT_WIDTH = 2


class ChartOfAccount(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    name = models.CharField(max_length=255)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
    )
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        related_name='children',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'chart_of_accounts'
        ordering = ['code', 'id']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['account_type']),
        ]

    @classmethod
    def get_account_type_code_prefix(cls, account_type):
        return ACCOUNT_TYPE_CODE_PREFIXES[account_type]

    @classmethod
    def split_code(cls, code):
        return code.split('-') if code else []

    @classmethod
    def format_top_level_group(cls, group_number):
        return f'{group_number:02d}'

    @classmethod
    def format_child_segment(cls, sequence_number):
        return f'{sequence_number:0{CHILD_SEGMENT_WIDTH}d}'

    @classmethod
    def get_top_level_group_number(cls, code):
        code_segments = cls.split_code(code)
        if len(code_segments) < 2 or not code_segments[-1].isdigit():
            return None
        return int(code_segments[-1])

    @classmethod
    def get_last_segment_number(cls, code):
        code_segments = cls.split_code(code)
        if len(code_segments) < 2 or not code_segments[-1].isdigit():
            return None
        return int(code_segments[-1])

    @classmethod
    def extend_update_fields(cls, kwargs, *fields):
        update_fields = kwargs.get('update_fields')
        if update_fields is None:
            return kwargs

        updated_kwargs = kwargs.copy()
        updated_fields = list(update_fields)
        for field in fields:
            if field not in updated_fields:
                updated_fields.append(field)
        updated_kwargs['update_fields'] = updated_fields
        return updated_kwargs

    def generate_next_code(self, exclude_pk=None):
        if self.parent_id:
            self.parent = type(self).objects.select_for_update().get(
                pk=self.parent_id,
            )
            self.account_type = self.parent.account_type

            siblings = type(self).objects.select_for_update().filter(
                parent_id=self.parent_id,
            )
            if exclude_pk:
                siblings = siblings.exclude(pk=exclude_pk)

            last_child_sequence = 0
            for sibling_code in siblings.values_list('code', flat=True):
                segment_number = self.get_last_segment_number(sibling_code)
                if segment_number is None:
                    continue
                last_child_sequence = max(
                    last_child_sequence,
                    segment_number,
                )

            next_child_sequence = last_child_sequence + 1
            return (
                f'{self.parent.code}-'
                f'{self.format_child_segment(next_child_sequence)}'
            )

        root_accounts = type(self).objects.select_for_update().filter(
            parent__isnull=True,
            account_type=self.account_type,
        )
        if exclude_pk:
            root_accounts = root_accounts.exclude(pk=exclude_pk)

        last_parent_group = 0
        for root_code in root_accounts.values_list('code', flat=True):
            group_number = self.get_top_level_group_number(root_code)
            if group_number is None:
                continue
            last_parent_group = max(last_parent_group, group_number)

        next_parent_group = (
            last_parent_group + TOP_LEVEL_GROUP_STEP
            if last_parent_group
            else TOP_LEVEL_GROUP_START
        )

        return (
            f'{self.get_account_type_code_prefix(self.account_type)}-'
            f'{self.format_top_level_group(next_parent_group)}'
        )

    def refresh_descendant_codes(self):
        children = type(self).objects.filter(
            parent_id=self.pk,
        ).order_by('id')

        used_segments = set()
        next_child_sequence = CHILD_SEGMENT_START
        for child in children:
            child.account_type = self.account_type
            existing_segment_number = self.get_last_segment_number(child.code)
            child_segment = None

            if existing_segment_number is not None:
                child_segment = self.format_child_segment(
                    existing_segment_number,
                )

            while child_segment is None or child_segment in used_segments:
                child_segment = self.format_child_segment(next_child_sequence)
                next_child_sequence += 1

            used_segments.add(child_segment)
            child.code = f'{self.code}-{child_segment}'

            type(self).objects.filter(pk=child.pk).update(
                account_type=child.account_type,
                code=child.code,
            )

            child.parent = self
            child.refresh_descendant_codes()

    def save(self, *args, **kwargs):
        save_kwargs = kwargs.copy()
        is_new = self._state.adding
        previous_state = None

        if not is_new:
            previous_state = type(self).objects.filter(
                pk=self.pk,
            ).values(
                'parent_id',
                'account_type',
                'code',
            ).first()

        with transaction.atomic():
            if self.parent_id:
                self.parent = type(self).objects.select_for_update().get(
                    pk=self.parent_id,
                )
                self.account_type = self.parent.account_type

            hierarchy_changed = is_new or (
                previous_state
                and (
                    previous_state['parent_id'] != self.parent_id
                    or previous_state['account_type'] != self.account_type
                )
            )
            code_missing = is_new or not previous_state or not previous_state['code']
            code_tampered = (
                bool(previous_state)
                and previous_state['code'] != self.code
            )

            if is_new or hierarchy_changed or code_missing:
                self.code = self.generate_next_code(
                    exclude_pk=None if is_new else self.pk,
                )
                save_kwargs = self.extend_update_fields(
                    save_kwargs,
                    'code',
                    'account_type',
                )
            elif code_tampered:
                self.code = previous_state['code']
                save_kwargs = self.extend_update_fields(
                    save_kwargs,
                    'code',
                )

            super().save(*args, **save_kwargs)

            if hierarchy_changed and not is_new:
                self.refresh_descendant_codes()

    def __str__(self):
        if self.code:
            return f'{self.code} - {self.name}'
        return self.name

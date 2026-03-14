from django.db import migrations


ACCOUNT_TYPE_CODE_PREFIXES = {
    'ASSET': 'AST-1',
    'LIABILITY': 'LIA-2',
    'EQUITY': 'EQT-3',
    'REVENUE': 'REV-4',
    'EXPENSE': 'EXP-5',
}

TOP_LEVEL_GROUP_START = 10
TOP_LEVEL_GROUP_STEP = 10
CHILD_SEGMENT_START = 1
CHILD_SEGMENT_WIDTH = 2
TEMPORARY_ACCOUNT_CODE_PREFIX = 'TMP-COA'


def format_top_level_group(group_number):
    return f'{group_number:02d}'


def format_child_segment(sequence_number):
    return f'{sequence_number:0{CHILD_SEGMENT_WIDTH}d}'


def assign_child_codes(chart_of_account_model, parent):
    children = chart_of_account_model.objects.filter(
        parent_id=parent.pk,
    ).order_by('id')

    next_child_sequence = CHILD_SEGMENT_START
    for child in children:
        child.account_type = parent.account_type
        child.code = (
            f'{parent.code}-'
            f'{format_child_segment(next_child_sequence)}'
        )
        child.save(update_fields=['account_type', 'code'])
        assign_child_codes(chart_of_account_model, child)
        next_child_sequence += 1


def rebuild_chart_of_account_codes(apps, schema_editor):
    chart_of_account_model = apps.get_model('account_api', 'ChartOfAccount')

    for account in chart_of_account_model.objects.order_by('id'):
        account.code = f'{TEMPORARY_ACCOUNT_CODE_PREFIX}-{account.pk}'
        account.save(update_fields=['code'])

    for account_type, prefix in ACCOUNT_TYPE_CODE_PREFIXES.items():
        group_number = TOP_LEVEL_GROUP_START
        root_accounts = chart_of_account_model.objects.filter(
            parent__isnull=True,
            account_type=account_type,
        ).order_by('id')

        for root_account in root_accounts:
            root_account.code = (
                f'{prefix}-{format_top_level_group(group_number)}'
            )
            root_account.save(update_fields=['code'])
            assign_child_codes(chart_of_account_model, root_account)
            group_number += TOP_LEVEL_GROUP_STEP


class Migration(migrations.Migration):

    dependencies = [
        ('account_api', '0004_rebuild_chartofaccount_codes'),
    ]

    operations = [
        migrations.RunPython(
            rebuild_chart_of_account_codes,
            migrations.RunPython.noop,
        ),
    ]

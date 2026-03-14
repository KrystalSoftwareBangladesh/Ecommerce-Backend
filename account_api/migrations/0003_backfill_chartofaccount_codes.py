from django.db import migrations


ACCOUNT_TYPE_CODE_PREFIXES = {
    'ASSET': 'AST',
    'LIABILITY': 'LIA',
    'EQUITY': 'EQT',
    'REVENUE': 'REV',
    'EXPENSE': 'EXP',
}

ACCOUNT_CODE_SEGMENT_LENGTH = 6
TEMPORARY_ACCOUNT_CODE_PREFIX = 'TMP-COA'


def build_code_segment(account_id):
    return f'{account_id:0{ACCOUNT_CODE_SEGMENT_LENGTH}d}'


def build_generated_code(account):
    own_segment = build_code_segment(account.pk)

    if account.parent_id:
        return f'{account.parent.code}-{own_segment}'

    return f'{ACCOUNT_TYPE_CODE_PREFIXES[account.account_type]}-{own_segment}'


def sync_descendants(chart_of_account_model, parent):
    children = chart_of_account_model.objects.filter(
        parent_id=parent.pk,
    ).select_related('parent').order_by('id')

    for child in children:
        if child.account_type != parent.account_type:
            child.account_type = parent.account_type
            child.save(update_fields=['account_type'])

        child.code = build_generated_code(child)
        child.save(update_fields=['code'])
        sync_descendants(chart_of_account_model, child)


def backfill_chart_of_account_codes(apps, schema_editor):
    chart_of_account_model = apps.get_model('account_api', 'ChartOfAccount')

    for account in chart_of_account_model.objects.order_by('id'):
        account.code = (
            f'{TEMPORARY_ACCOUNT_CODE_PREFIX}-{build_code_segment(account.pk)}'
        )
        account.save(update_fields=['code'])

    root_accounts = chart_of_account_model.objects.filter(
        parent__isnull=True,
    ).order_by('id')

    for root_account in root_accounts:
        root_account.code = build_generated_code(root_account)
        root_account.save(update_fields=['code'])
        sync_descendants(chart_of_account_model, root_account)


class Migration(migrations.Migration):

    dependencies = [
        ('account_api', '0002_alter_chartofaccount_code'),
    ]

    operations = [
        migrations.RunPython(
            backfill_chart_of_account_codes,
            migrations.RunPython.noop,
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('category_api', '0005_alter_category_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='show_in_menu',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text=(
                    'Show this category in the storefront navigation menu'
                ),
            ),
        ),
    ]

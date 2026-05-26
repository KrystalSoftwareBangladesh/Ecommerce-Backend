# Generated migration for hierarchical category naming

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('category_api', '0002_add_category_order'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='name',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='category',
            name='slug',
            field=models.SlugField(max_length=255),
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                fields=['name', 'parent'],
                name='unique_name_per_parent'
            ),
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                fields=['slug', 'parent'],
                name='unique_slug_per_parent'
            ),
        ),
    ]

from django.db import migrations, models


def clear_duplicate_defaults(apps, schema_editor):
    ProductImage = apps.get_model('product_api', 'ProductImage')
    Product = apps.get_model('product_api', 'Product')
    for product in Product.objects.all():
        defaults = list(
            ProductImage.objects.filter(
                product=product,
                is_default=True,
                is_active=True,
            ).order_by('display_order', 'created_at', 'id')
        )
        for image in defaults[1:]:
            image.is_default = False
            image.save(update_fields=['is_default'])


class Migration(migrations.Migration):

    dependencies = [
        ('product_api', '0008_productimage'),
    ]

    operations = [
        migrations.RunPython(
            clear_duplicate_defaults,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='productimage',
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ('is_default', True),
                    ('is_active', True),
                ),
                fields=('product',),
                name='product_image_single_default_per_product',
            ),
        ),
    ]

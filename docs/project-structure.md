# Project Structure

Mirrors the actual repository. Last verified 2026-08-23.

```text
ZayrahLife-Backend/
├── AGENTS.md
├── README.md
├── manage.py
├── requirements.txt
├── .env.example                     # copied to EcommerceBackend/env.py
├── .flake8
├── test_nested_import.py            # manage.py shell script, not a test module
│
├── .claude/
│   └── skills/
│       ├── accounting-operation/SKILL.md
│       ├── add-viewset-action/SKILL.md
│       ├── create-api/SKILL.md
│       └── create-model/SKILL.md
│
├── .github/
│   └── workflows/
│       ├── linter.yml
│       ├── deploy_bestcomputerhub_dev.yml
│       ├── deploy_zayrahlife_dev.yml.disable
│       └── deploy_bikkhato_dev.yml.disable
│
├── docs/
│   ├── architecture.md
│   ├── api-conventions.md
│   ├── business-rules.md
│   ├── category-import-api.md
│   ├── conventions.md
│   ├── domain-model.md
│   ├── project-structure.md
│   └── testing.md
│
├── EcommerceBackend/
│   ├── settings.py
│   ├── test_settings.py
│   ├── env.py                       # gitignored
│   ├── urls.py
│   ├── all_urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── core/
│       ├── choices.py
│       ├── exceptions.py
│       ├── filter.py                # empty
│       ├── models.py
│       ├── pagination.py
│       └── permission.py
│
├── account_api/
│   ├── models/chart_of_account.py
│   ├── serializers/chart_of_account.py
│   ├── views/v1/chart_of_account.py
│   ├── urls/{__init__.py,v1.py}
│   ├── filters.py
│   ├── services.py
│   ├── admin.py
│   └── tests.py
│
├── cart_api/
│   ├── models/{cart.py,cart_item.py}
│   ├── serializers/{cart.py,cart_item.py}
│   ├── services/{cart.py,cart_item.py}
│   ├── views/v1/{cart.py,cart_item.py}
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── category_api/
│   ├── models/category.py
│   ├── serializers/{category.py,category_import.py,import.py}
│   ├── views/v1/{category.py,category_import.py,import.py}
│   ├── management/commands/{import_categories.py,clean_category_html_entities.py}
│   ├── urls/{__init__.py,v1.py}
│   ├── filters.py
│   ├── services.py
│   ├── admin.py
│   └── tests.py
│
├── content_security_api/
│   ├── constants.py                 # SCANNER_VERSION and scan limits
│   ├── models/{choices.py,rule.py,scan.py,finding.py}
│   ├── serializers/{rule.py,scan.py,finding.py}
│   ├── services/
│   │   ├── {normalization.py,rules.py,scoring.py,scanner.py}
│   │   ├── {content_sources.py,review.py}
│   │   └── detectors/
│   │       ├── base.py
│   │       ├── {keyword.py,domain.py,html_tag.py,html_attribute.py}
│   │       └── {redirect.py,hidden_content.py,obfuscation.py}
│   ├── views/v1/{scan.py,finding.py,rule.py}
│   ├── urls/{__init__.py,v1.py}
│   ├── management/commands/scan_content.py
│   ├── filters.py
│   ├── admin.py
│   └── tests/                       # package, not a flat tests.py
│       ├── factories.py
│       ├── {test_models.py,test_detectors.py,test_scoring.py}
│       └── {test_scanner.py,test_api.py}
│
├── customer_api/
│   ├── models.py                    # flat module, not a package
│   ├── serializers/customer_profile.py
│   ├── views/v1/customer_profile.py
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── inventory_api/
│   ├── models/inventory.py
│   ├── serializers/inventory.py
│   ├── views/v1/inventory.py
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── meta_api/
│   ├── models.py                    # no models defined
│   ├── serializers/moderation_status.py
│   ├── services/moderation_status.py
│   ├── views/v1/moderation_status.py
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── origin_api/
│   ├── models/origin.py
│   ├── serializers/origin.py
│   ├── views/v1/origin.py
│   ├── urls/{__init__.py,v1.py}
│   └── admin.py                     # no tests.py
│
├── product_api/
│   ├── models/{product.py,product_image.py,brand.py}
│   ├── serializers/{product.py,product_image.py,brand.py}
│   ├── services/{product.py,brand.py}
│   ├── views/v1/{product.py,product_image.py,brand.py}
│   ├── management/commands/{import_products.py,import_product_categories.py}
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── purchase_api/
│   ├── models/purchase.py
│   ├── serializers/purchase.py
│   ├── views/v1/purchase.py
│   ├── urls/{__init__.py,v1.py}
│   ├── services.py
│   ├── admin.py
│   └── tests.py
│
├── review_api/
│   ├── models/review.py
│   ├── serializers/review.py
│   ├── services/review.py
│   ├── views/v1/review.py
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── sale_api/
│   ├── models/{sale.py,payment_method.py}
│   ├── serializers/{sale.py,payment_method.py}
│   ├── views/v1/{sale.py,payment_method.py}
│   ├── urls/{__init__.py,v1.py}
│   ├── services.py
│   ├── admin.py
│   └── tests.py
│
├── supplier_api/
│   ├── models/supplier.py
│   ├── serializers/supplier.py
│   ├── views/v1/supplier.py
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── transaction_api/
│   ├── models/transaction.py
│   ├── serializers/transaction.py
│   ├── views/v1/transaction.py
│   ├── urls/{__init__.py,v1.py}
│   ├── services.py
│   ├── admin.py
│   └── tests.py
│
├── user_api/
│   ├── models/user.py
│   ├── serializers/{user.py,auth.py,group.py,permission.py}
│   ├── views/v1/{user.py,auth.py,group.py,permission.py}
│   ├── urls/{__init__.py,v1.py}
│   ├── backends.py                  # EmailOrUsernameBackend
│   ├── admin.py
│   └── tests.py
│
├── wishlist_api/
│   ├── models/wishlist.py
│   ├── serializers/wishlist.py
│   ├── services/wishlist.py
│   ├── views/v1/wishlist.py
│   ├── urls/{__init__.py,v1.py}
│   ├── admin.py
│   └── tests.py
│
├── scripts/                         # WooCommerce export, run outside Django
│   ├── export_woocommerce_categories.py
│   ├── export_woocommerce_products.py
│   └── export_woocommerce_product_categories.py
│
├── resources/                       # seed data consumed by management commands
│   ├── categories.json
│   ├── products.json
│   └── product_categories.json
│
├── media/                           # gitignored upload root
└── env/                             # gitignored virtualenv
```

Every app also has `apps.py`, `migrations/` and package `__init__.py` files,
omitted above for brevity.

## Notes

- `content_security_api` is the only app whose tests are a package
  rather than a flat `tests.py`. `.flake8` excludes `tests.py` by name,
  so this app's test modules **are** linted.
- `content_security_api/models/choices.py` holds choices shared by
  several model modules in that app; elsewhere choices sit in the model
  module itself.
- `category_api/serializers/import.py` and `category_api/views/v1/import.py`
  are near-duplicates of the `category_import.py` modules. They are not
  imported by any `__init__.py` and not routed.

## Rule

Whenever a file or folder is created, deleted, renamed or moved, update this
document in the same change.

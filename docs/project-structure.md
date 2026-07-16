# Project Structure

```text
krystalsoftwarebangladesh-ecommerce-backend/

├── account_api/
├── category_api/
├── customer_api/
├── inventory_api/
├── origin_api/
│   ├── models/
│   │   └── origin.py
│   ├── serializers/
│   ├── views/
│   │   └── v1/
│   ├── urls/
│   └── admin.py
├── product_api/
│   ├── models/
│   │   ├── product.py
│   │   ├── product_image.py
│   │   └── brand.py
│   ├── serializers/
│   ├── views/
│   │   └── v1/
│   ├── services.py
│   └── tests.py
├── purchase_api/
├── sale_api/
├── supplier_api/
├── transaction_api/
├── user_api/
├── EcommerceBackend/
├── .github/
├── manage.py
├── requirements.txt
└── README.md
```

## Rules

Whenever a file or folder is:

- created
- deleted
- renamed
- moved

this document must be updated.

This document should always match the actual repository structure.

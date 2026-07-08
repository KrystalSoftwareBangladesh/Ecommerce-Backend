# Ecommerce Backend
Complete backend for Ecommerce Platform's web application with management system.

---

## Prerequisite
- Python 3
- PostgreSQL 16

---

## 📦 Installation

### Clone the repository
```bash
git clone git@github.com:KrystalSoftwareBangladesh/Ecommerce-Backend.git
cd Ecommerce-Backend
```

### Install dependency
If the existing virtual environment is already present, activate it:
```bash
source env/bin/activate
pip install -r requirements.txt
```

If the environment does not exist yet, create it once:
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### Environment Setup
```bash
cp .env.example EcommerceBackend/env.py
```
And then update values based on your environment.

### Migration
```bash
python manage.py migrate
```

### Create Super User
```bash
python manage.py createsuperuser
```

### Seeding Data
Export categories
```bash
python scripts/export_woocommerce_categories.py
```
Import categories
```bash
python manage.py import_categories resources/categories.json
```
Export products
```bash
python scripts/export_woocommerce_products.py
```
Import products
```bash
python manage.py import_products resources/products.json
```
Map products and categories
```bash
python manage.py import_product_categories resources/product_categories.json
```
Clean category name, description
```bash
python manage.py clean_category_html_entities
```

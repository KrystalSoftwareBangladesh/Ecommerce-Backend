# Ecommerce Backend
Complete backend for Ecommerce Platform's web application with management system.

## Prepared to Serve
- [Zayrah Life](https://ZayrahLife.rkshaon.info/)
- [Best Computer Hub](https://bestcomputerhub.com/)
- [bikkhato](https://bikkhato.rkshaon.info/)

## Swagger Documentations
- [Zayrah Life](https://apizayrahlife.rkshaon.info/docs/)
- [Best Computer Hub](https://apibestcomputerhub.rkshaon.info/docs/)
- [bikkhato](https://apibikkhato.rkshaon.info/docs/)

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
Clean category name, description
```bash
python manage.py clean_category_html_entities
```
Import products
```bash
python manage.py import_products resources/products.json
```
Export products and categories mapping
```bash
python scripts/export_woocommerce_product_categories.py
```
Map products and categories
```bash
python manage.py import_product_categories resources/product_categories.json
```
Export product images
```bash
python scripts/export_woocommerce_product_images.py
```
Import product images and map
```bash
python manage.py import_product_images \
    resources/product_images.json \
    --workers 25
```
You can adjust number of worker.

Import blog tags
```bash
python scripts/export_woocommerce_blog_tags.py
```
Export blog tags
```bash
python manage.py import_blog_tags resources/blog_tags.json
```
Import blog posts
```bash
python scripts/export_woocommerce_blog_posts.py
```
Export blog posts
```bash
python scripts/export_woocommerce_blog_posts.py
```
Import blog posts
```bash
python manage.py import_blog_posts resources/blog_posts.json
```
Export tags and posts mapping
```bash
python scripts/export_woocommerce_blog_post_tags.py
```
Map tags and posts
```bash
python manage.py import_blog_post_tags resources/blog_post_tags.json
```
Export blog post categories
```bash
python scripts/export_woocommerce_blog_categories.py
```
Import & reconcile blog post categories with product categories
```bash
python manage.py import_blog_categories resources/blog_categories.json
```
Export categories and blog posts mapping
```bash
python scripts/export_woocommerce_blog_post_categories.py
```
Map blog posts and categories
```bash
python manage.py import_blog_post_categories resources/blog_post_categories.json
```
Export blog post images
```bash
python scripts/export_woocommerce_blog_post_images.py
```
Import blog post images and map
```bash
python manage.py import_blog_post_images \
    resources/blog_post_images.json \
    --workers 5
```
Export users
```bash
python scripts/export_woocommerce_users.py
```
Import users & customers
```bash
python manage.py import_users resources/users.json
```
Export map of blog posts and authors
```bash
python scripts/export_woocommerce_blog_post_authors.py
```
Map blog posts and authors
```bash
python manage.py import_blog_post_authors resources/blog_post_authors.json
```
Export brands
```bash
python scripts/export_woocommerce_brands.py
```
Import brands
```bash
python manage.py import_brands resources/brands.json
```
Export map of products and brands
```bash
python scripts/export_woocommerce_product_brands.py
```
Map brands and products
```bash
python manage.py import_product_brands resources/product_brands.json
```
Export brand images
```bash
python scripts/export_woocommerce_brand_images.py
```
Import and map brand images
```bash
python manage.py import_brand_images resources/brand_images.json
```
Export brand metadata
```bash
python scripts/export_woocommerce_brand_metadata.py
```
Import and map brand metadata
```bash
python manage.py import_brand_metadata resources/brand_metadata.json
```

# API Conventions

## Pagination

Use StandardPagination.

## Response Format

{
  "success": true,
  "message": "",
  "data": {}
}

## API Versioning

All APIs must be placed in:

views/v1/
urls/v1.py

## Filtering

Use django-filter.

## Permissions

Apply permission classes to all protected endpoints.
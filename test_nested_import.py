#!/usr/bin/env python
"""
Quick test script to verify nested category import functionality.
Usage: python manage.py shell < test_nested_import.py
"""

import json
from category_api.services import CategoryImportService
from category_api.models import Category

# Clean up existing categories
Category.objects.all().delete()

# Test nested JSON structure
nested_json = [
    {
        "name": "Gaming Component",
        "description": "Gaming components category",
        "children": [
            {
                "name": "Laptop",
                "description": "Gaming laptops",
                "children": [
                    {
                        "name": "MSI",
                        "description": "MSI gaming laptops",
                        "children": []
                    },
                    {
                        "name": "ASUS",
                        "description": "ASUS gaming laptops",
                        "children": []
                    }
                ]
            },
            {
                "name": "Desktop PC Component",
                "description": "Desktop components",
                "children": [
                    {
                        "name": "Motherboard",
                        "description": "PC motherboards",
                        "children": [
                            {
                                "name": "MSI-AMD",
                                "description": "MSI AMD motherboards",
                                "children": []
                            }
                        ]
                    }
                ]
            }
        ]
    }
]

# Convert to JSON bytes
json_content = json.dumps(nested_json).encode('utf-8')

# Test import
print("Testing nested category import...")
result = CategoryImportService.import_from_json(json_content, user=None)

print("\nResult:")
print(f"  Success: {result['success']}")
print(f"  Created: {result['created']}")
print(f"  Errors: {result.get('errors', [])}")
print("\nCreated Categories:")
for cat in result.get('created_categories', []):
    print(f"  - {cat}")

# Verify in database
print("\nDatabase Verification:")
print(f"Total categories: {Category.objects.count()}")
for cat in Category.objects.all().order_by('id'):
    parent_name = cat.parent.name if cat.parent else "None"
    print(f"  - {cat.name} (parent: {parent_name})")

print("\n✓ Test complete!")

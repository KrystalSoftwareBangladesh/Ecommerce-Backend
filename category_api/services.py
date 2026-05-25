import json
import io
from typing import List, Dict, Any

import pandas as pd
from django.db import transaction
from django.core.exceptions import ValidationError

from category_api.models import Category


class CategoryImportService:
    """Service for importing categories from various file formats."""

    REQUIRED_FIELDS = {'name'}
    OPTIONAL_FIELDS = {'description', 'parent_id', 'slug'}
    ALL_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

    @staticmethod
    def import_from_json(file_content: bytes, user=None) -> Dict[str, Any]:
        """
        Import categories from JSON file.

        Supports both flat and nested (hierarchical) formats:

        Flat format:
        [
            {"name": "Electronics", "description": "...", "parent_id": null},
            {"name": "Phones", "description": "...", "parent_id": 1}
        ]

        Nested format (with children):
        [
            {
                "name": "Electronics",
                "description": "...",
                "children": [
                    {
                        "name": "Phones",
                        "description": "...",
                        "children": []
                    }
                ]
            }
        ]
        """
        try:
            data = json.loads(file_content.decode('utf-8'))
            if not isinstance(data, list):
                raise ValidationError("JSON must contain an array of objects")

            # Check if data has nested structure (children key)
            if CategoryImportService._has_nested_structure(data):
                return CategoryImportService._process_nested_categories(
                    data, user
                )
            else:
                return CategoryImportService._process_categories(data, user)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format: {str(e)}")

    @staticmethod
    def import_from_csv(file_content: bytes, user=None) -> Dict[str, Any]:
        """
        Import categories from CSV file.

        Expected format:
        name,description,parent_id
        Electronics,Electronics devices,
        Phones,Mobile phones,1
        """
        try:
            csv_string = file_content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_string))
            data = df.fillna(None).to_dict('records')
            return CategoryImportService._process_categories(data, user)
        except Exception as e:
            raise ValidationError(f"Invalid CSV format: {str(e)}")

    @staticmethod
    def import_from_xlsx(file_content: bytes, user=None) -> Dict[str, Any]:
        """
        Import categories from XLSX file.

        Expected format (same as CSV):
        name | description | parent_id
        Electronics | Electronics devices |
        Phones | Mobile phones | 1
        """
        try:
            bytes_io = io.BytesIO(file_content)
            df = pd.read_excel(bytes_io, engine='openpyxl')
            data = df.fillna(None).to_dict('records')
            return CategoryImportService._process_categories(data, user)
        except Exception as e:
            raise ValidationError(f"Invalid XLSX format: {str(e)}")

    @staticmethod
    def _process_categories(
        data: List[Dict[str, Any]],
        user=None
    ) -> Dict[str, Any]:
        """
        Process and validate categories before insertion.

        Returns:
            Dict with 'success', 'created', 'errors' keys
        """
        if not isinstance(data, list):
            raise ValidationError("Data must be a list of category objects")

        if not data:
            raise ValidationError("No categories provided")

        created_count = 0
        errors = []
        # Track created categories by name for parent linking
        category_map = {}

        with transaction.atomic():
            for idx, row in enumerate(data, 1):
                try:
                    # Validate required fields
                    if not isinstance(row, dict):
                        errors.append(
                            f"Row {idx}: Record must be an object/dictionary"
                        )
                        continue

                    name = (
                        row.get('name', '').strip()
                        if row.get('name')
                        else None
                    )
                    if not name:
                        errors.append(f"Row {idx}: 'name' field is required")
                        continue

                    # Build category data
                    category_data = {
                        'name': name,
                        'description': (
                            row.get('description', '').strip()
                            if row.get('description')
                            else ''
                        ),
                        'is_active': row.get('is_active', True),
                    }

                    # Handle parent category
                    parent_id = row.get('parent_id')
                    parent_name = row.get('parent_name')

                    if parent_id:
                        try:
                            parent = Category.objects.get(id=int(parent_id))
                            category_data['parent'] = parent
                        except Category.DoesNotExist:
                            errors.append(
                                f"Row {idx}: Parent category with id "
                                f"{parent_id} not found"
                            )
                            continue
                        except (ValueError, TypeError):
                            errors.append(
                                f"Row {idx}: Invalid parent_id value "
                                f"'{parent_id}'"
                            )
                            continue

                    elif parent_name:
                        if parent_name in category_map:
                            category_data['parent'] = category_map[parent_name]
                        else:
                            try:
                                parent = Category.objects.get(name=parent_name)
                                category_data['parent'] = parent
                            except Category.DoesNotExist:
                                errors.append(
                                    f"Row {idx}: Parent category "
                                    f"'{parent_name}' not found"
                                )
                                continue

                    # Set audit fields
                    if user:
                        category_data['created_by'] = user
                        category_data['updated_by'] = user

                    # Create category
                    category = Category.objects.create(**category_data)
                    category_map[name] = category
                    created_count += 1

                except Exception as e:
                    errors.append(f"Row {idx}: {str(e)}")

        return {
            'success': len(errors) == 0,
            'created': created_count,
            'errors': errors,
        }

    @staticmethod
    def _has_nested_structure(data: List[Dict[str, Any]]) -> bool:
        """
        Check if data has 'children' key indicating nested structure.

        Args:
            data: List of category dictionaries

        Returns:
            True if any item has 'children' key, False otherwise
        """
        for item in data:
            if isinstance(item, dict) and 'children' in item:
                return True
        return False

    @staticmethod
    def _process_nested_categories(
        data: List[Dict[str, Any]],
        user=None
    ) -> Dict[str, Any]:
        """
        Process categories with nested hierarchical structure (children).

        Args:
            data: List of root category objects
            user: User performing the import

        Returns:
            Dict with 'success', 'created', 'errors', 'created_categories' keys
        """
        if not isinstance(data, list):
            raise ValidationError("Data must be a list of category objects")

        if not data:
            raise ValidationError("No categories provided")

        created_count = 0
        errors = []
        created_categories = []

        with transaction.atomic():
            for idx, root_item in enumerate(data, 1):
                try:
                    if not isinstance(root_item, dict):
                        errors.append(
                            f"Item {idx}: Record must be an object/dictionary"
                        )
                        continue

                    # Process root category and its nested children
                    count, paths = (
                        CategoryImportService._process_category_recursive(
                            root_item,
                            parent_category=None,
                            user=user,
                            path="",
                            errors=errors
                        )
                    )
                    created_count += count
                    created_categories.extend(paths)

                except Exception as e:
                    errors.append(f"Item {idx}: {str(e)}")

        return {
            'success': len(errors) == 0,
            'created': created_count,
            'errors': errors,
            'created_categories': created_categories,
        }

    @staticmethod
    def _process_category_recursive(
        category_data: Dict[str, Any],
        parent_category: Any = None,
        user=None,
        path: str = "",
        errors: List[str] = None
    ) -> tuple:
        """
        Recursively process category and its children.

        Args:
            category_data: Category object with optional 'children' array
            parent_category: Parent Category instance (None for root)
            user: User performing the import
            path: Current hierarchy path for error messages
            errors: List to collect errors

        Returns:
            Tuple of (count, created_paths) where:
                - count: Number of categories created in this subtree
                - created_paths: List of full paths to created categories
        """
        if errors is None:
            errors = []

        created_count = 0
        created_paths = []

        try:
            if not isinstance(category_data, dict):
                error_msg = (
                    f"Invalid category at {path}: "
                    "Record must be an object/dictionary"
                )
                errors.append(error_msg)
                return 0, []

            # Extract and validate name
            name = (
                category_data.get('name', '').strip()
                if category_data.get('name')
                else None
            )
            if not name:
                error_msg = (
                    f"Invalid category at {path}: 'name' field is required"
                )
                errors.append(error_msg)
                return 0, []

            # Build the hierarchy path
            current_path = f"{path} > {name}" if path else name

            # Build category object
            cat_obj = {
                'name': name,
                'description': (
                    category_data.get('description', '').strip()
                    if category_data.get('description')
                    else ''
                ),
                'is_active': category_data.get('is_active', True),
            }

            # Set parent if exists
            if parent_category:
                cat_obj['parent'] = parent_category

            # Set audit fields
            if user:
                cat_obj['created_by'] = user
                cat_obj['updated_by'] = user

            # Create the category
            category = Category.objects.create(**cat_obj)
            created_count += 1
            created_paths.append(current_path)

            # Process children if they exist
            children = category_data.get('children', [])
            if children and isinstance(children, list):
                for child_data in children:
                    child_count, child_paths = (
                        CategoryImportService._process_category_recursive(
                            child_data,
                            parent_category=category,
                            user=user,
                            path=current_path,
                            errors=errors
                        )
                    )
                    created_count += child_count
                    created_paths.extend(child_paths)

        except Exception as e:
            error_msg = f"Error at {path}: {str(e)}"
            errors.append(error_msg)

        return created_count, created_paths

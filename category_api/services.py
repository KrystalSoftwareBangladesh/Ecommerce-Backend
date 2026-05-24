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

        Expected format:
        [
            {"name": "Electronics", "description": "...", "parent_id": null},
            {"name": "Phones", "description": "...", "parent_id": 1}
        ]
        """
        try:
            data = json.loads(file_content.decode('utf-8'))
            if not isinstance(data, list):
                raise ValidationError("JSON must contain an array of objects")
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

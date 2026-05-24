from rest_framework import serializers


class CategoryJsonImportSerializer(serializers.Serializer):
    """
    Serializer for importing categories from JSON file.

    Expected file format:
    [
        {"name": "Electronics", "description": "...", "parent_id": null},
        {"name": "Phones", "description": "...", "parent_id": 1}
    ]
    """
    file = serializers.FileField(
        help_text="JSON file containing categories array"
    )

    def validate_file(self, file):
        """Validate that file is a JSON file."""
        if not file.name.lower().endswith('.json'):
            raise serializers.ValidationError(
                "File must be in JSON format (.json)"
            )
        return file


class CategoryCsvImportSerializer(serializers.Serializer):
    """
    Serializer for importing categories from CSV file.

    Expected file format (with header):
    name,description,parent_id
    Electronics,Electronics devices,
    Phones,Mobile phones,1
    """
    file = serializers.FileField(
        help_text="CSV file containing categories"
    )

    def validate_file(self, file):
        """Validate that file is a CSV file."""
        if not file.name.lower().endswith('.csv'):
            raise serializers.ValidationError(
                "File must be in CSV format (.csv)"
            )
        return file


class CategoryXlsxImportSerializer(serializers.Serializer):
    """
    Serializer for importing categories from XLSX (Excel) file.

    Expected file format (with header row):
    name | description | parent_id
    Electronics | Electronics devices |
    Phones | Mobile phones | 1
    """
    file = serializers.FileField(
        help_text="XLSX file containing categories"
    )

    def validate_file(self, file):
        """Validate that file is an XLSX file."""
        valid_extensions = ('.xlsx', '.xls')
        if not file.name.lower().endswith(valid_extensions):
            raise serializers.ValidationError(
                "File must be in Excel format (.xlsx or .xls)"
            )
        return file


class CategoryImportResultSerializer(serializers.Serializer):
    """
    Serializer for the response after importing categories.
    """
    success = serializers.BooleanField(
        help_text="Whether import was successful (no errors)"
    )
    created = serializers.IntegerField(
        help_text="Number of categories created"
    )
    errors = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of error messages if any"
    )

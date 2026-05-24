from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.parsers import MultiPartParser, FormParser

from EcommerceBackend.core.permission import PublicListPermissionMixin

from category_api.serializers import (
    CategoryJsonImportSerializer,
    CategoryCsvImportSerializer,
    CategoryXlsxImportSerializer,
    CategoryImportResultSerializer,
)
from category_api.services import CategoryImportService


@extend_schema(tags=["Categories - Import"])
class CategoryImportViewSet(PublicListPermissionMixin, ViewSet):
    """
    ViewSet for importing categories from various file formats.
    """
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'import_json':
            return CategoryJsonImportSerializer
        elif self.action == 'import_csv':
            return CategoryCsvImportSerializer
        elif self.action == 'import_xlsx':
            return CategoryXlsxImportSerializer
        return None

    @extend_schema(
        request=CategoryJsonImportSerializer,
        responses={200: CategoryImportResultSerializer},
        description="Import categories from a JSON file",
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='import-json'
    )
    def import_json(self, request):
        """
        Import categories from JSON file.

        Expected JSON format:
        [
            {"name": "Electronics", "description": "...", "parent_id": null},
            {"name": "Phones", "description": "...", "parent_id": 1}
        ]
        """
        serializer = CategoryJsonImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data['file']
        file_content = file.read()

        try:
            result = CategoryImportService.import_from_json(
                file_content,
                user=request.user if request.user.is_authenticated else None
            )
            response_serializer = CategoryImportResultSerializer(result)
            return Response(
                response_serializer.data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(
        request=CategoryCsvImportSerializer,
        responses={200: CategoryImportResultSerializer},
        description="Import categories from a CSV file",
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='import-csv'
    )
    def import_csv(self, request):
        """
        Import categories from CSV file.

        Expected CSV format (with header):
        name,description,parent_id
        Electronics,Electronics devices,
        Phones,Mobile phones,1
        """
        serializer = CategoryCsvImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data['file']
        file_content = file.read()

        try:
            result = CategoryImportService.import_from_csv(
                file_content,
                user=request.user if request.user.is_authenticated else None
            )
            response_serializer = CategoryImportResultSerializer(result)
            return Response(
                response_serializer.data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(
        request=CategoryXlsxImportSerializer,
        responses={200: CategoryImportResultSerializer},
        description="Import categories from an XLSX (Excel) file",
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='import-xlsx'
    )
    def import_xlsx(self, request):
        """
        Import categories from XLSX file.

        Expected XLSX format (with header row):
        | name        | description          | parent_id |
        | Electronics | Electronics devices  |           |
        | Phones      | Mobile phones        | 1         |
        """
        serializer = CategoryXlsxImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data['file']
        file_content = file.read()

        try:
            result = CategoryImportService.import_from_xlsx(
                file_content,
                user=request.user if request.user.is_authenticated else None
            )
            response_serializer = CategoryImportResultSerializer(result)
            return Response(
                response_serializer.data,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

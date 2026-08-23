# Category Import API Documentation

## Overview

The Category Import API provides three endpoints for bulk importing categories from different file formats:

1. **JSON Import** - `POST /api/v1/categories/import-json/`
2. **CSV Import** - `POST /api/v1/categories/import-csv/`
3. **XLSX Import** - `POST /api/v1/categories/import-xlsx/`

## Supported File Formats

### JSON Format

**File Extension:** `.json`

**Expected Structure:**
```json
[
    {
        "name": "Electronics",
        "description": "Electronic devices and gadgets",
        "parent_id": null
    },
    {
        "name": "Phones",
        "description": "Mobile phones and smartphones",
        "parent_id": 1
    },
    {
        "name": "Laptops",
        "description": "Laptop computers",
        "parent_id": 1
    }
]
```

**Field Definitions:**
- `name` (required): Category name (must be unique)
- `description` (optional): Category description
- `parent_id` (optional): ID of parent category (for subcategories)
- `parent_name` (optional): Name of parent category (alternative to parent_id)
- `is_active` (optional): Boolean, defaults to true

### CSV Format

**File Extension:** `.csv`

**Expected Structure:**
```csv
name,description,parent_id
Electronics,Electronic devices and gadgets,
Phones,Mobile phones and smartphones,1
Laptops,Laptop computers,1
```

**Header Row Required:** Yes

**Field Definitions:**
- `name` (required): Category name
- `description` (optional): Category description
- `parent_id` (optional): ID of parent category
- `parent_name` (optional): Name of parent category
- `is_active` (optional): Boolean value

### XLSX Format

**File Extension:** `.xlsx` or `.xls`

**Expected Structure:**

| name | description | parent_id | parent_name | is_active |
|------|-------------|-----------|-------------|-----------|
| Electronics | Electronic devices and gadgets | | | |
| Phones | Mobile phones and smartphones | 1 | | true |
| Laptops | Laptop computers | 1 | | true |

**Header Row Required:** Yes (first row)

**Field Definitions:**
Same as CSV format

## API Endpoints

### 1. JSON Import

**Endpoint:** `POST /api/v1/categories/import-json/`

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/categories/import-json/ \
  -F "file=@categories.json"
```

**Response (Success):**
```json
{
    "success": true,
    "created": 3,
    "errors": []
}
```

**Response (With Errors):**
```json
{
    "success": false,
    "created": 2,
    "errors": [
        "Row 3: 'name' field is required",
        "Row 4: Parent category with id 999 not found"
    ]
}
```

### 2. CSV Import

**Endpoint:** `POST /api/v1/categories/import-csv/`

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/categories/import-csv/ \
  -F "file=@categories.csv"
```

**Response:** Same format as JSON import

### 3. XLSX Import

**Endpoint:** `POST /api/v1/categories/import-xlsx/`

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/categories/import-xlsx/ \
  -F "file=@categories.xlsx"
```

**Response:** Same format as JSON import

## Response Format

All import endpoints return a JSON response with the following structure:

```json
{
    "success": boolean,        // True if no errors, false otherwise
    "created": integer,        // Number of categories successfully created
    "errors": array           // Array of error messages
}
```

## Validation Rules

### Required Fields
- `name` - Must be provided for each category

### Validation Checks
- **Duplicate Names:** Category names must be unique
- **Parent Validation:** Parent category ID or name must exist in the database
- **Type Validation:** Fields must be of correct types (string for name, integer for parent_id)
- **Required Headers:** CSV and XLSX files must have a header row

### Error Handling
- Invalid file formats return HTTP 400 with error message
- Invalid data returns HTTP 200 with success=false and error details
- Row-level errors are captured and reported without stopping the import

## Features

### Atomic Transactions
- All rows are processed within a single database transaction
- If a critical error occurs, the entire import is rolled back
- Row-level errors don't prevent other rows from being imported

### Parent Category Resolution
- Can use either `parent_id` (numeric) or `parent_name` (string)
- Parent categories must exist in the database
- Supports hierarchical category structures

### User Tracking
- Automatically assigns `created_by` and `updated_by` to authenticated users
- Tracking only occurs for authenticated requests

### Slug Auto-Generation
- Slugs are automatically generated from category names
- Ensures uniqueness within parent category scope

## Requirements

### Dependencies
- `openpyxl` - For XLSX file parsing
- `pandas` - For CSV parsing and data processing
- `Django REST Framework` - For API endpoints

### Installation
```bash
pip install openpyxl pandas
```

## Usage Examples

### Example 1: Import JSON with Subcategories

**categories.json:**
```json
[
    {
        "name": "Electronics",
        "description": "All electronic items",
        "parent_id": null
    },
    {
        "name": "Mobile Devices",
        "description": "Mobile phones and tablets",
        "parent_id": 1
    },
    {
        "name": "Computers",
        "description": "Laptops and desktops",
        "parent_id": 1
    }
]
```

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/categories/import-json/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@categories.json"
```

### Example 2: Import CSV

**categories.csv:**
```csv
name,description,parent_id
Clothing,Fashion and apparel,
Men's,Men's clothing,1
Women's,Women's clothing,1
Children's,Children's clothing,1
```

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/categories/import-csv/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@categories.csv"
```

### Example 3: Import XLSX

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/categories/import-xlsx/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@categories.xlsx"
```

## Error Scenarios

### Scenario 1: Invalid File Format
```json
{
    "error": "File must be in JSON format (.json)"
}
```

### Scenario 2: Malformed Data
```json
{
    "error": "Invalid CSV format: No columns to parse from file"
}
```

### Scenario 3: Missing Required Fields
```json
{
    "success": false,
    "created": 0,
    "errors": [
        "Row 1: 'name' field is required"
    ]
}
```

### Scenario 4: Invalid Parent Reference
```json
{
    "success": false,
    "created": 2,
    "errors": [
        "Row 3: Parent category with id 999 not found"
    ]
}
```

## Authentication & Permissions

- Import endpoints are accessible to authenticated users
- User information is automatically captured in `created_by` field
- Public access is restricted (requires valid JWT token)

## Best Practices

1. **Validate Data Before Import:** Test with a small batch first
2. **Use Descriptive Names:** Category names should be clear and specific
3. **Organize Hierarchy:** Set up parent categories before subcategories
4. **Check for Duplicates:** Ensure category names don't already exist
5. **Handle Errors:** Review error messages and fix data accordingly
6. **Batch Operations:** Import large datasets in reasonable-sized batches (e.g., 100-1000 rows)

## Implementation Details

### Files Modified/Created

**New Files:**
- `category_api/services.py` - Import service with format handlers
- `category_api/serializers/category_import.py` - Import serializers
- `category_api/views/v1/category_import.py` - Import views/endpoints

**Modified Files:**
- `category_api/urls/v1.py` - Registered import endpoints
- `category_api/serializers/__init__.py` - Exported import serializers
- `category_api/views/v1/__init__.py` - Exported import viewset
- `requirements.txt` - Added openpyxl and pandas

## Performance Considerations

- Large imports (>10,000 rows) should be done asynchronously in production
- Use batch processing for very large datasets
- Consider implementing pagination or chunked imports for massive data
- Database indexing on frequently filtered fields improves performance

## Future Enhancements

- Async import processing for large files
- Import progress tracking
- Bulk update/upsert functionality
- Custom field mapping
- Data validation before import
- Export functionality

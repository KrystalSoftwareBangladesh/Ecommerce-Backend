# Business Rules

## Products

### Product Images

Product images are managed independently from product records and support a reusable gallery workflow.

- A product may have many images.
- Images are uploaded after product creation.
- The first active image becomes the default image.
- Exactly one active image is expected to be marked as default.
- This rule is enforced at the database level via a partial unique constraint and at the service layer for all create, update, and set-default operations.
- Image ordering is managed server-side and remains sequential.
- Soft deletion is used for image removal.
- Replacement updates the stored file while preserving metadata and image identity.

### Brand

Brand represents a product manufacturer or brand name.

- Brand name must be unique
- Slug is auto-generated and cannot be updated (SEO safety)
- Brand can be soft-deleted (is_active flag)
- Search available by name and description
- Publicly readable, authenticated create/update/delete

---

## Authentication

Public registration endpoint (`POST /auth/register/`) allows website customers to sign up.

Registration creates:
- User account with email and hashed password
- CustomerProfile with default type "WEBSITE"

Email must be unique.

---

## Inventory

Inventory changes must be traceable.

Inventory should only change through:

- Purchase
- Sale
- Return
- Adjustment

Never silently modify stock.

---

## Purchases

Purchases may:

- Increase inventory
- Create accounting transactions

Inventory and accounting must remain synchronized.

---

## Sales

Sales may:

- Reduce inventory
- Create accounting transactions

Stock must be validated before sale completion.

---

## Accounting

Financial records are historical records.

Avoid modifying posted transactions.

Prefer adjustment entries.

---

## Customers

Customer balances must reflect:

- Sales
- Payments
- Adjustments

---

## Permissions

Protected endpoints require authentication.

Existing permission patterns should be reused.

### Custom model permissions

Some actions require a dedicated permission on top of authentication.

User (`user_api.User`):

- `change_user_email`
- `change_user_username`
- `change_user_password`
- `assign_user_role`
- `remove_user_role`

Category (`category_api.Category`):

- `mark_category_as_menu` - required by `POST /api/v1/categories/{id}/mark-as-menu/`
- `remove_category_from_menu` - required by `POST /api/v1/categories/{id}/remove-from-menu/`

Menu visibility of a single category can only be changed by a user holding
the matching permission. Holding one of the two permissions does not grant
the other. Superusers hold every permission implicitly.

The remaining category endpoints, including `bulk-menu-update`, keep
requiring authentication only.

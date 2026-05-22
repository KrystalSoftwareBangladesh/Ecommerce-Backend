# Business Rules

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

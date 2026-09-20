"""Synthetic database, prompts, and answer keys for the SQL activity."""

from __future__ import annotations

COMPANY_NAME = "Gem City Office Supply"

CUSTOMERS = (
    ("C100", "Blue Ridge Design", "Dayton"),
    ("C200", "Patterson Legal", "Kettering"),
    ("C300", "Riverbend Health", "Oakwood"),
)

PRODUCTS = (
    ("P100", "Ergonomic Chair", 325.00),
    ("P200", "Desk Lamp", 85.00),
    ("P300", "Standing Desk", 700.00),
    ("P400", "Filing Cabinet", 240.00),
)

ORDERS = (
    ("O5001", "2026-09-03", "C100", "Fulfilled"),
    ("O5002", "2026-09-04", "C200", "Fulfilled"),
    ("O5003", "2026-09-06", "C100", "Fulfilled"),
    ("O5004", "2026-09-08", "C300", "Fulfilled"),
)

ORDER_LINES = (
    ("OL01", "O5001", "P100", 2, 310.00),
    ("OL02", "O5001", "P200", 4, 80.00),
    ("OL03", "O5002", "P300", 1, 700.00),
    ("OL04", "O5003", "P100", 1, 275.00),
    ("OL05", "O5003", "P400", 2, 240.00),
    ("OL06", "O5004", "P200", 10, 70.00),
)

PAYMENTS = (
    ("PAY01", "O5001", "2026-09-10", 940.00),
    ("PAY02", "O5002", "2026-09-12", 700.00),
)

SCHEMA = {
    "Customers": ("CustomerID", "CustomerName", "CustomerCity"),
    "Orders": ("OrderID", "OrderDate", "CustomerID", "OrderStatus"),
    "Products": ("ProductID", "ProductName", "StandardPrice"),
    "OrderLines": ("OrderLineID", "OrderID", "ProductID", "Quantity", "ActualUnitPrice"),
    "Payments": ("PaymentID", "OrderID", "PaymentDate", "Amount"),
}

PRIMARY_KEYS = {
    ("Customers", "CustomerID"),
    ("Orders", "OrderID"),
    ("Products", "ProductID"),
    ("OrderLines", "OrderLineID"),
    ("Payments", "PaymentID"),
}

READ_QUESTIONS = (
    (
        "source",
        "Which clauses assemble the rows before filtering?",
        ("SELECT", "FROM and JOIN", "WHERE", "ORDER BY"),
        "FROM and JOIN",
        "FROM identifies the starting table, and JOIN adds matching rows from related tables.",
    ),
    (
        "filter",
        "Which clause removes rows that do not satisfy the reporting condition?",
        ("SELECT", "ON", "WHERE", "GROUP BY"),
        "WHERE",
        "WHERE evaluates the condition after the row sources and joins have been established.",
    ),
    (
        "output",
        "Which part determines the columns displayed in the result?",
        ("SELECT expressions", "FROM", "ON", "WHERE"),
        "SELECT expressions",
        "SELECT appears first in the written query, but it describes the final output columns.",
    ),
)

READ_QUERY = """SELECT c.CustomerName,
       o.OrderID,
       ol.Quantity * ol.ActualUnitPrice AS LineAmount
FROM Customers AS c
JOIN Orders AS o
  ON o.CustomerID = c.CustomerID
JOIN OrderLines AS ol
  ON ol.OrderID = o.OrderID
WHERE o.OrderStatus = 'Fulfilled'
ORDER BY c.CustomerName, o.OrderID;"""

MISSING_QUERY = """SELECT o.OrderID, c.CustomerName
FROM Orders AS o
JOIN Customers AS c
  ON c.CustomerID = o.CustomerID
INNER JOIN Payments AS p
  ON p.OrderID = o.OrderID
WHERE p.PaymentID IS NULL;"""

MISSING_CAUSE_OPTIONS = (
    "A LEFT JOIN preserves every order; orders without a payment match receive NULL payment fields that WHERE can test",
    "Deleting WHERE is appropriate because the INNER JOIN already isolates orders without payments",
    "A CROSS JOIN creates unmatched payment rows with NULL identifiers for each unpaid order",
    "Testing IS NOT NULL retains the orders that have no matching payment record",
)
MISSING_CAUSE_CORRECT = MISSING_CAUSE_OPTIONS[0]

MISSING_REPAIR_OPTIONS = (
    "Replace INNER JOIN Payments with LEFT JOIN Payments and keep WHERE p.PaymentID IS NULL",
    "Delete the WHERE clause",
    "Replace INNER JOIN Payments with CROSS JOIN Payments",
    "Change IS NULL to IS NOT NULL",
)
MISSING_REPAIR_CORRECT = MISSING_REPAIR_OPTIONS[0]

MISSING_REPAIRED_QUERY = """SELECT o.OrderID, c.CustomerName
FROM Orders AS o
JOIN Customers AS c
  ON c.CustomerID = o.CustomerID
LEFT JOIN Payments AS p
  ON p.OrderID = o.OrderID
WHERE p.PaymentID IS NULL
ORDER BY o.OrderID;"""

AMOUNT_QUERY = """SELECT o.OrderID,
       SUM(ol.Quantity * p.StandardPrice) AS ReportedSales
FROM Orders AS o
JOIN OrderLines AS ol
  ON ol.OrderID = o.OrderID
JOIN Products AS p
  ON p.ProductID = ol.ProductID
GROUP BY o.OrderID
ORDER BY o.OrderID;"""

AMOUNT_CAUSE_OPTIONS = (
    "ol.ActualUnitPrice is the historical transaction fact that records what the customer was charged on each line",
    "p.StandardPrice is master data, so it always equals the price charged on every historical order line",
    "Multiplying p.StandardPrice by 0.90 reliably reconstructs every discount without using the stored transaction price",
    "ol.Quantity alone represents sales because the related product table already contains a price",
)
AMOUNT_CAUSE_CORRECT = AMOUNT_CAUSE_OPTIONS[0]

AMOUNT_FIELD_OPTIONS = (
    "ol.ActualUnitPrice",
    "p.StandardPrice",
    "p.StandardPrice * 0.90",
    "ol.Quantity",
)
AMOUNT_FIELD_CORRECT = "ol.ActualUnitPrice"

ROUTES = ("Accounting report", "Audit exception report")

ROUTE_PROMPTS = {
    "Accounting report": {
        "purpose": "Calculate total fulfilled-order sales by customer using the historical price charged.",
        "required": "Return exactly these aliases: CustomerName and TotalSales. Include every customer with fulfilled orders.",
    },
    "Audit exception report": {
        "purpose": "Identify order lines sold more than 10 percent below the product's standard price.",
        "required": "Return these aliases: OrderLineID, OrderID, ProductName, ActualUnitPrice, StandardPrice, and DiscountPct.",
    },
}

EXPECTED_ACCOUNTING = {
    "Blue Ridge Design": 1695.00,
    "Patterson Legal": 700.00,
    "Riverbend Health": 700.00,
}

EXPECTED_AUDIT = {
    "OL04": ("O5003", "Ergonomic Chair", 275.00, 325.00, 15.384615),
    "OL06": ("O5004", "Desk Lamp", 70.00, 85.00, 17.647059),
}

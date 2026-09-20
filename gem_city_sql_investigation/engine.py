"""Read-only SQLite execution and answer evaluation."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from .case_data import (
    AMOUNT_CAUSE_CORRECT,
    AMOUNT_FIELD_CORRECT,
    CUSTOMERS,
    EXPECTED_ACCOUNTING,
    EXPECTED_AUDIT,
    MISSING_CAUSE_CORRECT,
    MISSING_REPAIR_CORRECT,
    ORDERS,
    ORDER_LINES,
    PAYMENTS,
    PRODUCTS,
    READ_QUESTIONS,
    ROUTES,
)

MAX_QUERY_CHARS = 8_000
MAX_RESULT_ROWS = 100
BLOCKED_SQL = re.compile(
    r"\b(?:insert|update|delete|drop|alter|attach|detach|pragma|replace|create|vacuum|reindex|begin|commit|rollback)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


def build_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE Customers (
            CustomerID TEXT PRIMARY KEY,
            CustomerName TEXT NOT NULL,
            CustomerCity TEXT NOT NULL
        );
        CREATE TABLE Products (
            ProductID TEXT PRIMARY KEY,
            ProductName TEXT NOT NULL,
            StandardPrice REAL NOT NULL
        );
        CREATE TABLE Orders (
            OrderID TEXT PRIMARY KEY,
            OrderDate TEXT NOT NULL,
            CustomerID TEXT NOT NULL REFERENCES Customers(CustomerID),
            OrderStatus TEXT NOT NULL
        );
        CREATE TABLE OrderLines (
            OrderLineID TEXT PRIMARY KEY,
            OrderID TEXT NOT NULL REFERENCES Orders(OrderID),
            ProductID TEXT NOT NULL REFERENCES Products(ProductID),
            Quantity INTEGER NOT NULL,
            ActualUnitPrice REAL NOT NULL
        );
        CREATE TABLE Payments (
            PaymentID TEXT PRIMARY KEY,
            OrderID TEXT NOT NULL REFERENCES Orders(OrderID),
            PaymentDate TEXT NOT NULL,
            Amount REAL NOT NULL
        );
        """
    )
    connection.executemany("INSERT INTO Customers VALUES (?, ?, ?)", CUSTOMERS)
    connection.executemany("INSERT INTO Products VALUES (?, ?, ?)", PRODUCTS)
    connection.executemany("INSERT INTO Orders VALUES (?, ?, ?, ?)", ORDERS)
    connection.executemany("INSERT INTO OrderLines VALUES (?, ?, ?, ?, ?)", ORDER_LINES)
    connection.executemany("INSERT INTO Payments VALUES (?, ?, ?, ?)", PAYMENTS)
    connection.commit()
    return connection


def _safe_query_text(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Write a query before running it.")
    if len(sql) > MAX_QUERY_CHARS:
        raise ValueError("The query is too long for this activity.")
    query = sql.strip()
    if query.endswith(";"):
        query = query[:-1].rstrip()
    if ";" in query:
        raise ValueError("Run one query at a time.")
    if not re.match(r"^(?:select|with)\b", query, re.IGNORECASE):
        raise ValueError("This lab accepts only SELECT queries, including queries that begin with WITH.")
    if BLOCKED_SQL.search(query):
        raise ValueError("This lab is read-only. Use SELECT to retrieve data.")
    return query


def _authorizer(action: int, _arg1: str | None, _arg2: str | None, _db: str | None, _trigger: str | None) -> int:
    safe = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    recursive = getattr(sqlite3, "SQLITE_RECURSIVE", None)
    if recursive is not None:
        safe.add(recursive)
    return sqlite3.SQLITE_OK if action in safe else sqlite3.SQLITE_DENY


def execute_read_only(sql: str) -> QueryResult:
    query = _safe_query_text(sql)
    connection = build_connection()
    try:
        connection.set_authorizer(_authorizer)
        cursor = connection.execute(query)
        rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
        if len(rows) > MAX_RESULT_ROWS:
            raise ValueError(f"Limit the result to {MAX_RESULT_ROWS} rows or fewer.")
        columns = tuple(item[0] for item in cursor.description or ())
        return QueryResult(columns, tuple(tuple(row) for row in rows))
    except sqlite3.Error as error:
        raise ValueError(f"SQLite could not run the query: {error}") from error
    finally:
        connection.close()


def evaluate_reading(responses: dict[str, str]) -> tuple[bool, list[dict[str, Any]]]:
    details = []
    for item_id, prompt, _, answer, explanation in READ_QUESTIONS:
        selected = responses.get(item_id, "")
        details.append(
            {"id": item_id, "prompt": prompt, "selected": selected, "answer": answer, "correct": selected == answer, "explanation": explanation}
        )
    return all(item["correct"] for item in details), details


def evaluate_missing(responses: dict[str, str]) -> tuple[bool, list[dict[str, Any]]]:
    details = [
        {
            "id": "repair",
            "label": "How to repair the query",
            "selected": responses.get("repair", ""),
            "answer": MISSING_REPAIR_CORRECT,
            "correct": responses.get("repair") == MISSING_REPAIR_CORRECT,
            "explanation": "A left join keeps every order, and unmatched payment columns become NULL for the WHERE test.",
        },
        {
            "id": "cause",
            "label": "Why that repair works",
            "selected": responses.get("cause", ""),
            "answer": MISSING_CAUSE_CORRECT,
            "correct": responses.get("cause") == MISSING_CAUSE_CORRECT,
            "explanation": "The original inner join kept only orders that already had a payment match, so no surviving row could have a NULL PaymentID.",
        },
    ]
    return all(item["correct"] for item in details), details


def evaluate_amount(responses: dict[str, str]) -> tuple[bool, list[dict[str, Any]]]:
    details = [
        {
            "id": "field",
            "label": "Which field belongs in sales",
            "selected": responses.get("field", ""),
            "answer": AMOUNT_FIELD_CORRECT,
            "correct": responses.get("field") == AMOUNT_FIELD_CORRECT,
            "explanation": "ActualUnitPrice is stored on each line because it is a historical transaction fact.",
        },
        {
            "id": "cause",
            "label": "Why that field is appropriate",
            "selected": responses.get("cause", ""),
            "answer": AMOUNT_CAUSE_CORRECT,
            "correct": responses.get("cause") == AMOUNT_CAUSE_CORRECT,
            "explanation": "StandardPrice is current master data and remains useful as a benchmark, but it does not prove what the customer was charged on an earlier transaction.",
        },
    ]
    return all(item["correct"] for item in details), details


def _column_positions(columns: tuple[str, ...], required: tuple[str, ...]) -> dict[str, int]:
    normalized = {name.lower(): index for index, name in enumerate(columns)}
    missing = [name for name in required if name.lower() not in normalized]
    if missing:
        raise ValueError("Use the required column aliases: " + ", ".join(required) + ".")
    return {name: normalized[name.lower()] for name in required}


def evaluate_custom_query(route: str, sql: str) -> tuple[bool, str, QueryResult | None]:
    if route not in ROUTES:
        return False, "Choose an assignment route.", None
    try:
        result = execute_read_only(sql)
    except (ValueError, TypeError) as error:
        return False, str(error), None

    try:
        if route == "Accounting report":
            pos = _column_positions(result.columns, ("CustomerName", "TotalSales"))
            actual = {}
            for row in result.rows:
                actual[str(row[pos["CustomerName"]])] = round(float(row[pos["TotalSales"]]), 2)
            if actual != EXPECTED_ACCOUNTING:
                return False, "The columns are present, but the customer totals or included customers do not match the underlying fulfilled-order data.", result
            return True, "The report returns every customer with fulfilled orders and values sales using the historical price charged.", result

        pos = _column_positions(
            result.columns,
            ("OrderLineID", "OrderID", "ProductName", "ActualUnitPrice", "StandardPrice", "DiscountPct"),
        )
        actual = {}
        for row in result.rows:
            actual[str(row[pos["OrderLineID"]])] = (
                str(row[pos["OrderID"]]),
                str(row[pos["ProductName"]]),
                round(float(row[pos["ActualUnitPrice"]]), 2),
                round(float(row[pos["StandardPrice"]]), 2),
                float(row[pos["DiscountPct"]]),
            )
        if set(actual) != set(EXPECTED_AUDIT):
            return False, "The result should contain only the two order lines discounted more than 10 percent.", result
        for line_id, expected in EXPECTED_AUDIT.items():
            observed = actual[line_id]
            if observed[:4] != (expected[0], expected[1], expected[2], expected[3]) or abs(observed[4] - expected[4]) > 0.05:
                return False, "The exception lines are present, but one or more displayed values or discount percentages are incorrect.", result
        return True, "The query isolates the two lines whose actual selling price is more than 10 percent below standard.", result
    except (ValueError, TypeError) as error:
        return False, str(error), result

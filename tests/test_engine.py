import unittest

from gem_city_sql_investigation.case_data import (
    AMOUNT_CAUSE_CORRECT,
    AMOUNT_CAUSE_OPTIONS,
    AMOUNT_FIELD_CORRECT,
    AMOUNT_FIELD_OPTIONS,
    MISSING_CAUSE_CORRECT,
    MISSING_CAUSE_OPTIONS,
    MISSING_REPAIR_CORRECT,
    MISSING_REPAIR_OPTIONS,
    READ_QUESTIONS,
)
from gem_city_sql_investigation.engine import (
    evaluate_amount,
    evaluate_custom_query,
    evaluate_missing,
    evaluate_reading,
    execute_read_only,
)


ACCOUNTING_SQL = """SELECT c.CustomerName AS CustomerName,
SUM(ol.Quantity * ol.ActualUnitPrice) AS TotalSales
FROM Customers c
JOIN Orders o ON o.CustomerID = c.CustomerID
JOIN OrderLines ol ON ol.OrderID = o.OrderID
WHERE o.OrderStatus = 'Fulfilled'
GROUP BY c.CustomerID, c.CustomerName
ORDER BY TotalSales DESC, CustomerName"""

AUDIT_SQL = """SELECT ol.OrderLineID AS OrderLineID, ol.OrderID AS OrderID,
p.ProductName AS ProductName, ol.ActualUnitPrice AS ActualUnitPrice,
p.StandardPrice AS StandardPrice,
((p.StandardPrice - ol.ActualUnitPrice) / p.StandardPrice) * 100.0 AS DiscountPct
FROM OrderLines ol
JOIN Products p ON p.ProductID = ol.ProductID
WHERE ol.ActualUnitPrice < p.StandardPrice * 0.90
ORDER BY DiscountPct DESC"""


class EngineTests(unittest.TestCase):
    def test_diagnostic_keys(self):
        reading = {item_id: answer for item_id, _, _, answer, _ in READ_QUESTIONS}
        self.assertTrue(evaluate_reading(reading)[0])
        self.assertTrue(evaluate_missing({"cause": MISSING_CAUSE_CORRECT, "repair": MISSING_REPAIR_CORRECT})[0])
        self.assertTrue(evaluate_amount({"cause": AMOUNT_CAUSE_CORRECT, "field": AMOUNT_FIELD_CORRECT})[0])

    def test_every_wrong_diagnostic_choice_has_a_nonrevealing_hint(self):
        for item_id, _, options, answer, _ in READ_QUESTIONS:
            for option in options:
                if option == answer:
                    continue
                _, details = evaluate_reading({item_id: option})
                detail = next(item for item in details if item["id"] == item_id)
                self.assertTrue(detail["hint"])
                self.assertNotIn(answer.casefold(), detail["hint"].casefold())

        diagnostic_sets = (
            (evaluate_missing, "repair", MISSING_REPAIR_OPTIONS, MISSING_REPAIR_CORRECT),
            (evaluate_missing, "cause", MISSING_CAUSE_OPTIONS, MISSING_CAUSE_CORRECT),
            (evaluate_amount, "field", AMOUNT_FIELD_OPTIONS, AMOUNT_FIELD_CORRECT),
            (evaluate_amount, "cause", AMOUNT_CAUSE_OPTIONS, AMOUNT_CAUSE_CORRECT),
        )
        for evaluator, item_id, options, answer in diagnostic_sets:
            for option in options:
                if option == answer:
                    continue
                _, details = evaluator({item_id: option})
                detail = next(item for item in details if item["id"] == item_id)
                self.assertTrue(detail["hint"])
                self.assertNotIn(answer.casefold(), detail["hint"].casefold())

    def test_custom_routes_are_validated_by_results(self):
        self.assertTrue(evaluate_custom_query("Accounting report", ACCOUNTING_SQL)[0])
        self.assertTrue(evaluate_custom_query("Audit exception report", AUDIT_SQL)[0])

    def test_valid_wrong_query_still_returns_its_output(self):
        passed, message, result = evaluate_custom_query(
            "Accounting report",
            "SELECT CustomerID, CustomerName FROM Customers ORDER BY CustomerID",
        )
        self.assertFalse(passed)
        self.assertIn("aliases", message)
        self.assertIsNotNone(result)
        self.assertEqual(len(result.rows), 3)

    def test_read_only_executor_blocks_changes_and_multiple_statements(self):
        with self.assertRaises(ValueError):
            execute_read_only("DELETE FROM Orders")
        with self.assertRaises(ValueError):
            execute_read_only("SELECT * FROM Orders; SELECT * FROM Customers")
        result = execute_read_only("SELECT OrderID FROM Orders ORDER BY OrderID")
        self.assertEqual(len(result.rows), 4)


if __name__ == "__main__":
    unittest.main()

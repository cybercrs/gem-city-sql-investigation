import unittest

from gem_city_sql_investigation.case_data import (
    AMOUNT_CAUSE_CORRECT,
    AMOUNT_FIELD_CORRECT,
    MISSING_CAUSE_CORRECT,
    MISSING_REPAIR_CORRECT,
    READ_QUESTIONS,
)
from gem_city_sql_investigation.progress import activity_defaults, decode_snapshot, encode_state, reset_saved_progress
from tests.test_engine import ACCOUNTING_SQL, AUDIT_SQL


def complete_state():
    state = activity_defaults()
    state["si_shuffle_seed"] = 34105
    state["si_stage"] = 5
    state["si_reading"] = {item_id: answer for item_id, _, _, answer, _ in READ_QUESTIONS}
    state["si_missing"] = {"cause": MISSING_CAUSE_CORRECT, "repair": MISSING_REPAIR_CORRECT}
    state["si_amount"] = {"cause": AMOUNT_CAUSE_CORRECT, "field": AMOUNT_FIELD_CORRECT}
    state["si_drafts"] = {
        "reading": dict(state["si_reading"]),
        "missing": dict(state["si_missing"]),
        "amount": dict(state["si_amount"]),
    }
    state["si_custom"] = {
        "Accounting report": {"draft": ACCOUNTING_SQL, "submitted": ACCOUNTING_SQL, "passed": True},
        "Audit exception report": {"draft": AUDIT_SQL, "submitted": AUDIT_SQL, "passed": True},
    }
    state["si_attempts"] = {"reading": 1, "missing": 1, "amount": 1, "accounting": 1, "audit": 1}
    return state


class ProgressTests(unittest.TestCase):
    def test_completed_round_trip(self):
        restored = decode_snapshot(encode_state(complete_state()))
        self.assertIsNotNone(restored)
        self.assertEqual(restored["si_stage"], 5)

    def test_partial_draft_and_shuffle_seed_round_trip(self):
        state = activity_defaults()
        state["si_stage"] = 1
        state["si_shuffle_seed"] = 987654
        item_id, _, _, answer, _ = READ_QUESTIONS[0]
        state["si_drafts"]["reading"] = {item_id: answer}
        restored = decode_snapshot(encode_state(state))
        self.assertIsNotNone(restored)
        self.assertEqual(restored["si_shuffle_seed"], 987654)
        self.assertEqual(restored["si_drafts"]["reading"][item_id], answer)

    def test_skipped_stage_is_rejected(self):
        state = activity_defaults()
        state["si_stage"] = 4
        self.assertIsNone(decode_snapshot(encode_state(state)))

    def test_tampered_success_is_rejected(self):
        state = complete_state()
        state["si_custom"]["Accounting report"]["draft"] = "SELECT * FROM Customers"
        state["si_custom"]["Accounting report"]["submitted"] = "SELECT * FROM Customers"
        self.assertIsNone(decode_snapshot(encode_state(state)))

    def test_partial_custom_drafts_round_trip(self):
        state = complete_state()
        state["si_stage"] = 4
        state["si_custom"] = {
            "Accounting report": {"draft": "SELECT c.CustomerName", "submitted": "", "passed": False},
            "Audit exception report": {"draft": "SELECT ol.OrderLineID", "submitted": "", "passed": False},
        }
        restored = decode_snapshot(encode_state(state))
        self.assertIsNotNone(restored)
        self.assertEqual(restored["si_custom"]["Accounting report"]["draft"], "SELECT c.CustomerName")
        self.assertEqual(restored["si_custom"]["Audit exception report"]["draft"], "SELECT ol.OrderLineID")

    def test_future_draft_is_rejected(self):
        state = activity_defaults()
        state["si_stage"] = 1
        state["si_drafts"]["amount"] = {"field": AMOUNT_FIELD_CORRECT}
        self.assertIsNone(decode_snapshot(encode_state(state)))

    def test_reset_replaces_progress(self):
        state = complete_state()
        query = {}
        reset_saved_progress(state, query)
        self.assertEqual(state["si_stage"], 0)
        self.assertEqual(state["si_drafts"]["reading"], {})
        self.assertIsNotNone(decode_snapshot(query["progress"]))


if __name__ == "__main__":
    unittest.main()

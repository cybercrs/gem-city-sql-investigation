import unittest

from streamlit.testing.v1 import AppTest

from gem_city_sql_investigation.case_data import (
    AMOUNT_CAUSE_CORRECT,
    AMOUNT_FIELD_CORRECT,
    MISSING_CAUSE_CORRECT,
    MISSING_REPAIR_CORRECT,
    READ_QUESTIONS,
)
from gem_city_sql_investigation.progress import SNAPSHOT_PARAM, decode_snapshot
from tests.test_engine import ACCOUNTING_SQL, AUDIT_SQL


def button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


class AppFlowTests(unittest.TestCase):
    def test_complete_both_query_routes(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        self.assertFalse(app.exception)
        button(app, "Begin reading SQL").click().run()

        for item_id, _, _, answer, _ in READ_QUESTIONS:
            app.radio(key=f"widget_si_read_{item_id}").set_value(answer)
        button(app, "Check how the query works").click().run()
        button(app, "Continue to the missing-record case").click().run()

        app.radio(key="widget_si_missing_cause").set_value(MISSING_CAUSE_CORRECT)
        app.radio(key="widget_si_missing_repair").set_value(MISSING_REPAIR_CORRECT)
        button(app, "Diagnose the missing rows").click().run()
        button(app, "Continue to the wrong-amount case").click().run()

        app.radio(key="widget_si_amount_cause").set_value(AMOUNT_CAUSE_CORRECT)
        app.radio(key="widget_si_amount_field").set_value(AMOUNT_FIELD_CORRECT)
        button(app, "Diagnose the amount").click().run()
        button(app, "Continue to the custom query").click().run()

        app.text_area(key="widget_si_accounting_sql").set_value(ACCOUNTING_SQL)
        button(app, "Check accounting report").click().run()
        app.text_area(key="widget_si_audit_sql").set_value(AUDIT_SQL)
        button(app, "Check audit exception report").click().run()
        button(app, "Complete the SQL investigation").click().run()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["si_stage"], 5)
        self.assertTrue(any("investigation complete" in item.value.lower() for item in app.markdown))

    def test_both_query_editors_start_empty(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        app.session_state["si_stage"] = 4
        app.run()
        self.assertEqual(app.text_area(key="widget_si_accounting_sql").value, "")
        self.assertEqual(app.text_area(key="widget_si_audit_sql").value, "")

    def test_valid_but_incorrect_query_displays_its_output(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        app.session_state["si_stage"] = 4
        app.run()
        app.text_area(key="widget_si_accounting_sql").set_value(
            "SELECT CustomerID, CustomerName FROM Customers ORDER BY CustomerID"
        )
        button(app, "Check accounting report").click().run()
        self.assertTrue(app.dataframe)
        self.assertTrue(any("required column aliases" in item.value.lower() for item in app.error))

    def test_partial_selection_is_saved_in_the_url(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        button(app, "Begin reading SQL").click().run()
        item_id, _, _, answer, _ = READ_QUESTIONS[0]
        app.radio(key=f"widget_si_read_{item_id}").set_value(answer).run()

        token = app.query_params[SNAPSHOT_PARAM]
        restored = decode_snapshot(token[0] if isinstance(token, list) else token)
        self.assertIsNotNone(restored)
        self.assertEqual(restored["si_stage"], 1)
        self.assertEqual(restored["si_drafts"]["reading"][item_id], answer)

    def test_progress_pills_match_numbered_steps(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        rendered = "\n".join(item.value for item in app.markdown)
        for label in ("Brief", "1. Read", "2. Missing rows", "3. Wrong amount", "4. Write", "Complete"):
            self.assertIn(label, rendered)

    def test_wrong_answer_can_be_revised_and_checked_in_one_action(self):
        app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
        button(app, "Begin reading SQL").click().run()

        correct_answers = {item_id: answer for item_id, _, _, answer, _ in READ_QUESTIONS}
        first_id, _, first_options, first_answer, _ = READ_QUESTIONS[0]
        wrong_answer = next(option for option in first_options if option != first_answer)
        for item_id, answer in correct_answers.items():
            app.radio(key=f"widget_si_read_{item_id}").set_value(wrong_answer if item_id == first_id else answer)
        button(app, "Check how the query works").click().run()

        self.assertEqual(app.radio(key=f"widget_si_read_{first_id}").value, wrong_answer)
        self.assertTrue(any(item.label == "Check revised answers" for item in app.button))

        app.radio(key=f"widget_si_read_{first_id}").set_value(first_answer)
        button(app, "Check revised answers").click().run()

        self.assertEqual(app.session_state["si_reading"][first_id], first_answer)
        self.assertTrue(any(item.label == "Continue to the missing-record case" for item in app.button))
        self.assertFalse(any(item.label.startswith("Revise") for item in app.button))


if __name__ == "__main__":
    unittest.main()

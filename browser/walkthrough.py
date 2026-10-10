from playwright.sync_api import expect
from gem_city_sql_investigation.case_data import (
    READ_QUESTIONS,
    MISSING_CAUSE_CORRECT,
    MISSING_REPAIR_CORRECT,
    AMOUNT_CAUSE_CORRECT,
    AMOUNT_FIELD_CORRECT,
)
from tests.test_engine import ACCOUNTING_SQL, AUDIT_SQL


def lesson(page, click, choose, select, idle, check, results, readonly):
    click("Begin reading SQL")
    first_id, _, options, answer, _ = READ_QUESTIONS[0]
    for item_id, _, choices, correct, _ in READ_QUESTIONS:
        choose(
            next(x for x in choices if x != correct)
            if item_id == first_id
            else correct,
            "widget_si_read_" + item_id,
        )
    click("Check how the query works")
    assert idle()["si_attempts"]["reading"] == 1
    expect(page.get_by_role("button", name="Forward", exact=True)).to_be_disabled()
    click("Check revised answers")
    assert idle()["si_attempts"]["reading"] == 2
    choose(answer, "widget_si_read_" + first_id)
    click("Check revised answers")
    assert idle()["si_attempts"]["reading"] == 3
    click("Continue to the missing-record case")
    choose(MISSING_CAUSE_CORRECT, "widget_si_missing_cause")
    choose(MISSING_REPAIR_CORRECT, "widget_si_missing_repair")
    click("Diagnose the missing rows")
    click("Continue to the wrong-amount case")
    choose(AMOUNT_CAUSE_CORRECT, "widget_si_amount_cause")
    choose(AMOUNT_FIELD_CORRECT, "widget_si_amount_field")
    click("Diagnose the amount")
    click("Continue to the custom query")
    editor = page.get_by_role("textbox", name="Accounting report SQL", exact=True)
    editor.fill("SELECT CustomerID, CustomerName FROM Customers ORDER BY CustomerID")
    editor.press("Tab")
    idle()
    before = idle()
    click("Back")
    readonly()
    assert idle() == before
    click("Forward")
    page.reload()
    idle()
    expect(editor).to_have_value(
        "SELECT CustomerID, CustomerName FROM Customers ORDER BY CustomerID"
    )
    check("SQL draft survives review navigation and refresh")
    click("Check accounting report")
    assert not idle()["si_custom"]["Accounting report"]["passed"]
    expect(page.locator("[data-testid=stDataFrame]")).to_be_visible()
    # WITH passes the statement prefix check and reaches SQLite's authorizer.
    editor.fill("WITH x AS (SELECT 1) DELETE FROM Customers")
    click("Check accounting report")
    expect(
        page.get_by_text(
            "This lab is read-only. Use SELECT to retrieve data.", exact=True
        )
    ).to_be_visible()
    assert not idle()["si_custom"]["Accounting report"]["passed"]
    expect(page.get_by_role("button", name="Forward", exact=True)).to_be_disabled()
    editor.fill(ACCOUNTING_SQL)
    click("Check accounting report")
    assert idle()["si_custom"]["Accounting report"]["passed"]
    audit = page.get_by_role("textbox", name="Audit exception report SQL", exact=True)
    audit.fill(AUDIT_SQL)
    click("Check audit exception report")
    assert idle()["si_custom"]["Audit exception report"]["passed"]
    click("Complete the SQL investigation")
    assert idle()["si_stage"] == 5
    check(
        "Full SQL lesson, incorrect reports, authorizer rejection, pandas output and both correct report routes"
    )


def radio_label(page, key):
    if key.startswith("widget_si_read_"):
        return next(
            prompt
            for item_id, prompt, _, _, _ in READ_QUESTIONS
            if key == "widget_si_read_" + item_id
        )
    return {
        "widget_si_missing_repair": "1. Which repair matches the reporting purpose?",
        "widget_si_missing_cause": "2. Which explanation best supports that repair?",
        "widget_si_amount_field": "1. Which value should be multiplied by ol.Quantity in the ReportedSales expression?",
        "widget_si_amount_cause": "2. Which explanation best supports that choice?",
    }[key]

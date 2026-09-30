"""Student-facing Streamlit app for accounting-focused SQL reasoning."""

from __future__ import annotations

import hashlib
import random
from html import escape

import pandas as pd
import streamlit as st

from gem_city_sql_investigation.case_data import (
    AMOUNT_CAUSE_OPTIONS,
    AMOUNT_FIELD_OPTIONS,
    AMOUNT_QUERY,
    COMPANY_NAME,
    MISSING_CAUSE_OPTIONS,
    MISSING_QUERY,
    MISSING_REPAIRED_QUERY,
    MISSING_REPAIR_OPTIONS,
    PRIMARY_KEYS,
    READ_QUERY,
    READ_QUESTIONS,
    ROUTE_PROMPTS,
    ROUTES,
    SCHEMA,
)
from gem_city_sql_investigation.engine import (
    evaluate_amount,
    evaluate_custom_query,
    evaluate_missing,
    evaluate_reading,
    execute_read_only,
)
from gem_city_sql_investigation.progress import (
    SNAPSHOT_PARAM,
    activity_defaults,
    record_attempt,
    reset_saved_progress,
    restore_session_state,
    sync_progress_query,
)
from gem_city_sql_investigation.theme import APP_CSS


st.set_page_config(
    page_title="Gem City SQL Investigation",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

STAGE_LABELS = ("Brief", "1. Read", "2. Missing rows", "3. Wrong amount", "4. Write", "Complete")
ROUTE_KEYS = {
    "Accounting report": "accounting",
    "Audit exception report": "audit",
}


def initialize_state() -> None:
    if "si_restore_attempted" not in st.session_state:
        restored = restore_session_state(st.session_state, st.query_params.get(SNAPSHOT_PARAM))
        st.session_state.si_restore_attempted = True
        if restored:
            st.session_state.si_scroll_to_top = True
    for key, value in activity_defaults().items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_stage(stage: int) -> None:
    st.session_state.si_stage = stage
    st.session_state.si_scroll_to_top = True


def restart() -> None:
    reset_saved_progress(st.session_state, st.query_params)
    st.session_state.si_scroll_to_top = True


def save_draft(group: str, answer_key: str, widget_key: str) -> None:
    """Persist an unfinished choice outside widget state so refresh can restore it."""

    drafts = {key: dict(value) for key, value in st.session_state.si_drafts.items()}
    group_answers = dict(drafts[group])
    value = st.session_state.get(widget_key)
    if value is None:
        group_answers.pop(answer_key, None)
    else:
        group_answers[answer_key] = str(value)
    drafts[group] = group_answers
    st.session_state.si_drafts = drafts


def replace_draft(group: str, answers: dict[str, str]) -> None:
    drafts = {key: dict(value) for key, value in st.session_state.si_drafts.items()}
    drafts[group] = dict(answers)
    st.session_state.si_drafts = drafts


def save_custom_sql(route: str, widget_key: str) -> None:
    custom = {key: dict(value) for key, value in st.session_state.si_custom.items()}
    custom[route] = {
        "draft": st.session_state.get(widget_key, ""),
        "submitted": "",
        "passed": False,
    }
    st.session_state.si_custom = custom


def shuffled(items: tuple | list, salt: str) -> list:
    """Return a stable per-student order that survives reruns and refreshes."""

    digest = hashlib.sha256(f"{st.session_state.si_shuffle_seed}:{salt}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    ordered = list(items)
    rng.shuffle(ordered)
    if len(ordered) > 1 and ordered == list(items):
        ordered = ordered[1:] + ordered[:1]
    return ordered


def selected_index(options: tuple | list, selected: str | None) -> int | None:
    return list(options).index(selected) if selected in options else None


def render_scroll_reset() -> None:
    """Reset after navigation without overriding student-initiated scrolling."""

    if not st.session_state.pop("si_scroll_to_top", False):
        return
    st.iframe(
        """
        <script>
        (() => {
          const parent = window.parent;
          const main = parent.document.querySelector('section[data-testid="stMain"]');
          if (!main) return;
          let cancelled = false;
          let finished = false;
          const scrollingKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);
          const cancel = () => { cancelled = true; cleanup(); };
          const cancelKey = (event) => { if (scrollingKeys.has(event.key)) cancel(); };
          const cleanup = () => {
            parent.removeEventListener('wheel', cancel);
            parent.removeEventListener('touchstart', cancel);
            parent.removeEventListener('keydown', cancelKey);
          };
          const reset = () => {
            if (finished) return;
            finished = true;
            if (!cancelled) main.scrollTo({ top: 0, left: 0, behavior: 'auto' });
            cleanup();
          };
          parent.addEventListener('wheel', cancel, { passive: true });
          parent.addEventListener('touchstart', cancel, { passive: true });
          parent.addEventListener('keydown', cancelKey);
          parent.requestAnimationFrame(() => parent.requestAnimationFrame(reset));
          parent.setTimeout(reset, 120);
        })();
        </script>
        """,
        height=1,
        tab_index=-1,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="kicker">ORDER-TO-CASH SQL REASONING</div>
          <h1>Gem City SQL Investigation</h1>
          <p>Read the query, locate the reporting failure, repair the logic, and write a defensible accounting or audit report.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stage_row() -> None:
    current = int(st.session_state.si_stage)
    pills = []
    for index, label in enumerate(STAGE_LABELS):
        status = "complete" if index < current else "active" if index == current else ""
        pills.append(f'<div class="stage-pill {status}">{escape(label)}</div>')
    st.markdown(f'<div class="stage-row">{"".join(pills)}</div>', unsafe_allow_html=True)


def render_feedback(label: str, correct: bool, guidance: str, selected: str = "") -> None:
    status = "correct" if correct else ""
    result = "Correct" if correct else "Reconsider"
    selection = f" Your answer: {escape(selected)}." if selected else ""
    st.markdown(
        f'<div class="feedback {status}"><strong>{escape(label)} — {result}.</strong>{selection} {escape(guidance)}</div>',
        unsafe_allow_html=True,
    )


def render_schema_cards() -> None:
    cards = []
    for table, fields in SCHEMA.items():
        field_html = "".join(
            f'<div class="schema-field{" primary-key" if (table, field) in PRIMARY_KEYS else ""}">{escape(field)}</div>'
            for field in fields
        )
        cards.append(f'<section class="schema-table"><h4>{escape(table)}</h4>{field_html}</section>')
    st.markdown(
        f'<div class="schema-key"><span>CustomerID</span> Primary key field</div>'
        f'<div class="schema-grid">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def result_frame(result) -> pd.DataFrame:
    return pd.DataFrame(result.rows, columns=result.columns)


def render_result_table(result) -> None:
    """Fit common case outputs without forcing equal column widths."""

    frame = result_frame(result)
    column_config = {}
    for column in frame.columns:
        if column in {"ActualUnitPrice", "StandardPrice", "Amount", "TotalSales", "LineAmount"}:
            column_config[column] = st.column_config.NumberColumn(column, format="$%.2f", width="small")
        elif column == "DiscountPct":
            column_config[column] = st.column_config.NumberColumn(column, format="%.1f%%", width="small")
        elif column in {"CustomerName", "ProductName"}:
            column_config[column] = st.column_config.TextColumn(column, width="medium")
        else:
            column_config[column] = st.column_config.TextColumn(column, width="small")
    st.dataframe(
        frame,
        column_config=column_config,
        hide_index=True,
        row_height=34,
        width="stretch",
    )


def render_schema_stage() -> None:
    st.markdown('<div class="eyebrow">Investigation briefing</div>', unsafe_allow_html=True)
    st.header(f"Turn {COMPANY_NAME} data into useful accounting information")
    st.markdown(
        f"{COMPANY_NAME} sells office furnishings to business customers. Its order-to-cash information is stored in a normalized database, with related business facts separated into connected tables."
    )
    st.markdown(
        '<div class="case-card"><strong>Your investigation</strong> You will interpret existing SQL, diagnose why plausible queries produce incomplete or misleading results, and then build both an accounting report and an audit exception report. The goal is to connect query logic to the accounting purpose the output must serve.</div>',
        unsafe_allow_html=True,
    )
    st.button("Begin reading SQL", type="primary", width="stretch", on_click=set_stage, args=(1,))


def render_reading() -> None:
    st.markdown('<div class="eyebrow">Step 1</div>', unsafe_allow_html=True)
    st.header("Read the query in logical order")
    st.markdown(
        '<p class="lead"><strong>Your task:</strong> Trace what the database must do with the query. SQL begins with SELECT when written, but the database must establish the row sources and joins before it can filter rows and shape the final output.</p>',
        unsafe_allow_html=True,
    )
    st.code(READ_QUERY, language="sql")
    response = dict(st.session_state.si_reading)
    draft = dict(st.session_state.si_drafts["reading"])
    ordered_questions = shuffled(READ_QUESTIONS, "reading-question-order")
    response_correct = bool(response) and evaluate_reading(response)[0]
    if not response_correct:
        if response:
            st.info("Revise any answer below, then select Check revised answers.")
        answers = {}
        for item_id, prompt, options, _, _ in ordered_questions:
            ordered_options = shuffled(options, f"reading-answer-order:{item_id}")
            widget_key = f"widget_si_read_{item_id}"
            answers[item_id] = st.radio(
                prompt,
                ordered_options,
                index=selected_index(ordered_options, draft.get(item_id)),
                key=widget_key,
                on_change=save_draft,
                args=("reading", item_id, widget_key),
            )
        button_label = "Check revised answers" if response else "Check how the query works"
        submitted = st.button(button_label, type="primary", width="stretch")
        if submitted:
            if any(value is None for value in answers.values()):
                st.warning("Answer all three questions before checking your reasoning.")
            else:
                response = {key: str(value) for key, value in answers.items()}
                replace_draft("reading", response)
                st.session_state.si_reading = response
                record_attempt(st.session_state, "reading")
                st.rerun()

    if response:
        correct, details = evaluate_reading(response)
        details_by_id = {str(detail["id"]): detail for detail in details}
        for item_id, _, _, _, _ in ordered_questions:
            detail = details_by_id[item_id]
            guidance = str(detail["explanation"]) if detail["correct"] else f"Hint: {detail['hint']}"
            render_feedback(str(detail["prompt"]), bool(detail["correct"]), guidance, str(detail["selected"]))
        if correct:
            st.button("Continue to the missing-record case", type="primary", width="stretch", on_click=set_stage, args=(2,))


def render_missing() -> None:
    st.markdown('<div class="eyebrow">Step 2</div>', unsafe_allow_html=True)
    st.header("Find why the unpaid-order report returns nothing")
    st.markdown(
        '<p class="lead"><strong>Your task:</strong> Choose the repair that preserves the records the controller needs, then select the explanation that supports your repair.</p>',
        unsafe_allow_html=True,
    )
    st.markdown("The controller expects the report to list orders with no payment record. The current query returns zero rows even though two orders have no related payment.")
    st.code(MISSING_QUERY, language="sql")
    response = dict(st.session_state.si_missing)
    draft = dict(st.session_state.si_drafts["missing"])
    question_specs = (
        ("repair", "1. Which repair matches the reporting purpose?", MISSING_REPAIR_OPTIONS),
        ("cause", "2. Which explanation best supports that repair?", MISSING_CAUSE_OPTIONS),
    )
    response_correct = bool(response) and evaluate_missing(response)[0]
    if not response_correct:
        if response:
            st.info("Revise either answer below, then select Check revised answers.")
        answers = {}
        for item_id, prompt, options in question_specs:
            ordered_options = shuffled(options, f"missing-answer-order:{item_id}")
            widget_key = f"widget_si_missing_{item_id}"
            answers[item_id] = st.radio(
                prompt,
                ordered_options,
                index=selected_index(ordered_options, draft.get(item_id)),
                key=widget_key,
                on_change=save_draft,
                args=("missing", item_id, widget_key),
            )
        button_label = "Check revised answers" if response else "Diagnose the missing rows"
        submitted = st.button(button_label, type="primary", width="stretch")
        if submitted:
            if any(value is None for value in answers.values()):
                st.warning("Choose both the cause and the repair before checking your work.")
            else:
                response = {key: str(value) for key, value in answers.items()}
                replace_draft("missing", response)
                st.session_state.si_missing = response
                record_attempt(st.session_state, "missing")
                st.rerun()

    if response:
        correct, details = evaluate_missing(response)
        details_by_id = {str(detail["id"]): detail for detail in details}
        for item_id, _, _ in question_specs:
            detail = details_by_id[item_id]
            guidance = str(detail["explanation"]) if detail["correct"] else f"Hint: {detail['hint']}"
            render_feedback(str(detail["label"]), bool(detail["correct"]), guidance, str(detail["selected"]))
        if correct:
            st.subheader("Repaired query and result")
            st.code(MISSING_REPAIRED_QUERY, language="sql")
            render_result_table(execute_read_only(MISSING_REPAIRED_QUERY))
            st.markdown(
                '<div class="principle"><strong>Accounting interpretation</strong> No payment row means no payment record in this database. It does not prove the customer owes the full order amount unless the system also records partial payments, credits, write-offs, and timing consistently.</div>',
                unsafe_allow_html=True,
            )
            st.button("Continue to the wrong-amount case", type="primary", width="stretch", on_click=set_stage, args=(3,))


def render_amount() -> None:
    st.markdown('<div class="eyebrow">Step 3</div>', unsafe_allow_html=True)
    st.header("Find why the sales amount is overstated")
    st.markdown(
        '<p class="lead"><strong>Your task:</strong> Choose the value that measures the historical exchange, then select the explanation that supports your choice.</p>',
        unsafe_allow_html=True,
    )
    st.markdown("The query runs and every order appears, but discounted lines are valued at the standard price instead of the price the customer actually paid.")
    st.code(AMOUNT_QUERY, language="sql")
    response = dict(st.session_state.si_amount)
    draft = dict(st.session_state.si_drafts["amount"])
    question_specs = (
        ("field", "1. Which value should be multiplied by ol.Quantity in the ReportedSales expression?", AMOUNT_FIELD_OPTIONS),
        ("cause", "2. Which explanation best supports that choice?", AMOUNT_CAUSE_OPTIONS),
    )
    response_correct = bool(response) and evaluate_amount(response)[0]
    if not response_correct:
        if response:
            st.info("Revise either answer below, then select Check revised answers.")
        answers = {}
        for item_id, prompt, options in question_specs:
            ordered_options = shuffled(options, f"amount-answer-order:{item_id}")
            widget_key = f"widget_si_amount_{item_id}"
            answers[item_id] = st.radio(
                prompt,
                ordered_options,
                index=selected_index(ordered_options, draft.get(item_id)),
                key=widget_key,
                on_change=save_draft,
                args=("amount", item_id, widget_key),
            )
        button_label = "Check revised answers" if response else "Diagnose the amount"
        submitted = st.button(button_label, type="primary", width="stretch")
        if submitted:
            if any(value is None for value in answers.values()):
                st.warning("Answer both questions before checking your work.")
            else:
                response = {key: str(value) for key, value in answers.items()}
                replace_draft("amount", response)
                st.session_state.si_amount = response
                record_attempt(st.session_state, "amount")
                st.rerun()

    if response:
        correct, details = evaluate_amount(response)
        details_by_id = {str(detail["id"]): detail for detail in details}
        for item_id, _, _ in question_specs:
            detail = details_by_id[item_id]
            guidance = str(detail["explanation"]) if detail["correct"] else f"Hint: {detail['hint']}"
            render_feedback(str(detail["label"]), bool(detail["correct"]), guidance, str(detail["selected"]))
        if correct:
            st.markdown(
                '<div class="principle"><strong>Correct measure</strong> Sales for each line are ol.Quantity × ol.ActualUnitPrice. p.StandardPrice remains useful for exception testing, but it is not the recorded exchange amount.</div>',
                unsafe_allow_html=True,
            )
            st.button("Continue to the custom query", type="primary", width="stretch", on_click=set_stage, args=(4,))


def render_query_workspace(route: str, number: int) -> None:
    route_key = ROUTE_KEYS[route]
    prompt = ROUTE_PROMPTS[route]
    widget_key = f"widget_si_{route_key}_sql"
    entry = dict(st.session_state.si_custom[route])

    st.subheader(f"{number}. {route}")
    st.markdown(
        f'<div class="purpose"><strong>Purpose</strong> {escape(prompt["purpose"])}<br><strong>Required output</strong> {escape(prompt["required"])}</div>',
        unsafe_allow_html=True,
    )

    if widget_key not in st.session_state:
        st.session_state[widget_key] = entry["draft"]
    sql = st.text_area(
        f"{route} SQL",
        height=260,
        key=widget_key,
        placeholder="Enter your SQL here.",
        on_change=save_custom_sql,
        args=(route, widget_key),
    )
    run_clicked = st.button(
        f"Check {route.lower()}",
        key=f"check_si_{route_key}",
        type="primary",
        width="stretch",
    )
    if run_clicked:
        passed, _, _ = evaluate_custom_query(route, sql)
        custom = {key: dict(value) for key, value in st.session_state.si_custom.items()}
        custom[route] = {"draft": sql, "submitted": sql, "passed": passed}
        st.session_state.si_custom = custom
        record_attempt(st.session_state, route_key)
        entry = dict(custom[route])

    if entry["submitted"]:
        passed, message, result = evaluate_custom_query(route, entry["submitted"])
        if result is not None:
            st.markdown("**Your query output**")
            render_result_table(result)
        if passed:
            st.success(message)
            if route == "Accounting report":
                st.markdown("This result summarizes the full fulfilled-order population by customer using the price actually charged on each line.")
            else:
                st.markdown("This result is an exception population, not proof of error. The next step would be to inspect authorization, contracts, promotions, and related-party indicators for these lines.")
        else:
            st.error(message)


def render_custom() -> None:
    st.markdown('<div class="eyebrow">Step 4</div>', unsafe_allow_html=True)
    st.header("Build two queries for two accounting purposes")
    st.markdown(
        '<p class="lead"><strong>Your task:</strong> Write both queries below. Each editor is checked independently, and any executable query will display its output so you can compare the result with the stated purpose and revise.</p>',
        unsafe_allow_html=True,
    )
    st.subheader("Available tables and fields")
    render_schema_cards()

    render_query_workspace("Accounting report", 1)
    st.divider()
    render_query_workspace("Audit exception report", 2)

    if all(st.session_state.si_custom[route]["passed"] for route in ROUTES):
        st.button("Complete the SQL investigation", type="primary", width="stretch", on_click=set_stage, args=(5,))


def render_debrief() -> None:
    st.markdown('<div class="eyebrow">Investigation complete</div>', unsafe_allow_html=True)
    st.header("A correct query must match both the database structure and the accounting purpose")
    st.success("You read SQL in logical order, repaired a join that excluded the needed records, corrected a transaction measure, and produced both an accounting report and an audit exception report.")
    st.subheader("What changed in the report logic")
    st.markdown(
        """
        <div class="logic-grid">
          <section class="logic-card">
            <div class="logic-label">PRESERVE THE POPULATION</div>
            <h4>INNER JOIN → LEFT JOIN</h4>
            <p>The original join removed orders without payments before the NULL test could examine them. The repaired join keeps every order and exposes unmatched payment fields as NULL.</p>
          </section>
          <section class="logic-card">
            <div class="logic-label">MEASURE THE TRANSACTION</div>
            <h4>StandardPrice → ActualUnitPrice</h4>
            <p>The master-data price is a benchmark, not proof of the historical exchange. The order-line price records what the customer was actually charged.</p>
          </section>
          <section class="logic-card">
            <div class="logic-label">MATCH THE PURPOSE</div>
            <h4>Rows → accounting evidence</h4>
            <p>A sales report summarizes the full population. An audit query isolates exceptions for follow-up. Neither output becomes evidence until its fields and completeness fit the question.</p>
          </section>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("The reasoning chain")
    st.markdown(
        "FROM and JOIN determine which records can reach the result. WHERE then filters those candidate rows. GROUP BY and aggregate functions determine the level of summarization. SELECT names the fields and calculations displayed to the user. A query may run without an error and still answer the wrong accounting question."
    )
    st.markdown(
        '<div class="principle"><strong>Audit boundary</strong> SQL identifies a population or exception. The accountant still has to decide whether the data are complete, whether the fields mean what the report assumes, and what evidence would resolve each exception.</div>',
        unsafe_allow_html=True,
    )
    st.subheader("The same normalized structure supports each question")
    render_schema_cards()
    st.markdown(
        '<div class="principle"><strong>Why the structure matters</strong> Primary and foreign keys let the query reconstruct the order-to-cash process without duplicating facts. The reporting purpose then determines which relationships, filters, calculations, and level of summarization belong in the result.</div>',
        unsafe_allow_html=True,
    )
    attempts = st.session_state.si_attempts
    revisions = sum(max(0, value - 1) for value in attempts.values())
    col1, col2, col3 = st.columns(3)
    col1.metric("Investigation stages", "4 of 4")
    col2.metric("Reports built", "2 of 2")
    col3.metric("Revisions", revisions)


st.markdown(APP_CSS, unsafe_allow_html=True)
initialize_state()
render_hero()
top_left, top_right = st.columns([5, 1])
with top_right:
    st.button("Start over", width="stretch", on_click=restart)
render_stage_row()

stage = int(st.session_state.si_stage)
if stage == 0:
    render_schema_stage()
elif stage == 1:
    render_reading()
elif stage == 2:
    render_missing()
elif stage == 3:
    render_amount()
elif stage == 4:
    render_custom()
else:
    render_debrief()

sync_progress_query(st.session_state, st.query_params)
render_scroll_reset()

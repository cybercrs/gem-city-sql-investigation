# Gem City SQL Investigation

This independent investigation gives students a normalized order-to-cash database for the fictional Gem City Office Supply. Students read a query, diagnose missing rows, diagnose an incorrect sales amount, and write both an accounting report and an audit exception query. The app does not require a login and does not collect names or other identifying information.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Run the checks

```bash
python -m unittest discover -s tests -v
python -m py_compile streamlit_app.py gem_city_sql_investigation/*.py
```

Each student query runs against a fresh in-memory SQLite database. The executor accepts one `SELECT` or `WITH` query at a time, blocks data-changing statements, and limits result size. Student progress is stored in a compact validated `progress` parameter in the page URL.

The visual theme uses the University of Dayton's public red, navy, and turquoise color system. No university logo or protected mark is included.

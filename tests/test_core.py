import pandas as pd
import pytest

from app.charts import suggest_chart
from app.db import Database
from app.engine import Analyst, extract_sql
from app.guard import UnsafeSQLError, validate
from eval.run_eval import results_match


@pytest.fixture(scope="module")
def db():
    return Database()


# ---- guardrails ---------------------------------------------------------------
@pytest.mark.parametrize("sql", [
    "DROP TABLE fact_sales",
    "DELETE FROM fact_sales",
    "INSERT INTO dim_geography VALUES ('XX', 'X', 'X')",
    "UPDATE fact_orders SET is_late = 0",
    "CREATE TABLE t AS SELECT 1",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM fact_sales; DROP TABLE fact_sales",
    "SELECT * FROM users",
    "COPY fact_sales TO 'out.csv'",
    "ATTACH 'other.db'",
])
def test_guard_blocks_unsafe(sql):
    with pytest.raises(UnsafeSQLError):
        validate(sql)


def test_guard_allows_ctes_and_adds_limit():
    out = validate("WITH m AS (SELECT date_key, SUM(price) AS r FROM fact_sales GROUP BY 1) SELECT * FROM m")
    assert "LIMIT 1000" in out


def test_guard_keeps_existing_limit():
    assert "LIMIT 5" in validate("SELECT * FROM dim_geography LIMIT 5")


def test_database_blocks_file_access(db):
    with pytest.raises(Exception):
        db.query("SELECT * FROM read_csv_auto('/etc/hostname')")


# ---- engine -------------------------------------------------------------------
class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_self_correction_recovers_from_bad_column(db):
    llm = ScriptedLLM([
        "```sql\nSELECT SUM(revenue) FROM fact_sales\n```",
        "```sql\nSELECT ROUND(SUM(price), 2) AS revenue FROM fact_sales\n```",
    ])
    ans = Analyst(llm, db).ask("total revenue?", summarize=False)
    assert ans.ok and ans.attempts == 2
    assert round(float(ans.data.iat[0, 0]), 2) == 13221498.11
    assert "revenue" in llm.calls[1][-1]["content"].lower()  # error was fed back


def test_unsafe_sql_is_never_executed(db):
    llm = ScriptedLLM(["```sql\nDROP TABLE fact_sales\n```"] * 3)
    ans = Analyst(llm, db).ask("delete everything", summarize=False)
    assert not ans.ok and ans.attempts == 3
    assert db.row_count("fact_sales") == 110197


def test_extract_sql():
    assert extract_sql("Here you go:\n```sql\nSELECT 1;\n```") == "SELECT 1"
    assert extract_sql("SELECT 2") == "SELECT 2"


# ---- eval comparator & charts ------------------------------------------------------
def test_results_match_ignores_names_and_order():
    a = pd.DataFrame({"region": ["South", "North"], "rev": [10.04, 2.0]})
    b = pd.DataFrame({"r": [2.0, 10.0], "reg": ["north", "south"]})[["reg", "r"]]
    assert results_match(a, b)
    assert not results_match(a, b.head(1))


def test_suggest_chart():
    ts = pd.DataFrame({"year_month": ["2018-01", "2018-02"], "revenue": [1.0, 2.0]})
    cat = pd.DataFrame({"category": ["A", "B"], "revenue": [1.0, 2.0]})
    assert suggest_chart(ts)[0] == "line"
    assert suggest_chart(cat)[0] == "bar"
    assert suggest_chart(pd.DataFrame({"revenue": [1.0]})) is None
